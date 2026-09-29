import { createServer } from "node:http";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes, randomUUID, scryptSync, timingSafeEqual } from "node:crypto";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../frontend/dist");
const dataDir = process.env.DATA_DIR || path.join(here, "data");
const dataPath = path.join(dataDir, "state.json");
const port = Number.parseInt(process.env.PORT || "3000", 10);
const host = process.env.HOST || "0.0.0.0";
const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

let writeChain = Promise.resolve();

function hashPassword(password) {
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(password, salt, 32).toString("hex");
  return `scrypt$${salt}$${hash}`;
}

function verifyPassword(password, stored) {
  const [kind, salt, hash] = String(stored || "").split("$");
  if (kind !== "scrypt" || !salt || !hash) return false;
  const actual = scryptSync(String(password), salt, 32);
  const expected = Buffer.from(hash, "hex");
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

function usernameOk(name) {
  return typeof name === "string"
    && name.length >= 1
    && name.length <= 39
    && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name);
}

function emailOk(email) {
  if (typeof email !== "string") return false;
  const value = email.trim();
  if (!value || value.length > 254) return false;
  const parts = value.split("@");
  if (parts.length !== 2 || !parts[0] || !parts[1]) return false;
  return parts[1].split(".").every((label) => label.length > 0) && parts[1].includes(".");
}

function passwordOk(password) {
  return typeof password === "string"
    && password.length >= 12
    && password.length <= 128
    && !/\s/.test(password)
    && /[A-Z]/.test(password)
    && /[a-z]/.test(password)
    && /[0-9]/.test(password)
    && /[^A-Za-z0-9]/.test(password);
}

function seedState() {
  return {
    users: [{
      id: "user-alice",
      username: "alice-dev",
      email: "alice.dev@example.test",
      password: hashPassword("Valid-password-123!"),
      emailVerified: true,
    }, {
      id: "user-bob",
      username: "bob-reviewer",
      email: "bob.reviewer@example.test",
      password: hashPassword("Valid-password-123!"),
      emailVerified: true,
    }],
    sessions: [],
    organizations: [{
      name: "acme-demo",
      displayName: "Acme Demo",
      owner: "alice-dev",
    }],
    members: [
      { org: "acme-demo", username: "alice-dev", role: "Owner" },
      { org: "acme-demo", username: "bob-reviewer", role: "Member" },
    ],
    teams: [
      { org: "acme-demo", name: "platform-team", parent: "" },
      { org: "acme-demo", name: "frontend-team", parent: "platform-team" },
      { org: "acme-demo", name: "frontend-child", parent: "frontend-team" },
    ],
    teamMembers: [],
    grants: [
      { owner: "alice-dev", repo: "acme-docs", subjectType: "user", subject: "bob-reviewer", role: "Write" },
    ],
    issues: [
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 1,
        title: "Improve onboarding",
        body: "Describe the onboarding improvement. Welcome flow notes.",
        state: "open",
        author: "alice-dev",
        assignees: [],
        labels: ["bug", "documentation"],
        milestone: "Q3 launch",
        comments: [{ author: "alice-dev", body: "Tracking the welcome flow.", time: "1 hour ago", reactions: [] }],
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 4,
        title: "Closed onboarding bug",
        body: "Archived bug notes.",
        state: "closed",
        author: "alice-dev",
        assignees: [],
        labels: ["bug"],
        milestone: "",
        comments: [],
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 6,
        title: "Legacy welcome text",
        body: "Older welcome copy.",
        state: "closed",
        author: "alice-dev",
        assignees: [],
        labels: ["bug"],
        milestone: "",
        updated: "3 days ago",
        comments: [],
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 5,
        title: "Original issue title",
        body: "Keep this title when a blank edit is rejected.",
        state: "open",
        author: "alice-dev",
        assignees: [],
        labels: [],
        milestone: "",
        comments: [],
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 2,
        title: "Fix search",
        body: "Search still misses notes.",
        state: "open",
        author: "alice-dev",
      },
    ],
    pulls: [
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 1,
        title: "Improve onboarding",
        state: "open",
        author: "alice-dev",
        head: "feature-search",
        base: "main",
        approved: true,
        check: "success",
        reviewers: [],
        reviews: [],
        activity: [],
        changedFiles: ["src/search.ts", "docs/onboarding.txt"],
        additions: 3,
        deletions: 1,
        line: "+export const query = \"search flow\";",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 2,
        title: "Fix search",
        state: "open",
        author: "alice-dev",
        head: "feature-search",
        base: "main",
        approved: false,
        check: "success",
        reviewers: [],
        reviews: [],
        activity: [],
        changedFiles: ["src/search.ts"],
        additions: 1,
        deletions: 0,
        line: "+export const pending = true;",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 3,
        title: "Draft onboarding update",
        state: "draft",
        author: "alice-dev",
        head: "draft-feature",
        base: "main",
        approved: false,
        check: "success",
        reviewers: [],
        reviews: [],
        activity: [],
        changedFiles: ["docs/onboarding.txt"],
        additions: 1,
        deletions: 0,
        line: "+Draft notes.",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        number: 4,
        title: "Archive search notes",
        state: "closed",
        author: "alice-dev",
        head: "feature-search",
        base: "main",
        approved: false,
        check: "pending",
        reviewers: [],
        reviews: [],
        activity: [],
        changedFiles: ["docs/onboarding.txt"],
        additions: 0,
        deletions: 1,
        line: "-Old notes.",
      },
    ],
    labels: [
      { owner: "alice-dev", repo: "acme-docs", name: "bug" },
      { owner: "alice-dev", repo: "acme-docs", name: "documentation" },
    ],
    milestones: [
      { owner: "alice-dev", repo: "acme-docs", name: "Q3 launch" },
      { owner: "alice-dev", repo: "acme-docs", name: "v1.0" },
    ],
    protections: [
      { owner: "alice-dev", repo: "acme-docs", branch: "main", review: true, check: true },
    ],
    repositories: [
      {
        owner: "alice-dev",
        name: "acme-docs",
        visibility: "public",
        description: "Public notes for the search flow.",
        defaultBranch: "main",
        organization: "acme-demo",
        updated: "1 hour ago",
      },
      {
        owner: "alice-dev",
        name: "secret-research",
        visibility: "private",
        description: "Private research notes.",
        defaultBranch: "main",
        organization: "acme-demo",
        updated: "3 hours ago",
      },
      {
        owner: "alice-dev",
        name: "acme-fork",
        visibility: "public",
        description: "Existing fork name.",
        defaultBranch: "main",
        organization: "",
        updated: "1 day ago",
        forkedFrom: { owner: "alice-dev", name: "acme-docs" },
      },
    ],
    files: [
      {
        owner: "alice-dev",
        repo: "acme-docs",
        path: "README.md",
        branch: "main",
        content: "Document search flow for repository readers.\n",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        path: "docs/guide.txt",
        branch: "main",
        content: "Notes for the docs directory.\n",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        path: "src/search.ts",
        branch: "main",
        content: "export const query = \"search flow\";\n",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        path: "NOTES.md",
        branch: "feature-search",
        content: "Feature branch notes.\n",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        path: "README.md",
        branch: "feature-search",
        content: "Feature-search branch notes.\n",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        path: "main-only.md",
        branch: "feature-search",
        content: "This file exists only on feature-search.\n",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        path: "README.md",
        branch: "release",
        content: "Document search flow for repository readers.\n",
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        path: "docs/onboarding.txt",
        branch: "draft-feature",
        content: "Draft notes.\n",
      },
      {
        owner: "alice-dev",
        repo: "secret-research",
        path: "README.md",
        branch: "main",
        content: "Document search flow for private readers.\n",
      },
    ],
    commits: [
      {
        owner: "alice-dev",
        repo: "acme-docs",
        branch: "main",
        sha: "a11ce01",
        parent: null,
        author: "alice-dev",
        message: "Initial repository notes",
        time: "2 days ago",
        files: ["docs/guide.txt"],
        additions: 1,
        deletions: 0,
        patches: { "docs/guide.txt": ["+Notes for the docs directory."] },
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        branch: "main",
        sha: "b22ce02",
        parent: "a11ce01",
        author: "alice-dev",
        message: "Document search flow",
        time: "1 hour ago",
        files: ["README.md", "src/search.ts"],
        additions: 2,
        deletions: 0,
        patches: {
          "README.md": ["+Document search flow for repository readers."],
          "src/search.ts": ["+export const query = \"search flow\";"],
        },
      },
      {
        owner: "alice-dev",
        repo: "acme-docs",
        branch: "feature-search",
        sha: "c33ce03",
        parent: "a11ce01",
        author: "alice-dev",
        message: "Start feature search notes",
        time: "3 hours ago",
        files: ["NOTES.md"],
        additions: 1,
        deletions: 0,
        patches: { "NOTES.md": ["+Feature branch notes."] },
      },
    ],
  };
}

