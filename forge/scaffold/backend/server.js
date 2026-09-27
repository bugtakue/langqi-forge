'use strict';
// Generic zero-dependency HTTP framework: routing, JSON bodies, cookie sessions,
// static frontend serving with SPA fallback, route/seed module auto-loading.
// Application code lives in routes/*.js and seed/*.js (loaded in filename order).
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const db = require('./lib/db');

const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || '0.0.0.0';
const STATIC_DIR = path.join(__dirname, '..', 'frontend', 'dist');
const SESSION_COOKIE = 'sid';

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8', '.csv': 'text/csv; charset=utf-8', '.woff2': 'font/woff2',
};

// ---------- auth helpers ----------
function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(String(password), salt, 32).toString('hex');
  return `scrypt$${salt}$${hash}`;
}
function verifyPassword(password, stored) {
  if (!stored || typeof stored !== 'string' || !stored.startsWith('scrypt$')) return false;
  const [, salt, hash] = stored.split('$');
  const test = crypto.scryptSync(String(password), salt, 32).toString('hex');
  return crypto.timingSafeEqual(Buffer.from(test, 'hex'), Buffer.from(hash, 'hex'));
}
/** Remove secret-looking fields (password, hash, token) before sending a record to the client. */
function publicUser(user) {
  if (!user) return null;
  const out = {};
  for (const [k, v] of Object.entries(user)) {
    if (/password|hash|secret|token/i.test(k)) continue;
    out[k] = v;
  }
  return out;
}

class HttpError extends Error {
  constructor(status, message, extra) { super(message); this.status = status; this.extra = extra; }
}

// ---------- router ----------
const routes = [];
// Patterns: literal segments, `:name` (one segment) and `:name*` (rest of path, may contain '/').
function addRoute(method, pattern, handler) {
  const keys = [];
  const segs = (pattern.replace(/\/+$/, '') || '/').split('/').filter(Boolean);
  let src = '';
  for (const seg of segs) {
    const m = /^:(\w+)(\*)?$/.exec(seg);
    if (m) { keys.push(m[1]); src += m[2] ? '(?:/(.*))?' : '/([^/]+)'; }
    else src += '/' + seg.replace(/[.+?^${}()|[\]\\*]/g, '\\$&');
  }
  routes.push({ method, re: new RegExp('^' + (src || '/') + '/?$'), keys, handler, pattern });
}
const app = {
  get: (p, h) => addRoute('GET', p, h),
  post: (p, h) => addRoute('POST', p, h),
  put: (p, h) => addRoute('PUT', p, h),
  patch: (p, h) => addRoute('PATCH', p, h),
  delete: (p, h) => addRoute('DELETE', p, h),
};

