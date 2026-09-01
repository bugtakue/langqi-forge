import { pbkdf2Sync, randomBytes, randomUUID, timingSafeEqual } from "node:crypto";

const CREDENTIAL_SCHEME = "pbkdf2-sha256";
const CREDENTIAL_ITERATIONS = 120_000;
const CREDENTIAL_BYTES = 32;

export function normalizeEmail(value) {
  return String(value ?? "").trim().toLowerCase();
}

export function validateUsername(value) {
  const username = String(value ?? "").trim();
  return /^(?=.{1,39}$)[a-z0-9]+(?:-[a-z0-9]+)*$/.test(username)
    ? { ok: true, value: username }
    : { ok: false, code: "invalid_username", message: "Username must contain 1–39 lowercase letters, digits, or single hyphens." };
}

export function validateEmail(value) {
  const email = normalizeEmail(value);
  const parts = email.split("@");
  const labels = parts.length === 2 ? parts[1].split(".") : [];
  const valid = email.length <= 254
    && parts.length === 2
    && Boolean(parts[0])
    && !/\s/.test(email)
    && labels.length >= 2
    && labels.every(Boolean);
  return valid
    ? { ok: true, value: email }
    : { ok: false, code: "invalid_email", message: "Email format is invalid." };
}

export function validatePassword(value) {
  const password = String(value ?? "");
  const valid = password.length >= 12
    && password.length <= 128
    && !/\s/.test(password)
    && /[A-Z]/.test(password)
    && /[a-z]/.test(password)
    && /[0-9]/.test(password)
    && /[^A-Za-z0-9]/.test(password);
  return valid
    ? { ok: true, value: password }
    : { ok: false, code: "invalid_password", message: "Password must be 12–128 characters and include upper, lower, digit, and special characters without whitespace." };
}

export function hashPassword(password) {
  const checked = validatePassword(password);
  if (!checked.ok) throw new Error(checked.message);
  const salt = randomBytes(16);
  const derived = pbkdf2Sync(checked.value, salt, CREDENTIAL_ITERATIONS, CREDENTIAL_BYTES, "sha256");
  return `${CREDENTIAL_SCHEME}$${CREDENTIAL_ITERATIONS}$${salt.toString("hex")}$${derived.toString("hex")}`;
}

export function verifyPassword(account, candidate, overrideHash = "") {
  const encoded = String(overrideHash || account?.passwordHash || "");
  const [scheme, iterationsText, saltHex, expectedHex] = encoded.split("$");
  if (scheme === CREDENTIAL_SCHEME && /^[0-9]+$/.test(iterationsText) && /^[a-f0-9]+$/i.test(saltHex || "") && /^[a-f0-9]+$/i.test(expectedHex || "")) {
    const expected = Buffer.from(expectedHex, "hex");
    if (expected.length !== CREDENTIAL_BYTES) return false;
    const actual = pbkdf2Sync(String(candidate ?? ""), Buffer.from(saltHex, "hex"), Number(iterationsText), expected.length, "sha256");
    return timingSafeEqual(actual, expected);
  }
  // Read-only compatibility for an old local demo state. New and reset states
  // never write plaintext credentials.
  const legacy = Buffer.from(String(account?.password ?? ""));
  const supplied = Buffer.from(String(candidate ?? ""));
  return legacy.length === supplied.length && legacy.length > 0 && timingSafeEqual(legacy, supplied);
}

export function publicAccount(account) {
  const { password: _password, passwordHash: _passwordHash, ...safe } = account || {};
  return safe;
}

export class SessionStore {
  constructor({ sessionTtlMs = 24 * 60 * 60 * 1000, recoveryTtlMs = 15 * 60 * 1000 } = {}) {
    this.sessionTtlMs = sessionTtlMs;
    this.recoveryTtlMs = recoveryTtlMs;
    this.sessions = new Map();
    this.recoveries = new Map();
  }

  createSession(username, worldId) {
    const token = randomUUID();
    this.storeSession(token, username, worldId);
    return token;
  }

  storeSession(token, username, worldId) {
    this.sessions.set(token, { username, worldId, createdAt: Date.now(), expiresAt: Date.now() + this.sessionTtlMs });
    return token;
  }

  resolveSession(token, worldId) {
    const session = this.sessions.get(String(token || ""));
    if (!session) return null;
    if (session.expiresAt <= Date.now() || session.worldId !== worldId) {
      this.sessions.delete(String(token || ""));
      return null;
    }
    return session;
  }

  destroySession(token) {
    return this.sessions.delete(String(token || ""));
  }

  destroyAccountSessions(username, worldId) {
    for (const [token, session] of this.sessions) {
      if (session.username === username && session.worldId === worldId) this.sessions.delete(token);
    }
  }

  beginRecovery(email, worldId) {
    const token = randomUUID();
    this.storeRecovery(token, email, worldId);
    return token;
  }

  storeRecovery(token, email, worldId) {
    this.recoveries.set(token, { email: normalizeEmail(email), worldId, expiresAt: Date.now() + this.recoveryTtlMs });
    return token;
  }

  resolveRecovery(token, worldId) {
    const context = this.recoveries.get(String(token || ""));
    if (!context || context.expiresAt <= Date.now() || context.worldId !== worldId) return null;
    return context;
  }

  consumeRecovery(token, worldId) {
    const key = String(token || "");
    const context = this.resolveRecovery(key, worldId);
    this.recoveries.delete(key);
    return context;
  }
}

export function bearerToken(request) {
  const match = /^Bearer\s+([^\s]+)$/i.exec(String(request?.headers?.authorization || ""));
  return match?.[1] || "";
}