async function loadState() {
  try {
    const parsed = JSON.parse(await readFile(dataPath, "utf8"));
    if (!parsed.users) return seedState();
    return parsed;
  } catch (error) {
    if (error && error.code === "ENOENT") return seedState();
    throw error;
  }
}

async function saveState(next) {
  await mkdir(path.dirname(dataPath), { recursive: true });
  const temporary = `${dataPath}.${randomUUID()}.tmp`;
  await writeFile(temporary, JSON.stringify(next));
  await rename(temporary, dataPath);
  return next;
}

function transact(mutator) {
  const run = writeChain.then(async () => {
    const current = await loadState();
    const draft = structuredClone(current);
    const result = await mutator(draft);
    await saveState(draft);
    return result;
  });
  writeChain = run.then(() => undefined, () => undefined);
  return run;
}

function cookieValue(request, name) {
  const header = request.headers.cookie || "";
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return "";
}

function publicUser(user) {
  if (!user) return null;
  return { id: user.id, username: user.username, email: user.email, emailVerified: true };
}

function currentUser(state, request) {
  const sid = cookieValue(request, "sid");
  const session = state.sessions.find((item) => item.id === sid);
  if (!session) return null;
  return state.users.find((user) => user.id === session.userId) || null;
}

function sendJson(response, status, body, extraHeaders) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    ...(extraHeaders || {}),
  });
  response.end(JSON.stringify(body));
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    request.on("data", (chunk) => {
      size += chunk.length;
      if (size > 1_000_000) {
        reject(Object.assign(new Error("Payload too large"), { status: 413 }));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => {
      if (!chunks.length) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(Object.assign(new Error("Invalid JSON"), { status: 400 }));
      }
    });
    request.on("error", reject);
  });
}

function memberRole(state, orgName, username) {
  const member = (state.members || []).find((item) => item.org === orgName && item.username === username);
  return member ? member.role : "";
}

function teamNameOk(name) {
  return typeof name === "string"
    && name.length >= 1
    && name.length <= 50
    && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name);
}

function branchNameOk(name) {
  if (typeof name !== "string" || name.length < 1 || name.length > 100) return false;
  if (name.endsWith("/") || name.endsWith(".") || name.includes("..") || name.includes("//")) return false;
  if (name.startsWith("/") || name.startsWith(".")) return false;
  return /^[A-Za-z0-9._/-]+$/.test(name);
}

function teamDescendants(state, org, name, seen = new Set()) {
  const found = [];
  for (const team of state.teams || []) {
    if (team.org !== org || team.parent !== name || seen.has(team.name)) continue;
    seen.add(team.name);
    found.push(team.name, ...teamDescendants(state, org, team.name, seen));
  }
  return found;
}

function onTeam(state, org, team, username) {
  return (state.teamMembers || []).some((item) => item.org === org && item.team === team && item.username === username);
}

function repoGrant(state, record, subjectType, subject) {
  return (state.grants || []).find((item) => item.owner === record.owner && item.repo === record.name
    && item.subjectType === subjectType && item.subject === subject);
}

function canManagePull(state, record, pull, user) {
  if (!user || !pull) return false;
  if (user.username === pull.author) return true;
  return canAdminRepo(state, record, user);
}

function canAdminRepo(state, record, user) {
  if (!user || !record) return false;
  if (user.username === record.owner) return true;
  if (record.organization && memberRole(state, record.organization, user.username) === "Owner") return true;
  const grant = repoGrant(state, record, "user", user.username);
  return Boolean(grant && (grant.role === "Admin" || grant.role === "Maintain"));
}

function isRepoAdmin(state, record, user) {
  if (!user || !record) return false;
  if (user.username === record.owner) return true;
  if (record.organization && memberRole(state, record.organization, user.username) === "Owner") return true;
  const grant = repoGrant(state, record, "user", user.username);
  return Boolean(grant && grant.role === "Admin");
}

function canWriteRepo(state, record, user) {
  if (!user || !record) return false;
  if (user.username === record.owner) return true;
  if (record.organization && memberRole(state, record.organization, user.username) === "Owner") return true;
  const grant = repoGrant(state, record, "user", user.username);
  return Boolean(grant && ["Write", "Maintain", "Admin"].includes(grant.role));
}

function eligibleReviewers(state, record, pull) {
  if (!record || !pull) return [];
  const names = new Set();
  for (const user of state.users || []) {
    if (user.username !== pull.author && canWriteRepo(state, record, user)) names.add(user.username);
  }
  for (const grant of state.grants || []) {
    if (grant.owner === record.owner && grant.repo === record.name && grant.subjectType === "user"
      && grant.subject !== pull.author && ["Write", "Maintain", "Admin"].includes(grant.role)) {
      names.add(grant.subject);
    }
  }
  return [...names];
}

function eligibleAssignees(state, record) {
  if (!record) return [];
  const names = new Set();
  for (const grant of state.grants || []) {
    if (grant.owner === record.owner && grant.repo === record.name && grant.subjectType === "user"
      && ["Triage", "Write", "Maintain", "Admin"].includes(grant.role)) {
      names.add(grant.subject);
    }
  }
  return [...names];
}

function canManageIssues(state, record, user) {
  if (!user || !record) return false;
  if (user.username === record.owner) return true;
  if (record.organization && memberRole(state, record.organization, user.username) === "Owner") return true;
  const grant = repoGrant(state, record, "user", user.username);
  return Boolean(grant && ["Triage", "Maintain", "Admin"].includes(grant.role));
}

