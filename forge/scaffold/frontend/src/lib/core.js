// Generic SPA runtime: history router, API helper, session state, shell rendering.
// Page modules live in /pages/*.js and export `routes = [{ path, render }]`.
// `render(el, ctx)` fills `el` (the main content element) and attaches listeners.
import pageModules from '../pages/_index.js';
import * as shell from '../shell.js';

export const state = { user: null };

/** HTML-escape any value for safe interpolation into template strings. */
export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/** fetch wrapper: JSON in/out, cookies included. Throws Error(message) with .status and .data on non-2xx. */
export async function api(method, path, body) {
  const opts = { method, headers: {}, credentials: 'same-origin' };
  if (body !== undefined) {
    if (typeof body === 'string') { opts.body = body; opts.headers['Content-Type'] = 'text/plain'; }
    else { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json'; }
  }
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const err = new Error((data && (data.error || data.message)) || `Request failed (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

/** Collect named form controls into a plain object (checkboxes -> boolean). */
export function formData(form) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === 'checkbox') out[el.name] = el.checked;
    else if (el.type === 'radio') { if (el.checked) out[el.name] = el.value; }
    else out[el.name] = el.value;
  }
  return out;
}

export async function refreshUser() {
  try { state.user = (await api('GET', '/api/session')).user; } catch { state.user = null; }
  return state.user;
}

// ---------- router ----------
const table = [];
for (const mod of pageModules) {
  for (const r of mod.routes || []) {
    const segs = r.path.split('/').filter(Boolean);
    const keys = [];
    const re = new RegExp('^' + segs.map((s) => {
      const m = /^:(\w+)(\*)?$/.exec(s);
      if (m) { keys.push(m[1]); return m[2] ? '(?:/(.*))?' : '/([^/]+)'; }
      return '/' + s.replace(/[.+?^${}()|[\]\\*]/g, '\\$&');
    }).join('') + '/?$');
    const score = segs.reduce((a, s) => a + (s.startsWith(':') ? (s.endsWith('*') ? 0 : 1) : 3), 0) * 10 + segs.length;
    table.push({ ...r, re: segs.length ? re : /^\/?$/, keys, score });
  }
}
table.sort((a, b) => b.score - a.score);

function match(pathname) {
  for (const r of table) {
    const m = r.re.exec(pathname);
    if (m) {
      const params = {};
      r.keys.forEach((k, i) => { params[k] = m[i + 1] == null ? '' : decodeURIComponent(m[i + 1]); });
      return { route: r, params };
    }
  }
  return null;
}

let renderToken = 0;
export async function render() {
  const token = ++renderToken;
  const url = new URL(location.href);
  const found = match(url.pathname);
  const ctx = {
    params: found ? found.params : {},
    query: Object.fromEntries(url.searchParams.entries()),
    path: url.pathname,
    get user() { return state.user; },
    api, esc, navigate, formData, refreshUser, state,
    rerender: render,
    isCurrent: () => token === renderToken,
  };
  const root = document.getElementById('app');
  let main;
  try {
    main = (await shell.renderShell(root, ctx)) || root;
  } catch (err) {
    console.error(err);
    root.innerHTML = '<main id="main"></main>';
    main = root.querySelector('main');
  }
  if (token !== renderToken) return;
  if (!found) {
    main.innerHTML = '<h1>Page not found</h1><p><a href="/">Go home</a></p>';
    return;
  }
  try {
    if (found.route.title) document.title = found.route.title;
    await found.route.render(main, ctx);
  } catch (err) {
    console.error(err);
    if (token !== renderToken) return;
    main.innerHTML = `<div role="alert" class="error">${esc(err.message || 'Something went wrong')}</div>`;
  }
}

/** Client-side navigation; re-renders the matched page. */
export async function navigate(to, { replace = false } = {}) {
  if (replace) history.replaceState({}, '', to);
  else history.pushState({}, '', to);
  await render();
}

document.addEventListener('click', (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest('a[href]');
  if (!a || a.target || a.hasAttribute('download') || a.dataset.external !== undefined) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  e.preventDefault();
  navigate(url.pathname + url.search + url.hash);
});
window.addEventListener('popstate', () => render());

refreshUser().then(render);