function parseCookies(header) {
  const out = {};
  (header || '').split(';').forEach((part) => {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  });
  return out;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => { size += c.length; if (size > 20 * 1024 * 1024) { reject(new HttpError(413, 'Payload too large')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

function send(res, status, body, headers = {}) {
  if (res.headersSent) return;
  if (body !== undefined && typeof body !== 'string' && !Buffer.isBuffer(body)) {
    body = JSON.stringify(body);
    headers['Content-Type'] = headers['Content-Type'] || 'application/json; charset=utf-8';
  }
  res.writeHead(status, { 'Cache-Control': 'no-store', ...headers });
  res.end(body);
}

// ---------- sessions ----------
function loadSession(req) {
  const sid = req.cookies[SESSION_COOKIE];
  if (!sid) return null;
  const s = db.findOne('sessions', { sid });
  return s || null;
}
function createSession(res, userId) {
  const sid = crypto.randomBytes(24).toString('hex');
  db.insert('sessions', { sid, userId: String(userId) });
  res.setHeader('Set-Cookie', `${SESSION_COOKIE}=${sid}; Path=/; HttpOnly; SameSite=Lax`);
  return sid;
}
function destroySession(req, res) {
  const sid = req.cookies[SESSION_COOKIE];
  if (sid) db.remove('sessions', { sid });
  res.setHeader('Set-Cookie', `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`);
}
/** Invalidate every session of a user (optionally keeping one sid). */
function destroyUserSessions(userId, exceptSid) {
  db.remove('sessions', (s) => s.userId === String(userId) && s.sid !== exceptSid);
}

const ctx = {
  db, HttpError, hashPassword, verifyPassword, publicUser, createSession, destroySession, destroyUserSessions,
  /** Throw 401 unless signed in; returns the user record. */
  requireUser(req) { if (!req.user) throw new HttpError(401, 'Authentication required'); return req.user; },
};

// ---------- static ----------
function serveStatic(req, res, urlPath) {
  let rel = decodeURIComponent(urlPath);
  if (rel.includes('\0')) return false;
  let file = path.normalize(path.join(STATIC_DIR, rel));
  if (!file.startsWith(STATIC_DIR)) return false;
  if (fs.existsSync(file) && fs.statSync(file).isFile()) {
    const ext = path.extname(file).toLowerCase();
    send(res, 200, fs.readFileSync(file), { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    return true;
  }
  return false;
}
function serveIndex(res) {
  const index = path.join(STATIC_DIR, 'index.html');
  if (fs.existsSync(index)) send(res, 200, fs.readFileSync(index), { 'Content-Type': MIME['.html'] });
  else send(res, 200, '<!doctype html><title>App</title><p>Frontend not built</p>', { 'Content-Type': MIME['.html'] });
}

// ---------- request handling ----------
async function handle(req, res) {
  const url = new URL(req.url, 'http://localhost');
  req.path = url.pathname;
  req.query = Object.fromEntries(url.searchParams.entries());
  req.cookies = parseCookies(req.headers.cookie);
  req.session = loadSession(req);
  req.user = req.session ? db.get('users', req.session.userId) : null;

  if (req.path === '/api/health') return send(res, 200, { ok: true, ready: true });
  if (req.path === '/api/session' && req.method === 'GET') return send(res, 200, { user: publicUser(req.user) });

  if (req.path.startsWith('/api/')) {
    for (const r of routes) {
      if (r.method !== req.method) continue;
      const m = r.re.exec(req.path);
      if (!m) continue;
      req.params = {};
      r.keys.forEach((k, i) => { req.params[k] = m[i + 1] == null ? '' : decodeURIComponent(m[i + 1]); });
      const raw = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method) ? await readBody(req) : Buffer.alloc(0);
      req.rawBody = raw;
      req.body = {};
      if (raw.length) {
        const type = req.headers['content-type'] || '';
        if (type.includes('application/json')) {
          try { req.body = JSON.parse(raw.toString('utf8')); } catch { throw new HttpError(400, 'Invalid JSON body'); }
        } else if (type.includes('application/x-www-form-urlencoded')) {
          req.body = Object.fromEntries(new URLSearchParams(raw.toString('utf8')).entries());
        } else {
          req.body = { text: raw.toString('utf8') };
        }
      }
      const result = await r.handler(req, res, ctx);
      if (!res.headersSent) send(res, 200, result === undefined ? { ok: true } : result);
      return;
    }
    return send(res, 404, { error: 'Not found' });
  }

  if (req.method === 'GET' || req.method === 'HEAD') {
    if (serveStatic(req, res, req.path)) return;
    return serveIndex(res);
  }
  send(res, 404, { error: 'Not found' });
}

function loadModules(dir, apply) {
  const full = path.join(__dirname, dir);
  if (!fs.existsSync(full)) return;
  for (const f of fs.readdirSync(full).filter((f) => f.endsWith('.js')).sort()) {
    try { apply(require(path.join(full, f)), f); } catch (err) { console.error(`failed to load ${dir}/${f}:`, err); }
  }
}

function start() {
  db.load();
  loadModules('seed', (mod, f) => { const fn = typeof mod === 'function' ? mod : mod.seed; if (typeof fn === 'function') fn(db, ctx); });
  db.saveNow();
  loadModules('routes', (mod) => { const fn = typeof mod === 'function' ? mod : mod.register; if (typeof fn === 'function') fn(app, ctx); });
  const server = http.createServer((req, res) => {
    handle(req, res).catch((err) => {
      const status = err instanceof HttpError ? err.status : 500;
      if (status >= 500) console.error(err);
      send(res, status, { error: err.message || 'Server error', ...(err.extra || {}) });
    });
  });
  server.listen(PORT, HOST, () => console.log(`server listening on ${HOST}:${PORT}`));
}

module.exports = { app, ctx };
if (require.main === module) start();