function canSeeRepo(state, record, user) {
  if (!record) return false;
  if (record.visibility === "public") return true;
  if (!user) return false;
  if (user.username === record.owner) return true;
  const org = record.organization || "";
  if (org && memberRole(state, org, user.username) === "Owner") return true;
  if (repoGrant(state, record, "user", user.username)) return true;
  return (state.teamMembers || []).some((item) => item.username === user.username
    && repoGrant(state, record, "team", item.team));
}

function visibleRepo(state, owner, repo, user) {
  const record = state.repositories.find((item) => item.owner === owner && item.name === repo);
  return canSeeRepo(state, record, user) ? record : null;
}

function repoView(state, record) {
  const org = (state.organizations || []).find((item) => item.name === record.organization);
  return { ...record, orgDisplay: org ? org.displayName : "" };
}

function snippet(content, query) {
  const lines = String(content).split("\n");
  const hit = query ? lines.find((line) => line.includes(query)) : lines[0];
  return hit || lines[0] || "";
}

async function handleApi(request, response, url) {
  const parts = url.pathname.split("/").filter(Boolean);
  if (request.method === "GET" && url.pathname === "/api/health") {
    sendJson(response, 200, { ready: true });
    return true;
  }
  if (request.method === "GET" && url.pathname === "/api/session") {
    const state = await loadState();
    sendJson(response, 200, { user: publicUser(currentUser(state, request)) });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/register") {
    const body = await readBody(request);
    const username = String(body.username || "");
    const email = String(body.email || "").trim().toLowerCase();
    const password = String(body.password || "");
    const confirm = String(body.confirm || "");
    const messages = [];
    if (!usernameOk(username)) messages.push("Username format is invalid");
    if (!emailOk(email)) messages.push("Email format is invalid");
    if (!passwordOk(password) || password !== confirm) messages.push("Password requirements are not satisfied");
    if (body.terms !== true) messages.push("Agree to terms is required");
    const result = await transact((draft) => {
      if (!messages.length && draft.users.some((user) => user.username === username)) {
        messages.push("Username already exists");
      }
      if (!messages.length && draft.users.some((user) => user.email === email)) {
        messages.push("Email is already in use");
      }
      if (messages.length) return { ok: false, messages };
      draft.users.push({
        id: randomUUID(),
        username,
        email,
        password: hashPassword(password),
        emailVerified: true,
      });
      return { ok: true };
    });
    if (!result.ok) {
      sendJson(response, 400, { error: result.messages[0], messages: result.messages });
      return true;
    }
    sendJson(response, 200, { ok: true });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/login") {
    const body = await readBody(request);
    const identifier = String(body.identifier || "").trim();
    const password = String(body.password || "");
    const sessionId = randomUUID();
    const result = await transact((draft) => {
      const needle = identifier.toLowerCase();
      const user = draft.users.find((item) => item.username === identifier || item.email === needle);
      if (!user || !verifyPassword(password, user.password)) return null;
      draft.sessions.push({ id: sessionId, userId: user.id });
      return publicUser(user);
    });
    if (!result) {
      sendJson(response, 401, { error: "Invalid credentials" });
      return true;
    }
    sendJson(response, 200, { user: result }, {
      "set-cookie": `sid=${encodeURIComponent(sessionId)}; HttpOnly; Path=/; SameSite=Lax`,
    });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/logout") {
    const sid = cookieValue(request, "sid");
    await transact((draft) => {
      draft.sessions = draft.sessions.filter((item) => item.id !== sid);
    });
    sendJson(response, 200, { ok: true }, {
      "set-cookie": "sid=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax",
    });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/recover/start") {
    const body = await readBody(request);
    const email = String(body.email || "").trim();
    if (!emailOk(email)) {
      sendJson(response, 400, { error: "Email format is invalid", messages: ["Email format is invalid"] });
      return true;
    }
    sendJson(response, 200, { ok: true, code: "123456" });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/recover/finish") {
    const body = await readBody(request);
    const email = String(body.email || "").trim().toLowerCase();
    const code = String(body.code || "");
    const password = String(body.password || "");
    const confirm = String(body.confirm || "");
    if (code !== "123456") {
      sendJson(response, 400, { error: "Verification code is invalid" });
      return true;
    }
    if (!passwordOk(password) || password !== confirm) {
      sendJson(response, 400, { error: "Password requirements are not satisfied" });
      return true;
    }
    const updated = await transact((draft) => {
      const user = draft.users.find((item) => item.email === email);
      if (!user) return false;
      user.password = hashPassword(password);
      return true;
    });
    if (!updated) {
      sendJson(response, 400, { error: "Verification code is invalid" });
      return true;
    }
    sendJson(response, 200, { ok: true, message: "Password updated" });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/password") {
    const body = await readBody(request);
    const current = String(body.current || "");
    const password = String(body.password || "");
    const confirm = String(body.confirm || "");
    const updated = await transact((draft) => {
      const user = currentUser(draft, request);
      if (!user) return { status: 401, error: "Invalid credentials" };
      if (!current) return { status: 400, error: "Current password is required" };
      if (!verifyPassword(current, user.password)) return { status: 400, error: "Current password is incorrect" };
      if (password !== confirm) return { status: 400, error: "Password confirmation does not match" };
      if (!passwordOk(password)) return { status: 400, error: "Password requirements are not satisfied" };
      user.password = hashPassword(password);
      return { status: 200, message: "Password updated" };
    });
    sendJson(response, updated.status, updated.status === 200
      ? { ok: true, message: updated.message }
      : { error: updated.error });
    return true;
  }
  if (request.method === "GET" && url.pathname === "/api/orgs") {
    const state = await loadState();
    const user = currentUser(state, request);
    const organizations = (state.organizations || []).filter((org) => {
      if (!user) return true;
      return memberRole(state, org.name, user.username);
    });
    sendJson(response, 200, {
      organizations: organizations.map((org) => ({
        name: org.name,
        displayName: org.displayName,
        role: user ? memberRole(state, org.name, user.username) : "",
      })),
    });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/orgs") {
    const body = await readBody(request);
    const name = String(body.name || "").trim();
    const displayName = String(body.displayName || "").trim();
    const created = await transact((draft) => {
      const actor = currentUser(draft, request);
      if (!actor) return { status: 401, error: "Invalid credentials" };
      const messages = [];
      if ((draft.organizations || []).some((org) => org.name === name)) {
        messages.push("Organization name already exists");
      } else if (!usernameOk(name)) {
        messages.push("Organization name format is invalid");
      }
      if (!displayName || displayName.length > 100) messages.push("Display name is required");
      if (messages.length) return { status: 400, error: messages[0], messages };
      draft.organizations.push({ name, displayName, owner: actor.username });
      draft.members.push({ org: name, username: actor.username, role: "Owner" });
      return { status: 200, name };
    });
    sendJson(response, created.status, created.status === 200
      ? { ok: true, name: created.name }
      : { error: created.error, messages: created.messages || [created.error] });
    return true;
  }
  if (parts[0] === "api" && parts[1] === "orgs" && parts.length >= 4) {
    const name = decodeURIComponent(parts[2]);
    const section = decodeURIComponent(parts[3]);
    const teamName = parts[4] ? decodeURIComponent(parts[4]) : "";
    if (section === "teams" && request.method === "GET" && !teamName) {
      const state = await loadState();
      const org = (state.organizations || []).find((item) => item.name === name);
      if (!org) {
        sendJson(response, 404, { error: "Not found" });
        return true;
      }
      const user = currentUser(state, request);
      sendJson(response, 200, {
        organization: { ...org, role: user ? memberRole(state, name, user.username) : "" },
        teams: (state.teams || []).filter((item) => item.org === name),
      });
      return true;
    }
    if (section === "teams" && request.method === "POST" && !teamName) {
      const body = await readBody(request);
      const created = await transact((draft) => {
        const actor = currentUser(draft, request);
        if (!actor || memberRole(draft, name, actor.username) !== "Owner") {
          return { status: 403, error: "Access denied" };
        }
        const team = String(body.name || "").trim();
        const parent = String(body.parent || "").trim();
        if (!teamNameOk(team)) return { status: 400, error: "Team name format is invalid" };
        if ((draft.teams || []).some((item) => item.org === name && item.name === team)) {
          return { status: 400, error: "Team name already exists" };
        }
        if (parent && !(draft.teams || []).some((item) => item.org === name && item.name === parent)) {
          return { status: 400, error: "Parent team is invalid" };
        }
        draft.teams.push({ org: name, name: team, parent, description: String(body.description || "") });
        return { status: 200, name: team };
      });
      sendJson(response, created.status, created.status === 200 ? { ok: true, name: created.name } : { error: created.error });
      return true;
    }
    if (section === "teams" && teamName && request.method === "GET") {
      const state = await loadState();
      const org = (state.organizations || []).find((item) => item.name === name);
      const team = (state.teams || []).find((item) => item.org === name && item.name === teamName);
      if (!org || !team) {
        sendJson(response, 404, { error: "Not found" });
        return true;
      }
      const user = currentUser(state, request);
      sendJson(response, 200, {
        organization: { ...org, role: user ? memberRole(state, name, user.username) : "" },
        team,
        teams: (state.teams || []).filter((item) => item.org === name),
        members: (state.teamMembers || []).filter((item) => item.org === name && item.team === teamName),
      });
      return true;
    }
    if (section === "teams" && teamName && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const team = (draft.teams || []).find((item) => item.org === name && item.name === teamName);
        if (!actor || !team || memberRole(draft, name, actor.username) !== "Owner") {
          return { status: 403, error: "Access denied" };
        }
        if (body.action === "add-member") {
          const username = String(body.username || "").trim();
          if (memberRole(draft, name, username) === "") return { status: 400, error: "Account not found" };
          if (!onTeam(draft, name, teamName, username)) {
            draft.teamMembers.push({ org: name, team: teamName, username });
          }
          return { status: 200 };
        }
        if (body.action === "remove-member") {
          draft.teamMembers = (draft.teamMembers || []).filter((item) => !(item.org === name && item.team === teamName && item.username === body.username));
          return { status: 200 };
        }
        const parent = String(body.parent || "").trim();
        if (parent === teamName || teamDescendants(draft, name, teamName).includes(parent)) {
          return { status: 400, error: "Cyclic team hierarchy is not allowed" };
        }
        if (parent && !(draft.teams || []).some((item) => item.org === name && item.name === parent)) {
          return { status: 400, error: "Parent team is invalid" };
        }
        team.parent = parent;
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (section === "people" && request.method === "GET") {
      const state = await loadState();
      const org = (state.organizations || []).find((item) => item.name === name);
      if (!org) {
        sendJson(response, 404, { error: "Not found" });
        return true;
      }
      const user = currentUser(state, request);
      sendJson(response, 200, {
        organization: { ...org, role: user ? memberRole(state, name, user.username) : "" },
        members: (state.members || []).filter((item) => item.org === name),
      });
      return true;
    }
    if (section === "people" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        if (!actor || memberRole(draft, name, actor.username) !== "Owner") {
          return { status: 403, error: "Access denied" };
        }
        const query = String(body.username || "").trim();
        const account = draft.users.find((item) => item.username === query || item.email === query.toLowerCase());
        if (body.action === "remove") {
          const owners = (draft.members || []).filter((item) => item.org === name && item.role === "Owner");
          const target = (draft.members || []).find((item) => item.org === name && item.username === query);
          if (target && target.role === "Owner" && owners.length < 2) {
            return { status: 400, error: "Organization must keep an Owner" };
          }
          draft.members = (draft.members || []).filter((item) => !(item.org === name && item.username === query));
          draft.teamMembers = (draft.teamMembers || []).filter((item) => !(item.org === name && item.username === query));
          draft.grants = (draft.grants || []).filter((item) => !(item.subjectType === "user" && item.subject === query && item.organization === name));
          return { status: 200 };
        }
        if (!account) return { status: 400, error: "Account not found" };
        if (memberRole(draft, name, account.username)) return { status: 400, error: "Account is already a member" };
        const role = body.role === "Owner" ? "Owner" : "Member";
        draft.members.push({ org: name, username: account.username, role });
        return { status: 200, username: account.username, role };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true, username: updated.username, role: updated.role } : { error: updated.error });
      return true;
    }
    sendJson(response, 404, { error: "Not found" });
    return true;
  }
  if (request.method === "GET" && parts[0] === "api" && parts[1] === "orgs" && parts.length === 3) {
    const name = decodeURIComponent(parts[2]);
    const state = await loadState();
    const user = currentUser(state, request);
    const org = (state.organizations || []).find((item) => item.name === name);
    if (!org) {
      sendJson(response, 404, { error: "Not found" });
      return true;
    }
    const repositories = state.repositories.filter((item) => item.organization === name && canSeeRepo(state, item, user))
      .map((item) => ({
        owner: item.owner,
        name: item.name,
        description: item.description || "",
        visibility: item.visibility,
        updated: item.updated || "",
      }));
    const role = user ? memberRole(state, name, user.username) : "";
    sendJson(response, 200, { organization: { ...org, role }, repositories });
    return true;
  }
  if (request.method === "POST" && url.pathname === "/api/repos") {
    const body = await readBody(request);
    const created = await transact((draft) => {
      const actor = currentUser(draft, request);
      if (!actor) return { status: 401, error: "Invalid credentials" };
      const owner = String(body.owner || actor.username).trim();
      const name = String(body.name || "").trim();
      const messages = [];
      if (!name) messages.push("Repository name is required");
      else if (!usernameOk(name)) messages.push("Repository name format is invalid");
      const ownsNamespace = owner === actor.username || memberRole(draft, owner, actor.username) === "Owner";
      if (!ownsNamespace) messages.push("Repository creation is not permitted");
      if (!messages.length && draft.repositories.some((item) => item.owner === owner && item.name === name)) {
        messages.push("Repository name already exists");
      }
      if (messages.length) return { status: 400, error: messages[0], messages };
      const visibility = body.visibility === "private" ? "private" : "public";
      draft.repositories.push({
        owner,
        name,
        visibility,
        description: String(body.description || ""),
        defaultBranch: "main",
        organization: owner === actor.username ? "" : owner,
        updated: "just now",
      });
      if (body.readme === true) {
        draft.files.push({
          owner,
          repo: name,
          path: "README.md",
          branch: "main",
          content: `${name}\n`,
        });
        draft.commits.push({
          owner,
          repo: name,
          branch: "main",
          sha: randomUUID().slice(0, 7),
          parent: null,
          author: actor.username,
          message: "Initial commit",
          time: "just now",
          files: ["README.md"],
          additions: 1,
          deletions: 0,
          patches: { "README.md": [`+${name}`] },
        });
      }
      return { status: 200, owner, name };
    });
    sendJson(response, created.status, created.status === 200
      ? { ok: true, owner: created.owner, name: created.name }
      : { error: created.error, messages: created.messages || [created.error] });
    return true;
  }
  if (request.method === "GET" && url.pathname === "/api/search") {
    const query = url.searchParams.get("q") || "";
    const state = await loadState();
    const user = currentUser(state, request);
    const results = query
      ? state.repositories.filter((item) => item.name.includes(query) && canSeeRepo(state, item, user))
      : [];
    sendJson(response, 200, {
      results: results.map((item) => ({
        owner: item.owner,
        name: item.name,
        visibility: item.visibility,
        description: item.description || "",
        updated: item.updated || "",
      })),
    });
    return true;
  }
  const repoWrites = new Set(["fork", "file", "issue", "issue-state", "issue-edit", "issue-comment", "issue-react", "issue-meta", "access", "branch", "default-branch", "pull-state", "pull-create", "pull-line", "pull-review", "pull-reviewer", "pull-milestone", "pull-check", "visibility", "protection"]);
  if ((request.method === "GET" || (request.method === "POST" && repoWrites.has(parts[4])))
    && parts[0] === "api" && parts[1] === "repos" && parts.length >= 4) {
    const owner = decodeURIComponent(parts[2]);
    const repo = decodeURIComponent(parts[3]);
    const action = parts[4] || "";
    const state = await loadState();
    const user = currentUser(state, request);
    const stored = state.repositories.find((item) => item.owner === owner && item.name === repo);
    if (!stored) {
      sendJson(response, 404, { error: "Not found" });
      return true;
    }
    if (!canSeeRepo(state, stored, user)) {
      sendJson(response, 403, { error: "Access denied" });
      return true;
    }
    const record = stored;
    if (!action) {
      sendJson(response, 200, { ...repoView(state, record), canAdmin: canAdminRepo(state, record, user), isAdmin: isRepoAdmin(state, record, user), canManageIssues: canManageIssues(state, record, user), canWrite: canWriteRepo(state, record, user) });
      return true;
    }
    if (request.method === "POST" && action === "fork") {
      const body = await readBody(request);
      const forked = await transact((draft) => {
        const actor = currentUser(draft, request);
        const source = visibleRepo(draft, owner, repo, actor);
        if (!actor || !source) return { status: 404, error: "Not found" };
        const targetOwner = actor.username;
        const targetName = String(body.name || `${source.name}-fork`).trim();
        if (!usernameOk(targetName)) return { status: 400, error: "Repository name format is invalid" };
        if (draft.repositories.some((item) => item.owner === targetOwner && item.name === targetName)) {
          return { status: 400, error: "Repository name already exists" };
        }
        const visibility = source.visibility === "private" ? "private" : (body.visibility === "private" ? "private" : "public");
        draft.repositories.push({
          owner: targetOwner,
          name: targetName,
          visibility,
          description: source.description || "",
          defaultBranch: source.defaultBranch || "main",
          organization: "",
          updated: "just now",
          forkedFrom: { owner: source.owner, name: source.name },
        });
        for (const file of draft.files.filter((item) => item.owner === source.owner && item.repo === source.name)) {
          draft.files.push({ ...file, owner: targetOwner, repo: targetName });
        }
        for (const commit of (draft.commits || []).filter((item) => item.owner === source.owner && item.repo === source.name)) {
          draft.commits.push({ ...commit, owner: targetOwner, repo: targetName, sha: `f${commit.sha}` });
        }
        return { status: 200, owner: targetOwner, name: targetName };
      });
      sendJson(response, forked.status, forked.status === 200
        ? { ok: true, owner: forked.owner, name: forked.name }
        : { error: forked.error });
      return true;
    }
    if (action === "issues" && request.method === "GET") {
      const issues = (state.issues || []).filter((item) => item.owner === owner && item.repo === repo);
      sendJson(response, 200, { issues });
      return true;
    }
    if (action === "issue" && request.method === "GET") {
      const number = Number(parts[5] || 0);
      const issue = (state.issues || []).find((item) => item.owner === owner && item.repo === repo && item.number === number);
      if (!issue) {
        sendJson(response, 404, { error: "Not found" });
        return true;
      }
      sendJson(response, 200, {
        ...issue,
        candidates: eligibleAssignees(state, record),
        labelChoices: (state.labels || []).filter((item) => item.owner === owner && item.repo === repo).map((item) => item.name),
        milestoneChoices: (state.milestones || []).filter((item) => item.owner === owner && item.repo === repo).map((item) => item.name),
      });
      return true;
    }
    if (action === "issue" && request.method === "POST") {
      const body = await readBody(request);
      const created = await transact((draft) => {
        const actor = currentUser(draft, request);
        if (!actor) return { status: 401, error: "Invalid credentials" };
        const title = String(body.title || "").trim();
        if (!title) return { status: 400, error: "Title is required" };
        const numbers = (draft.issues || []).filter((item) => item.owner === owner && item.repo === repo).map((item) => item.number);
        const number = (numbers.length ? Math.max(...numbers) : 0) + 1;
        draft.issues.push({
          owner, repo, number, title, body: String(body.body || ""), state: "open", author: actor.username,
        });
        return { status: 200, number };
      });
      sendJson(response, created.status, created.status === 200 ? { ok: true, number: created.number } : { error: created.error });
      return true;
    }
    if (action === "issue-state" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const issue = (draft.issues || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !issue) return { status: 404, error: "Not found" };
        if (!canManageIssues(draft, record, actor)) return { status: 403, error: "Access denied" };
        issue.state = body.state === "closed" ? "closed" : "open";
        issue.activity = issue.activity || [];
        issue.activity.push(issue.state === "closed" ? "Closed issue" : "Reopened");
        return { status: 200, state: issue.state };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true, state: updated.state } : { error: updated.error });
      return true;
    }
    if (action === "issue-edit" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const issue = (draft.issues || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !issue) return { status: 401, error: "Invalid credentials" };
        if (!canWriteRepo(draft, record, actor)) return { status: 403, error: "Access denied" };
        if (body.field === "title") {
          const title = String(body.value || "").trim();
          if (!title) return { status: 400, error: "Title is required" };
          if (title.length > 256) return { status: 400, error: "Title is too long" };
          issue.title = title;
        } else {
          issue.body = String(body.value || "");
        }
        issue.activity = issue.activity || [];
        issue.activity.push(body.field === "title" ? "Edited the issue title" : "Edited the issue description");
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "issue-comment" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const issue = (draft.issues || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !issue) return { status: 401, error: "Invalid credentials" };
        if (!canWriteRepo(draft, record, actor)) return { status: 403, error: "Access denied" };
        const text = String(body.body || "").trim();
        if (!text) return { status: 400, error: "Comment is required" };
        if (text.length > 65536) return { status: 400, error: "Comment is too long" };
        issue.comments = issue.comments || [];
        issue.comments.push({ author: actor.username, body: text, time: "just now", reactions: [] });
        issue.activity = issue.activity || [];
        issue.activity.push("Commented");
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "issue-react" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const issue = (draft.issues || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !issue) return { status: 401, error: "Invalid credentials" };
        const index = Number(body.index || 0);
        const comment = (issue.comments || [])[index];
        if (!comment) return { status: 404, error: "Not found" };
        const kind = String(body.reaction || "+1");
        comment.reactions = comment.reactions || [];
        const existing = comment.reactions.findIndex((item) => item.user === actor.username && item.type === kind);
        if (existing >= 0) comment.reactions.splice(existing, 1);
        else comment.reactions.push({ user: actor.username, type: kind });
        return { status: 200, count: comment.reactions.filter((item) => item.type === kind).length };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true, count: updated.count } : { error: updated.error });
      return true;
    }
    if (action === "issue-meta" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const issue = (draft.issues || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !issue) return { status: 401, error: "Invalid credentials" };
        const value = String(body.value || "");
        if (body.kind === "assign") {
          if (!canManageIssues(draft, record, actor)) return { status: 403, error: "Access denied" };
          issue.assignees = issue.assignees || [];
          if (!issue.assignees.includes(value) && !eligibleAssignees(draft, record).includes(value)) {
            return { status: 400, error: "Assignee is not eligible" };
          }
          const removing = issue.assignees.includes(value);
          issue.assignees = removing ? issue.assignees.filter((item) => item !== value) : issue.assignees.concat(value);
          issue.activity = issue.activity || [];
          issue.activity.push(removing ? `Unassigned ${value}` : `Assigned ${value}`);
        } else if (body.kind === "label") {
          if (!canManageIssues(draft, record, actor)) return { status: 403, error: "Access denied" };
          issue.labels = issue.labels || [];
          const known = (draft.labels || []).some((item) => item.owner === owner && item.repo === repo && item.name === value);
          if (!issue.labels.includes(value) && !known) return { status: 400, error: "Label is not available" };
          const removing = issue.labels.includes(value);
          issue.labels = removing ? issue.labels.filter((item) => item !== value) : issue.labels.concat(value);
          issue.activity = issue.activity || [];
          issue.activity.push(removing ? `Removed label ${value}` : `Added label ${value}`);
        } else {
          if (!canManageIssues(draft, record, actor)) return { status: 403, error: "Access denied" };
          if (value !== "None" && !(draft.milestones || []).some((item) => item.owner === owner && item.repo === repo && item.name === value)) {
            return { status: 400, error: "Milestone is not available" };
          }
          issue.milestone = value === "None" ? "" : value;
          issue.activity = issue.activity || [];
          issue.activity.push(value === "None" ? "Cleared the milestone" : `Milestone ${value}`);
        }
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "pulls" && request.method === "GET") {
      sendJson(response, 200, { pulls: (state.pulls || []).filter((item) => item.owner === owner && item.repo === repo) });
      return true;
    }
    if (action === "pull" && request.method === "GET") {
      const number = Number(parts[5] || 0);
      const pull = (state.pulls || []).find((item) => item.owner === owner && item.repo === repo && item.number === number);
      const protection = pull && (state.protections || []).find((item) => item.owner === owner && item.repo === repo && item.branch === pull.base);
      const viewer = currentUser(state, request);
      const visible = pull ? {
        ...pull,
        protection: protection || null,
        draftComments: (pull.draftComments || []).filter((item) => viewer && item.author === viewer.username),
        canManagePull: canManagePull(state, record, pull, viewer),
        reviewerCandidates: eligibleReviewers(state, record, pull),
        milestone: pull.milestone || "",
        milestoneChoices: (state.milestones || []).filter((item) => item.owner === owner && item.repo === repo).map((item) => item.name),
      } : { error: "Not found" };
      sendJson(response, pull ? 200 : 404, visible);
      return true;
    }
    if (action === "pull-state" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const pull = (draft.pulls || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !pull) return { status: 404, error: "Not found" };
        const allowed = canManagePull(draft, record, pull, actor);
        if (body.action === "ready") {
          if (!allowed || pull.state !== "draft") return { status: 403, error: "Access denied" };
          pull.state = "open";
          pull.activity = pull.activity || [];
          pull.activity.push("Ready for review");
          return { status: 200, state: pull.state };
        }
        if (body.action === "merge") {
          if (!canAdminRepo(draft, record, actor) || pull.state !== "open") return { status: 403, error: "Access denied" };
          const rule = (draft.protections || []).find((item) => item.owner === owner && item.repo === repo && item.branch === pull.base);
          const latestReview = new Map();
          (pull.reviews || []).forEach((review) => latestReview.set(review.reviewer, review.decision));
          const changesRequested = [...latestReview.values()].includes("Request changes");
          if (changesRequested || (rule && rule.review && !pull.approved)) {
            return { status: 400, error: "Review required by branch protection" };
          }
          if (rule && rule.check && pull.check !== "success") {
            return { status: 400, error: "required check `test` is success" };
          }
          const heads = (draft.commits || []).filter((item) => item.owner === owner && item.repo === repo && item.branch === pull.base);
          const parent = heads.length ? heads[heads.length - 1].sha : null;
          const sha = `m${pull.number}ce${(draft.commits || []).length}`;
          draft.commits = draft.commits || [];
          draft.commits.push({
            owner, repo, branch: pull.base, sha, parent, author: actor.username,
            message: `Merge pull request #${pull.number}`, time: "just now",
            files: pull.changedFiles || [], additions: pull.additions || 0, deletions: pull.deletions || 0, patches: {},
          });
          pull.state = "merged";
          pull.mergedBy = actor.username;
          pull.mergedAt = "just now";
          pull.mergeSha = sha;
          return { status: 200, state: pull.state };
        }
        if (pull.state === "merged" || !allowed) return { status: 403, error: "Access denied" };
        pull.activity = pull.activity || [];
        if (body.state === "closed") {
          if (pull.state !== "open" && pull.state !== "draft") return { status: 400, error: "Access denied" };
          pull.state = "closed";
          pull.closedBy = actor.username;
          pull.closedAt = "just now";
          pull.activity.push("Closed pull request");
        } else {
          if (pull.state !== "closed") return { status: 400, error: "Access denied" };
          pull.state = "open";
          pull.activity.push("Reopened pull request");
        }
        return { status: 200, state: pull.state };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true, state: updated.state } : { error: updated.error });
      return true;
    }
    if (action === "pull-create" && request.method === "POST") {
      const body = await readBody(request);
      const created = await transact((draft) => {
        const actor = currentUser(draft, request);
        if (!actor) return { status: 401, error: "Invalid credentials" };
        const title = String(body.title || "").trim();
        if (!title) return { status: 400, error: "Title is required" };
        const numbers = (draft.pulls || []).filter((item) => item.owner === owner && item.repo === repo).map((item) => item.number);
        const number = (numbers.length ? Math.max(...numbers) : 0) + 1;
        draft.pulls.push({
          owner, repo, number, title, body: String(body.body || ""),
          state: body.draft ? "draft" : "open", author: actor.username,
          head: String(body.head || "feature-search"), base: String(body.base || "main"),
          approved: false, check: "pending", reviewers: [], reviews: [], activity: [],
          changedFiles: ["src/search.ts"], additions: 1, deletions: 0, line: "+export const created = true;",
        });
        return { status: 200, number };
      });
      sendJson(response, created.status, created.status === 200 ? { ok: true, number: created.number } : { error: created.error });
      return true;
    }
    if (action === "pull-line" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const pull = (draft.pulls || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !pull || !canWriteRepo(draft, record, actor) || actor.username === pull.author || pull.state !== "open") {
          return { status: 403, error: "Access denied" };
        }
        const text = String(body.body || "").trim();
        if (!text) return { status: 400, error: "Comment is required" };
        const entry = { author: actor.username, body: text, path: pull.changedFiles && pull.changedFiles[0] || "src/search.ts", line: pull.line || "" };
        if (body.pending) {
          pull.draftComments = pull.draftComments || [];
          pull.draftComments.push(entry);
        } else {
          pull.lineComments = pull.lineComments || [];
          pull.lineComments.push(entry);
        }
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "pull-review" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const pull = (draft.pulls || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !pull || !canWriteRepo(draft, record, actor) || actor.username === pull.author || pull.state !== "open") {
          return { status: 403, error: "Access denied" };
        }
        const decision = String(body.decision || "Comment");
        pull.reviews = pull.reviews || [];
        pull.reviews.push({ reviewer: actor.username, decision, summary: String(body.summary || ""), at: "just now" });
        const mine = pull.draftComments || [];
        if (mine.length) {
          pull.lineComments = pull.lineComments || [];
          pull.lineComments.push(...mine.filter((item) => item.author === actor.username));
          pull.draftComments = mine.filter((item) => item.author !== actor.username);
        }
        const latest = new Map();
        pull.reviews.forEach((review) => latest.set(review.reviewer, review.decision));
        pull.approved = [...latest.values()].includes("Approve") && ![...latest.values()].includes("Request changes");
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "pull-milestone" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const pull = (draft.pulls || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !pull) return { status: 404, error: "Not found" };
        if (!canManageIssues(draft, record, actor)) return { status: 403, error: "Access denied" };
        const value = String(body.value || "");
        if (value !== "None" && !(draft.milestones || []).some((item) => item.owner === owner && item.repo === repo && item.name === value)) {
          return { status: 400, error: "Milestone is not available" };
        }
        pull.milestone = value === "None" ? "" : value;
        pull.activity = pull.activity || [];
        pull.activity.push(value === "None" ? "Cleared the milestone" : `Milestone ${value}`);
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "pull-reviewer" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const pull = (draft.pulls || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !pull) return { status: 404, error: "Not found" };
        const allowed = actor.username === pull.author || canAdminRepo(draft, record, actor);
        if (!allowed || (pull.state !== "open" && pull.state !== "draft")) return { status: 403, error: "Access denied" };
        const username = String(body.username || "");
        if (!body.remove && (username === pull.author || !canWriteRepo(draft, record, { username }))) {
          return { status: 400, error: "Reviewer is not eligible" };
        }
        pull.reviewers = pull.reviewers || [];
        pull.reviewers = body.remove ? pull.reviewers.filter((item) => item !== username) : pull.reviewers.concat(pull.reviewers.includes(username) ? [] : [username]);
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "visibility" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const source = draft.repositories.find((item) => item.owner === owner && item.name === repo);
        if (!actor || !source || !canAdminRepo(draft, source, actor)) return { status: 403, error: "Access denied" };
        source.visibility = body.visibility === "private" ? "private" : "public";
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "pull-check" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const source = draft.repositories.find((item) => item.owner === owner && item.name === repo);
        const pull = (draft.pulls || []).find((item) => item.owner === owner && item.repo === repo && item.number === Number(body.number));
        if (!actor || !source || !pull || !isRepoAdmin(draft, source, actor)) return { status: 403, error: "Access denied" };
        const status = String(body.status || "pending");
        pull.check = status === "success" || status === "failure" ? status : "pending";
        pull.checkBy = actor.username;
        pull.checkAt = "just now";
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "protection" && request.method === "GET") {
      const rule = (state.protections || []).find((item) => item.owner === owner && item.repo === repo);
      sendJson(response, 200, rule || { review: false, check: false });
      return true;
    }
    if (action === "protection" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const source = draft.repositories.find((item) => item.owner === owner && item.name === repo);
        if (!actor || !source || !isRepoAdmin(draft, source, actor)) return { status: 403, error: "Access denied" };
        const branch = String(body.branch || "main").trim() || "main";
        let rule = (draft.protections || []).find((item) => item.owner === owner && item.repo === repo && item.branch === branch);
        if (!rule) {
          rule = { owner, repo, branch, review: false, check: false };
          draft.protections.push(rule);
        }
        rule.review = Boolean(body.review);
        rule.check = Boolean(body.check);
        return { status: 200, rule };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "access" && request.method === "GET") {
      const grants = (state.grants || []).filter((item) => item.owner === owner && item.repo === repo);
      const teams = (state.teams || []).filter((item) => item.org === record.organization);
      const members = (state.members || []).filter((item) => item.org === record.organization);
      sendJson(response, 200, { grants, teams, members });
      return true;
    }
    if (action === "access" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        if (!actor || (memberRole(draft, record.organization, actor.username) !== "Owner" && actor.username !== record.owner)) {
          return { status: 403, error: "Access denied" };
        }
        const subject = String(body.subject || "").trim();
        const subjectType = body.subjectType === "user" ? "user" : "team";
        const role = String(body.role || "Write");
        let grant = (draft.grants || []).find((item) => item.owner === owner && item.repo === repo
          && item.subjectType === subjectType && item.subject === subject);
        if (!grant) {
          grant = { owner, repo, organization: record.organization, subjectType, subject, role };
          draft.grants.push(grant);
        } else {
          grant.role = role;
        }
        return { status: 200 };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true } : { error: updated.error });
      return true;
    }
    if (action === "branch" && request.method === "POST") {
      const body = await readBody(request);
      const created = await transact((draft) => {
        const actor = currentUser(draft, request);
        const source = draft.repositories.find((item) => item.owner === owner && item.name === repo);
        if (!actor || !source || !canWriteRepo(draft, source, actor)) return { status: 403, error: "Access denied" };
        const branchName = String(body.name || "").trim();
        if (!branchNameOk(branchName)) return { status: 400, error: "Invalid branch" };
        const existing = new Set(draft.files.filter((item) => item.owner === owner && item.repo === repo)
          .map((item) => item.branch || source.defaultBranch));
        if (existing.has(branchName) || branchName === source.defaultBranch) return { status: 400, error: "Invalid branch" };
        const base = String(body.base || source.defaultBranch);
        for (const file of draft.files.filter((item) => item.owner === owner && item.repo === repo && (item.branch || source.defaultBranch) === base)) {
          draft.files.push({ ...file, branch: branchName });
        }
        return { status: 200, name: branchName };
      });
      sendJson(response, created.status, created.status === 200 ? { ok: true, name: created.name } : { error: created.error });
      return true;
    }
    if (action === "default-branch" && request.method === "POST") {
      const body = await readBody(request);
      const updated = await transact((draft) => {
        const actor = currentUser(draft, request);
        const source = draft.repositories.find((item) => item.owner === owner && item.name === repo);
        if (!actor || !source) return { status: 403, error: "Access denied" };
        if (memberRole(draft, source.organization, actor.username) !== "Owner" && actor.username !== source.owner) {
          return { status: 403, error: "Access denied" };
        }
        source.defaultBranch = String(body.branch || source.defaultBranch);
        return { status: 200, branch: source.defaultBranch };
      });
      sendJson(response, updated.status, updated.status === 200 ? { ok: true, branch: updated.branch } : { error: updated.error });
      return true;
    }
    if (action === "file" && request.method === "POST") {
      const body = await readBody(request);
      const saved = await transact((draft) => {
        const actor = currentUser(draft, request);
        const source = draft.repositories.find((item) => item.owner === owner && item.name === repo);
        if (!actor || !source || !canWriteRepo(draft, source, actor)) return { status: 403, error: "Access denied" };
        const filePath = String(body.path || "").trim();
        const message = String(body.message || "").trim();
        if (!filePath || filePath.startsWith("/") || filePath.includes("..")) return { status: 400, error: "Invalid file path" };
        if (!message || message.length > 72) return { status: 400, error: "Commit message is required" };
        const branchName = String(body.branch || source.defaultBranch);
        const protectedBranch = (draft.protections || []).some((item) => item.owner === owner && item.repo === repo && item.branch === branchName);
        if (protectedBranch) return { status: 400, error: "Branch is protected" };
        const onBranch = (item) => item.owner === owner && item.repo === repo && (item.branch || source.defaultBranch) === branchName;
        const replacing = Boolean(body.replace);
        if (!replacing) {
          const conflict = (draft.files || []).some((item) => onBranch(item) && (
            item.path === filePath || item.path.startsWith(`${filePath}/`) || filePath.startsWith(`${item.path}/`)
          ));
          if (conflict) return { status: 400, error: "A file already exists at this path" };
        }
        const prior = draft.commits.filter((item) => item.owner === owner && item.repo === repo && item.branch === branchName);
        const parent = prior.length ? prior[prior.length - 1].sha : null;
        const existing = draft.files.find((item) => item.owner === owner && item.repo === repo && item.path === filePath
          && (item.branch || source.defaultBranch) === branchName);
        if (existing) existing.content = String(body.content || "");
        else draft.files.push({ owner, repo, path: filePath, branch: branchName, content: String(body.content || "") });
        const sha = randomUUID().slice(0, 7);
        draft.commits.push({
          owner, repo, branch: branchName, sha, parent, author: actor.username,
          message, time: "just now", files: [filePath], additions: 1, deletions: 0,
          patches: { [filePath]: [`+${String(body.content || "").split("\n")[0] || ""}`] },
        });
        for (const pull of draft.pulls || []) {
          if (pull.owner === owner && pull.repo === repo && pull.head === branchName && pull.state === "open") {
            pull.approved = false;
            pull.check = "pending";
          }
        }
        return { status: 200, path: filePath, parent };
      });
      sendJson(response, saved.status, saved.status === 200 ? { ok: true, path: saved.path } : { error: saved.error });
      return true;
    }
    const branch = url.searchParams.get("branch") || record.defaultBranch;
    const files = state.files.filter((item) => item.owner === owner && item.repo === repo
      && (item.branch || record.defaultBranch) === branch);
    if (action === "files") {
      const query = url.searchParams.get("q") || "";
      const pathPrefix = url.searchParams.get("path") || "";
      const language = String(url.searchParams.get("language") || "").trim().toLowerCase();
      let matched = files;
      if (pathPrefix) {
        const prefix = pathPrefix.endsWith("/") ? pathPrefix : `${pathPrefix}/`;
        matched = matched.filter((item) => item.path === pathPrefix || item.path.startsWith(prefix));
      }
      if (query) {
        matched = matched.filter((item) => item.path.includes(query) || item.content.includes(query));
      }
      if (language) {
        const suffixes = {
          markdown: [".md"],
          typescript: [".ts", ".tsx"],
          javascript: [".js", ".mjs"],
          text: [".txt"],
        }[language] || ["." + language.replace(/^\./, "")];
        matched = matched.filter((item) => suffixes.some((suffix) => item.path.toLowerCase().endsWith(suffix)));
      }
      sendJson(response, 200, {
        branch,
        branches: [...new Set(state.files.filter((item) => item.owner === owner && item.repo === repo)
          .map((item) => item.branch || record.defaultBranch))],
        files: matched.map((item) => ({
          path: item.path,
          branch: item.branch || record.defaultBranch,
          snippet: snippet(item.content, query),
        })),
      });
      return true;
    }
    if (action === "commits") {
      const filePath = url.searchParams.get("path") || "";
      const commits = (state.commits || []).filter((item) => item.owner === owner && item.repo === repo
        && item.branch === branch && (!filePath || item.files.includes(filePath)));
      sendJson(response, 200, { branch, commits: commits.slice().reverse() });
      return true;
    }
    if (action === "commit") {
      const sha = decodeURIComponent(parts[5] || "");
      const commit = (state.commits || []).find((item) => item.owner === owner && item.repo === repo && item.sha === sha);
      if (!commit) {
        sendJson(response, 404, { error: "Not found" });
        return true;
      }
      sendJson(response, 200, commit);
      return true;
    }
    if (action === "blob") {
      const filePath = url.searchParams.get("path") || "";
      const file = files.find((item) => item.path === filePath);
      if (!file) {
        sendJson(response, 404, { error: "Not found" });
        return true;
      }
      sendJson(response, 200, file);
      return true;
    }
  }
  if (parts[0] === "api") {
    sendJson(response, 404, { error: "Not found" });
    return true;
  }
  return false;
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", "http://localhost");
    if (await handleApi(request, response, url)) return;
    const requested = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
    const candidate = path.resolve(publicDir, requested);
    const safePath = candidate.startsWith(publicDir + path.sep) ? candidate : path.join(publicDir, "index.html");
    let filePath = safePath;
    let body;
    try {
      body = await readFile(filePath);
    } catch {
      filePath = path.join(publicDir, "index.html");
      body = await readFile(filePath);
    }
    response.writeHead(200, { "content-type": types[path.extname(filePath)] || "application/octet-stream" });
    response.end(body);
  } catch (error) {
    const status = error && error.status ? error.status : 500;
    if (!response.headersSent) {
      sendJson(response, status, { error: String(error.message || error) });
    }
  }
});

await mkdir(path.dirname(dataPath), { recursive: true });
try {
  const existing = JSON.parse(await readFile(dataPath, "utf8"));
  if (!existing.users) await saveState(seedState());
} catch (error) {
  if (!error || error.code !== "ENOENT") throw error;
  await saveState(seedState());
}
server.listen(port, host);
