'use strict';
// Generic JSON document store persisted to data/db.json.
// Collections are arrays of plain objects. Every record gets a string `id`.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, '..', 'data');
const FILE = path.join(DATA_DIR, 'db.json');

let state = { collections: {}, counters: {} };
let saveTimer = null;

function load() {
  try {
    if (fs.existsSync(FILE)) state = JSON.parse(fs.readFileSync(FILE, 'utf8'));
  } catch (err) {
    console.error('db load failed, starting empty:', err.message);
    state = { collections: {}, counters: {} };
  }
  state.collections = state.collections || {};
  state.counters = state.counters || {};
}

function saveNow() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const tmp = FILE + '.' + process.pid + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(state));
  fs.renameSync(tmp, FILE);
}

function save() {
  if (saveTimer) return;
  saveTimer = setTimeout(() => { saveTimer = null; try { saveNow(); } catch (e) { console.error('db save failed', e); } }, 50);
}

function all(name) {
  if (!state.collections[name]) state.collections[name] = [];
  return state.collections[name];
}

function matches(rec, query) {
  if (!query) return true;
  if (typeof query === 'function') return !!query(rec);
  for (const k of Object.keys(query)) {
    if (rec[k] !== query[k]) return false;
  }
  return true;
}

function nextId(name) {
  state.counters[name] = (state.counters[name] || 0) + 1;
  return String(state.counters[name]);
}

const db = {
  load, save, saveNow,
  /** All records of a collection (live array; call db.save() after mutating). */
  all,
  /** Records matching an object (field equality) or predicate function. */
  find(name, query) { return all(name).filter((r) => matches(r, query)); },
  findOne(name, query) { return all(name).find((r) => matches(r, query)) || null; },
  get(name, id) { return all(name).find((r) => r.id === String(id)) || null; },
  /** Insert a record; assigns id (if missing), createdAt and updatedAt. Returns the stored record. */
  insert(name, rec) {
    const now = new Date().toISOString();
    const stored = { id: rec.id != null ? String(rec.id) : nextId(name), createdAt: now, updatedAt: now, ...rec };
    if (rec.id != null) stored.id = String(rec.id);
    all(name).push(stored);
    save();
    return stored;
  },
  /** Shallow-merge changes into the first record matching query. Returns the record or null. */
  update(name, query, changes) {
    const rec = typeof query === 'string' ? db.get(name, query) : db.findOne(name, query);
    if (!rec) return null;
    Object.assign(rec, changes, { updatedAt: new Date().toISOString() });
    save();
    return rec;
  },
  /** Remove all records matching query. Returns number removed. */
  remove(name, query) {
    const list = all(name);
    let removed = 0;
    for (let i = list.length - 1; i >= 0; i--) {
      if (matches(list[i], query)) { list.splice(i, 1); removed++; }
    }
    if (removed) save();
    return removed;
  },
  /** Insert only if no record matches `match` (idempotent seeding). Returns existing or new record. */
  ensure(name, match, rec) {
    const existing = db.findOne(name, match);
    if (existing) return existing;
    return db.insert(name, { ...match, ...rec });
  },
  /** Run fn and persist; use for multi-record atomic updates. */
  transaction(fn) { const out = fn(db); save(); return out; },
  uid() { return crypto.randomBytes(8).toString('hex'); },
};

module.exports = db;
