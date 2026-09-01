import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  appendAuditEvent,
  auditCsv,
  evaluateDirectBranchWritePolicy,
  executeEnterpriseCommand,
  normalizeEnterpriseState,
  shouldAuditCommand,
  verifyEnterpriseState,
} from "./enterprise.mjs";
import {
  SessionStore,
  bearerToken,
  hashPassword,
  normalizeEmail,
  publicAccount,
  validateEmail,
  validatePassword,
  validateUsername,
  verifyPassword,
} from "./auth.mjs";
import {
  authorizeGenericCommand,
  canViewRepository,
  isOrganizationOwner,
} from "./authorization.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../frontend/dist");
const dataDir = path.join(here, "data");
const statePath = path.join(dataDir, "github-state.json");
const port = Number.parseInt(process.env.PORT || "3000", 10);
const host = process.env.HOST || "0.0.0.0";
const accountPrefixes = [
  "E2E_LOGIN",
  "E2E_LOGIN_EMAIL",
  "E2E_SIGN_OUT",
  "E2E_PASSWORD_CHANGE",
  "E2E_PASSWORD_CHANGE_REQUIRED",
  "E2E_ORGANIZATION_OWNER",
  "E2E_TEAM_MAINTAINER",
  "E2E_ORGANIZATION_EXISTING_MEMBER",
  "E2E_ORGANIZATION_NEW_MEMBER",
  "E2E_ORGANIZATION_NON_OWNER",
  "E2E_REPOSITORY_ADMIN",
  "E2E_REPOSITORY_OWNER",
  "E2E_FORK_USER",
  "E2E_NON_ADMIN_COLLABORATOR",
  "E2E_VISIBILITY_ADMIN",
  "E2E_BRANCH_CONTRIBUTOR",
  "E2E_DEFAULT_BRANCH_ADMIN",
  "E2E_DEFAULT_BRANCH_NON_ADMIN",
  "E2E_FILE_CONTRIBUTOR",
  "E2E_ISSUE_AUTHOR",
  "E2E_ISSUE_EDITOR",
  "E2E_ISSUE_COMMENTER",
  "E2E_ISSUE_VIEWER",
  "E2E_PROTECTION_ADMIN",
  "E2E_PROTECTION_NON_ADMIN",
  "E2E_PR_CONTRIBUTOR",
  "E2E_DRAFT_PR_AUTHOR",
  "E2E_PR_REVIEWER",
  "E2E_PR_AUTHOR",
  "E2E_PR_MAINTAINER",
  "E2E_PR_VIEWER",
];

function env(name, fallback) {
  return String(process.env[name] || fallback);
}

function fixtureAccount(prefix, index) {
  const username = env(`${prefix}_USERNAME`, `fixture-user-${String(index + 1).padStart(2, "0")}`);
  return {
    id: username,
    username,
    email: env(`${prefix}_EMAIL`, `${username}@example.test`),
    passwordHash: hashPassword(env(`${prefix}_PASSWORD`, "Fixture-password-123!")),
    emailVerified: true,
    credentialStatus: "active",
  };
}

function repository(owner, name, extra = {}) {
  return {
    id: `${owner}/${name}`,
    owner,
    name,
    visibility: "public",
    description: `${name} collaboration repository`,
    defaultBranch: "main",
    branches: [
      {
        name: "main",
        files: {
          "README.md": `# ${name}\n`,
          "src/index.js": "export const answer = 42;",
        },
      },
    ],
    commits: [
      {
        id: "seed-commit",
        message: env("E2E_COMMIT_MESSAGE", "Seed the verified code fixture"),
        author: env("E2E_COMMIT_AUTHOR", "fixture-author"),
        changedFiles: [env("E2E_CHANGED_FILE", "src/index.js")],
      },
    ],
    accesses: [],
    protections: [],
    labels: [env("E2E_ISSUE_LABEL", "priority:high"), "bug", "enhancement"],
    milestones: [env("E2E_ISSUE_MILESTONE", "Qualifier")],
    forkedFrom: null,
    ...extra,
  };
}

function issue(number, title, extra = {}) {
  return {
    id: `acme/issues-repo#${number}`,
    repoId: "acme/issues-repo",
    number,
    title,
    description: `Fixture issue ${number}`,
    state: "open",
    author: "fixture-issue-author",
    editable: true,
    assignees: [],
    labels: [],
    milestone: "",
    comments: [],
    ...extra,
  };
}

function pullRequest(number, title, extra = {}) {
  return {
    id: `acme/pr-repo#${number}`,
    repoId: "acme/pr-repo",
    number,
    title,
    description: `Fixture pull request ${number}`,
    state: "open",
    draft: false,
    base: "main",
    head: "feature",
    author: "fixture-pr-author",
    mergeable: true,
    files: [env("E2E_PR_CHANGED_FILE", "src/feature.js")],
    commits: ["Implement fixture feature"],
    reviewers: [],
    reviewComments: [],
    reviews: [],
    checks: { test: "pending" },
    checkUpdatedBy: "",
    readyEvent: false,
    ...extra,
  };
}

function seededState() {
  const accounts = accountPrefixes.map(fixtureAccount);
  for (const username of [
    env("E2E_TEAM_CANDIDATE_USERNAME", "team-candidate"),
    env("E2E_ORGANIZATION_MEMBER_TO_REMOVE", "member-to-remove"),
    env("E2E_ISSUE_ASSIGNEE", "issue-assignee"),
    env("E2E_REQUESTED_REVIEWER", "requested-reviewer"),
  ]) {
    accounts.push({
      id: username,
      username,
      email: `${username}@example.test`,
      passwordHash: hashPassword("Fixture-password-123!"),
      emailVerified: true,
      credentialStatus: "active",
    });
  }

  const organizationOwner = env("E2E_ORGANIZATION_OWNER_USERNAME", accounts[5].username);
  const existingMember = env(
    "E2E_ORGANIZATION_EXISTING_MEMBER_USERNAME",
    accounts[7].username,
  );
  const nonOwner = env("E2E_ORGANIZATION_NON_OWNER_USERNAME", "fixture-user-10");
  const memberToRemove = env("E2E_ORGANIZATION_MEMBER_TO_REMOVE", "removable-user");

  const organizations = [
    {
      id: "open-labs",
      name: "open-labs",
      displayName: "Open Labs",
      owner: "public-owner",
      members: [],
    },
    {
      id: "acme",
      name: "acme",
      displayName: "Acme Engineering",
      owner: organizationOwner,
      members: [
        { username: organizationOwner, role: "Owner" },
        { username: existingMember, role: "Member" },
        { username: nonOwner, role: "Member" },
        { username: memberToRemove, role: "Member" },
      ],
    },
    {
      id: "existing-org",
      name: env("E2E_EXISTING_ORGANIZATION", "existing-org"),
      displayName: "Existing Organization",
      owner: organizationOwner,
      members: [{ username: organizationOwner, role: "Owner" }],
    },
  ];

  const teams = [
    {
      id: "acme/platform-team",
      organization: "acme",
      name: env("E2E_ACCESS_TEAM_NAME", "platform-team"),
      parent: "",
      members: [],
      maintainers: [env("E2E_TEAM_MAINTAINER_USERNAME", accounts[6].username)],
    },
    {
      id: "acme/security-team",
      organization: "acme",
      name: env("E2E_ACCESS_ROLE_CHANGE_TEAM_NAME", "security-team"),
      parent: "",
      members: [],
      maintainers: [],
    },
    { id: "acme/root-team", organization: "acme", name: "root-team", parent: "", members: [], maintainers: [] },
    {
      id: "acme/parent-team",
      organization: "acme",
      name: "parent-team",
      parent: env("E2E_CYCLIC_TEAM_ORIGINAL_PARENT", "root-team"),
      members: [],
      maintainers: [],
    },
    {
      id: "acme/child-team",
      organization: "acme",
      name: env("E2E_CYCLIC_TEAM_DESCENDANT", "child-team"),
      parent: "parent-team",
      members: [],
      maintainers: [],
    },
  ];

  const repositories = [
    repository("open-labs", env("E2E_PUBLIC_REPOSITORY_NAME", "roadmap-app")),
    repository("open-labs", env("E2E_PRIVATE_REPOSITORY_NAME", "private-ledger"), { visibility: "private" }),
    repository("open-labs", env("E2E_FORK_SOURCE_REPOSITORY_NAME", "fork-source")),
    repository("open-labs", "code-repo"),
    repository("acme", "managed-repo", {
      administrators: [env("E2E_REPOSITORY_ADMIN_USERNAME", "fixture-user-11")],
    }),
    repository("acme", "private-repo", { visibility: "private" }),
    repository("acme", "access-repo", {
      administrators: [env("E2E_REPOSITORY_ADMIN_USERNAME", "fixture-user-11")],
      accesses: [{ subject: env("E2E_ACCESS_ROLE_CHANGE_TEAM_NAME", "security-team"), role: "write" }],
    }),
    repository("acme", env("E2E_VISIBILITY_REPOSITORY_NAME", "visibility-repo"), {
      visibility: "private",
      accesses: [
        { subject: env("E2E_VISIBILITY_ADMIN_USERNAME", "fixture-user-15"), role: "admin" },
        { subject: env("E2E_NON_ADMIN_COLLABORATOR_USERNAME", "fixture-user-14"), role: "write" },
      ],
    }),
    repository("acme", "branch-repo", {
      accesses: [{ subject: env("E2E_BRANCH_CONTRIBUTOR_USERNAME", "fixture-user-16"), role: "write" }],
      branches: [
        { name: "main", files: { "README.md": "# branch-repo\n" } },
        { name: env("E2E_TARGET_BRANCH", "feature"), files: { [env("E2E_TARGET_BRANCH_FILE", "feature.txt")]: "feature branch" } },
      ],
    }),
    repository("acme", "default-repo", {
      accesses: [
        { subject: env("E2E_DEFAULT_BRANCH_ADMIN_USERNAME", "fixture-user-17"), role: "admin" },
        { subject: env("E2E_DEFAULT_BRANCH_NON_ADMIN_USERNAME", "fixture-user-18"), role: "write" },
      ],
      branches: [
        { name: env("E2E_OLD_DEFAULT_BRANCH", "main"), files: { "README.md": "main" } },
        { name: env("E2E_NEW_DEFAULT_BRANCH", "develop"), files: { "README.md": "develop" } },
      ],
    }),
    repository("acme", "file-repo", {
      accesses: [{ subject: env("E2E_FILE_CONTRIBUTOR_USERNAME", "fixture-user-19"), role: "write" }],
    }),
    repository("acme", "issues-repo", {
      accesses: [
        { subject: env("E2E_ISSUE_AUTHOR_USERNAME", "fixture-user-20"), role: "write" },
        { subject: env("E2E_ISSUE_EDITOR_USERNAME", "fixture-user-21"), role: "write" },
        { subject: env("E2E_ISSUE_COMMENTER_USERNAME", "fixture-user-22"), role: "write" },
        { subject: env("E2E_ISSUE_VIEWER_USERNAME", "fixture-user-23"), role: "read" },
      ],
    }),
    repository("acme", "protection-repo", {
      accesses: [
        { subject: env("E2E_PROTECTION_ADMIN_USERNAME", "fixture-user-24"), role: "admin" },
        { subject: env("E2E_PROTECTION_NON_ADMIN_USERNAME", "fixture-user-25"), role: "write" },
      ],
    }),
    repository("acme", "pr-repo", {
      accesses: [
        { subject: env("E2E_PR_CONTRIBUTOR_USERNAME", "fixture-user-26"), role: "write" },
        { subject: env("E2E_DRAFT_PR_AUTHOR_USERNAME", "fixture-user-27"), role: "write" },
        { subject: env("E2E_PR_REVIEWER_USERNAME", "fixture-user-28"), role: "write" },
        { subject: env("E2E_PR_AUTHOR_USERNAME", "fixture-user-29"), role: "write" },
        { subject: env("E2E_PR_MAINTAINER_USERNAME", "fixture-user-30"), role: "admin" },
        { subject: env("E2E_PR_VIEWER_USERNAME", "fixture-user-31"), role: "read" },
      ],
      branches: [
        { name: "main", files: { "README.md": "main" } },
        { name: "feature", files: { "src/feature.js": "export const feature = true;" } },
        { name: env("E2E_DRAFT_PULL_REQUEST_SOURCE_BRANCH", "review-feature"), files: { "src/wip.js": "export const workInProgress = true;" } },
      ],
    }),
    repository(
      env("E2E_REPOSITORY_OWNER_USERNAME", "fixture-user-12"),
      env("E2E_EXISTING_OWNED_REPOSITORY", "existing-repo"),
      { visibility: "private" },
    ),
    repository(
      env("E2E_FORK_USER_USERNAME", "fixture-user-13"),
      env("E2E_EXISTING_FORK_NAME", "existing-fork"),
      { visibility: "private", forkedFrom: `open-labs/${env("E2E_FORK_SOURCE_REPOSITORY_NAME", "fork-source")}` },
    ),
  ];

  const issues = [
    issue(1, env("E2E_ISSUE_TITLE", "Fixture issue detail"), {
      description: env("E2E_ISSUE_DESCRIPTION", "A durable issue description for browser acceptance."),
    }),
    issue(2, "Editable fixture issue"),
    issue(3, env("E2E_INVALID_EDIT_ISSUE_TITLE", "Protected fixture issue"), { editable: false }),
    issue(4, "Commentable fixture issue"),
    issue(5, "Comment validation fixture issue"),
    issue(6, "Assignable fixture issue"),
    issue(7, "Labelable fixture issue"),
    issue(8, "Milestone fixture issue"),
    issue(9, "Closable fixture issue"),
    issue(10, "Protected fixture issue", { editable: false }),
    issue(11, env("E2E_OPEN_ISSUE_TITLE", "Active fixture issue")),
    issue(12, env("E2E_CLOSED_ISSUE_TITLE", "Resolved fixture issue"), { state: "closed" }),
  ];

  const pullRequests = [
    pullRequest(1, env("E2E_OPEN_PULL_REQUEST_TITLE", "Active fixture pull request")),
    pullRequest(2, env("E2E_DRAFT_PULL_REQUEST_TITLE", "Fixture work-in-progress pull request"), {
      draft: true,
      head: env("E2E_DRAFT_PULL_REQUEST_SOURCE_BRANCH", "review-feature"),
      base: env("E2E_DRAFT_PULL_REQUEST_TARGET_BRANCH", "main"),
      author: env("E2E_DRAFT_PR_AUTHOR_USERNAME", "fixture-user-27"),
    }),
    pullRequest(3, env("E2E_PULL_REQUEST_TITLE", "Fixture pull request detail")),
    pullRequest(4, "Reviewable fixture pull request"),
    pullRequest(5, "Review queue fixture pull request"),
    pullRequest(6, "Change request fixture pull request"),
    pullRequest(7, "Assignable fixture pull request", { author: env("E2E_PR_AUTHOR_USERNAME", "fixture-user-29") }),
    pullRequest(8, "Mergeable fixture pull request"),
    pullRequest(9, "Unmergeable fixture pull request", { mergeable: false }),
    pullRequest(10, "Closable fixture pull request", { author: env("E2E_PR_AUTHOR_USERNAME", "fixture-user-29") }),
    pullRequest(11, "Protected fixture pull request", { author: "someone-else" }),
    {
      ...pullRequest(1, "Protected branch fixture pull request"),
      id: "acme/protection-repo#1",
      repoId: "acme/protection-repo",
    },
    {
      ...pullRequest(1, "Public fixture pull request"),
      id: `open-labs/${env("E2E_PUBLIC_REPOSITORY_NAME", "roadmap-app")}#1`,
      repoId: `open-labs/${env("E2E_PUBLIC_REPOSITORY_NAME", "roadmap-app")}`,
    },
  ];

  return normalizeEnterpriseState({ version: 2, accounts, organizations, teams, repositories, issues, pullRequests });
}

const allowedCollections = new Set([
  "accounts",
  "organizations",
  "teams",
  "repositories",
  "issues",
  "pullRequests",
]);
const patchFields = Object.freeze({
  teams: new Set(["parent"]),
  repositories: new Set(["accesses", "branches", "commits", "defaultBranch", "protections", "visibility"]),
  issues: new Set(["description", "milestone", "state", "title"]),
  pullRequests: new Set(["checks", "checkUpdatedBy", "draft", "readyEvent", "state"]),
});
const listFields = Object.freeze({
  organizations: new Set(["members"]),
  teams: new Set(["members"]),
  repositories: new Set(["accesses", "branches", "protections"]),
  issues: new Set(["assignees", "comments", "labels"]),
  pullRequests: new Set(["reviewComments", "reviewers", "reviews"]),
});
let ready = false;
let state = seededState();
let mutationQueue = Promise.resolve();
const isolatedFixtureWorlds = process.env.FACTORY26_RESET_FIXTURES === "1";
const passwordOverrides = new Map();
const listRemovalOverrides = new Map();
const authentication = new SessionStore();

await mkdir(dataDir, { recursive: true });
if (process.env.FACTORY26_RESET_FIXTURES !== "1") {
  try {
    const loaded = JSON.parse(await readFile(statePath, "utf8"));
    if (!loaded || !Array.isArray(loaded.accounts)) throw new Error("state must contain an accounts array");
    state = loaded;
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw new Error(`Refusing to overwrite unreadable GitHub state at ${statePath}: ${error.message}`);
    }
  }
}
normalizeEnterpriseState(state);
if (!state.auditEvents.length) {
  appendAuditEvent(state, { actor: "system", action: "system.genesis", result: { ok: true } });
}
const startupIntegrity = verifyEnterpriseState(state);
if (!startupIntegrity.valid) {
  throw new Error(`Refusing to start with invalid GitHub state: ${startupIntegrity.layer || startupIntegrity.reason}`);
}
await persistSnapshot(state);
ready = true;

async function persistSnapshot(candidate) {
  const temporary = `${statePath}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporary, JSON.stringify(candidate, null, 2), { mode: 0o600 });
    await rename(temporary, statePath);
  } finally {
    await unlink(temporary).catch(() => undefined);
  }
}

function serializeMutation(operation) {
  const queued = mutationQueue.then(operation, operation);
  mutationQueue = queued.then(() => undefined, () => undefined);
  return queued;
}

function applyCommandEffects(effects) {
  for (const effect of effects || []) {
    if (effect.type === "session.create") authentication.storeSession(effect.token, effect.username, effect.worldId);
    else if (effect.type === "session.destroy") authentication.destroySession(effect.token);
    else if (effect.type === "session.destroy_account") authentication.destroyAccountSessions(effect.username, effect.worldId);
    else if (effect.type === "recovery.create") authentication.storeRecovery(effect.token, effect.email, effect.worldId);
    else if (effect.type === "recovery.consume") authentication.consumeRecovery(effect.token, effect.worldId);
    else if (effect.type === "password.override") passwordOverrides.set(effect.key, effect.passwordHash);
    else if (effect.type === "list.remove.override") {
      const removedValues = listRemovalOverrides.get(effect.key) || new Set();
      removedValues.add(effect.value);
      listRemovalOverrides.set(effect.key, removedValues);
    } else throw new Error(`unsupported command effect: ${effect.type}`);
  }
}

function sendJson(response, status, value) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(value));
}

class RequestError extends Error {
  constructor(status, message, code = "invalid_request") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function readBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 1_000_000) throw new RequestError(413, "request body too large", "body_too_large");
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new RequestError(400, "request body must be valid JSON", "invalid_json");
  }
}

function requestWorldId(request) {
  const value = String(request.headers["x-langqi-world"] || "global");
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(value)) throw new RequestError(400, "invalid fixture world identifier", "invalid_world");
  return value;
}

function resultStatus(result) {
  if (result.ok) return 200;
  if (result.code === "authentication_required" || result.code === "invalid_session") return 401;
  if (result.code === "forbidden") return 403;
  if (result.code === "not_found") return 404;
  if (["invalid_username", "invalid_email", "invalid_password", "invalid_confirmation", "invalid_recovery", "validation"].includes(result.code)) return 422;
  return 409;
}

function projectedState(source, actor) {
  const projected = structuredClone(source);
  projected.accounts = actor === "anonymous" ? [] : projected.accounts.map(publicAccount);
  projected.repositories = projected.repositories.filter((repo) => canViewRepository(source, repo, actor));
  const visibleRepositories = new Set(projected.repositories.map((repo) => repo.id));
  projected.issues = projected.issues.filter((entry) => visibleRepositories.has(entry.repoId));
  projected.pullRequests = projected.pullRequests.filter((entry) => visibleRepositories.has(entry.repoId));
  for (const collectionName of ["workflows", "workflowRuns", "environments", "rulesets", "issueForms", "repositoryRelations"]) {
    projected[collectionName] = (projected[collectionName] || []).filter((entry) => {
      if (entry.repoId && !visibleRepositories.has(entry.repoId)) return false;
      if (collectionName === "repositoryRelations" && entry.username !== actor) return false;
      return true;
    });
  }
  const ownedOrganizations = new Set(
    source.organizations
      .filter((organization) => isOrganizationOwner(source, organization.name, actor))
      .map((organization) => organization.name),
  );
  projected.identityProviders = (projected.identityProviders || []).filter((entry) => ownedOrganizations.has(entry.organization));
  projected.scimUsers = (projected.scimUsers || []).filter((entry) => ownedOrganizations.has(entry.organization));
  projected.dataPolicies = (projected.dataPolicies || []).filter((entry) => ownedOrganizations.has(entry.organization));
  projected.auditEvents = (projected.auditEvents || []).filter(
    (event) => event.actor === actor || event.actor === "system" || (event.organization && ownedOrganizations.has(event.organization)),
  );
  projected.viewer = actor === "anonymous" ? "" : actor;
  return projected;
}

function collection(targetState, name) {
  if (!allowedCollections.has(name)) throw new Error("unsupported collection");
  return targetState[name];
}

function sameValue(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function removalKey(worldId, payload) {
  return `${worldId}:${payload.collection}:${payload.id}:${payload.field}:${payload.key || ""}`;
}

function stateForWorld(worldId, actor = "anonymous") {
  if (!isolatedFixtureWorlds) return projectedState(state, actor);
  const worldState = structuredClone(state);
  for (const [key, removedValues] of listRemovalOverrides) {
    const [entryWorld, collectionName, id, field, valueKey] = key.split(":");
    if (entryWorld !== worldId || !allowedCollections.has(collectionName)) continue;
    const item = worldState[collectionName].find((entry) => entry.id === id);
    if (!item || !Array.isArray(item[field])) continue;
    item[field] = item[field].filter((value) => {
      const candidate = valueKey ? value?.[valueKey] : value;
      return !removedValues.has(JSON.stringify(candidate));
    });
  }
  return projectedState(worldState, actor);
}

function execute(targetState, command, worldId = "global", actor = "anonymous", sessionToken = "") {
  const state = targetState;
  const { type, payload = {} } = command;
  const integrity = verifyEnterpriseState(state);
  if (type !== "audit.verify" && !integrity.valid) {
    return { ok: false, code: "integrity", message: "audit chain integrity failed; command is blocked", details: integrity };
  }
  if (type === "account.create") {
    const username = validateUsername(payload.username);
    const email = validateEmail(payload.email);
    const password = validatePassword(payload.password);
    if (!username.ok) return { ok: false, code: username.code, message: username.message };
    if (!email.ok) return { ok: false, code: email.code, message: email.message };
    if (!password.ok) return { ok: false, code: password.code, message: password.message };
    if (payload.confirm !== payload.password) return { ok: false, code: "invalid_confirmation", message: "password confirmation does not match" };
    if (payload.terms !== true) return { ok: false, code: "validation", message: "service terms must be accepted" };
    const duplicate = state.accounts.find(
      (item) => item.username === username.value || normalizeEmail(item.email) === email.value,
    );
    if (duplicate) return { ok: false, code: duplicate.username === username.value ? "username_exists" : "email_exists" };
    const account = {
      id: username.value,
      username: username.value,
      email: email.value,
      passwordHash: hashPassword(password.value),
      emailVerified: true,
      credentialStatus: "active",
    };
    state.accounts.push(account);
    return { ok: true, item: publicAccount(account) };
  }
  if (type === "account.authenticate") {
    const item = state.accounts.find(
      (account) =>
        (account.username === String(payload.login || "").trim() || normalizeEmail(account.email) === normalizeEmail(payload.login)) &&
        account.credentialStatus !== "disabled" &&
        verifyPassword(account, payload.password, passwordOverrides.get(`${worldId}:${account.username}`)),
    );
    const nextSessionToken = item ? randomUUID() : "";
    return {
      ok: Boolean(item),
      code: item ? undefined : "invalid_credentials",
      item: item ? { username: item.username, email: item.email } : null,
      sessionToken: nextSessionToken || undefined,
      ...(item ? { _effects: [{ type: "session.create", token: nextSessionToken, username: item.username, worldId }] } : {}),
    };
  }
  if (type === "account.recovery.begin") {
    const nextResetToken = randomUUID();
    return {
      ok: true,
      resetToken: nextResetToken,
      _effects: [{ type: "recovery.create", token: nextResetToken, email: payload.email, worldId }],
    };
  }
  if (type === "account.password") {
    const checked = validatePassword(payload.password);
    if (!checked.ok) return { ok: false, code: checked.code, message: checked.message };
    if (payload.confirm !== payload.password) return { ok: false, code: "invalid_confirmation", message: "password confirmation does not match" };
    let item;
    if (actor !== "anonymous") {
      item = state.accounts.find((account) => account.username === actor);
      if (!item || !verifyPassword(item, payload.currentPassword, passwordOverrides.get(`${worldId}:${item.username}`))) {
        return { ok: false, code: "incorrect_current_password" };
      }
    } else {
      if (payload.code !== "123456") return { ok: false, code: "invalid_recovery", message: "verification code is invalid" };
      const recovery = authentication.resolveRecovery(payload.resetToken, worldId);
      if (!recovery) return { ok: false, code: "invalid_recovery", message: "recovery context is invalid or expired" };
      item = state.accounts.find((account) => normalizeEmail(account.email) === recovery.email);
      if (!item) return { ok: false, code: "invalid_recovery", message: "recovery could not be completed" };
    }
    const nextHash = hashPassword(checked.value);
    const effects = [];
    if (isolatedFixtureWorlds) effects.push({ type: "password.override", key: `${worldId}:${item.username}`, passwordHash: nextHash });
    else {
      item.passwordHash = nextHash;
      delete item.password;
    }
    effects.push({ type: "session.destroy_account", username: item.username, worldId });
    if (actor === "anonymous") effects.push({ type: "recovery.consume", token: payload.resetToken, worldId });
    return { ok: true, _effects: effects };
  }
  if (type === "session.destroy") {
    if (actor === "anonymous" || !sessionToken) return { ok: false, code: "invalid_session", message: "session is not active" };
    return { ok: true, _effects: [{ type: "session.destroy", token: sessionToken }] };
  }
  const enterpriseResult = executeEnterpriseCommand(state, command, { actor, worldId });
  if (enterpriseResult !== null) return enterpriseResult;
  const authorization = authorizeGenericCommand(state, type, payload, actor);
  if (!authorization.ok) return authorization;
  if (type === "pullRequest.create") {
    const repo = state.repositories.find((entry) => entry.id === payload.item?.repoId);
    const title = String(payload.item?.title || "").trim();
    const base = String(payload.item?.base || "");
    const head = String(payload.item?.head || "");
    if (!repo || !title || title.length > 256 || base === head || !repo.branches.some((branch) => branch.name === base) || !repo.branches.some((branch) => branch.name === head)) {
      return { ok: false, code: "validation", message: "pull request requires a title and two existing, distinct branches" };
    }
    const numbers = state.pullRequests
      .filter((pull) => pull.repoId === payload.item.repoId)
      .map((pull) => Number(pull.number) || 0);
    const number = Math.max(0, ...numbers) + 1;
    const item = {
      repoId: repo.id,
      id: `${payload.item.repoId}#${number}`,
      number,
      title,
      description: String(payload.item.description || "").slice(0, 65_536),
      state: "open",
      draft: Boolean(payload.item.draft),
      base,
      head,
      author: actor,
      mergeable: payload.item.mergeable !== false,
      files: Array.isArray(payload.item.files) ? payload.item.files.map(String).slice(0, 2_000) : [],
      commits: Array.isArray(payload.item.commits) ? payload.item.commits.map(String).slice(0, 2_000) : [],
      reviewers: [],
      reviewComments: [],
      reviews: [],
      checks: { test: "pending" },
      checkUpdatedBy: "",
      readyEvent: false,
    };
    state.pullRequests.push(item);
    return { ok: true, item };
  }
  if (type === "create") {
    const items = collection(state, payload.collection);
    let item;
    if (payload.collection === "organizations") {
      const name = String(payload.item?.name || "").trim();
      if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(name)) return { ok: false, code: "validation", message: "organization name is invalid" };
      item = { id: name, name, displayName: String(payload.item?.displayName || "").trim().slice(0, 160), owner: actor, members: [{ username: actor, role: "Owner" }] };
      if (!item.displayName) return { ok: false, code: "validation", message: "organization display name is required" };
    } else if (payload.collection === "teams") {
      const organization = String(payload.item?.organization || "");
      const name = String(payload.item?.name || "").trim();
      if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(name)) return { ok: false, code: "validation", message: "team name is invalid" };
      item = { id: `${organization}/${name}`, organization, name, parent: "", members: [], maintainers: [actor] };
    } else if (payload.collection === "repositories") {
      const owner = String(payload.item?.owner || "");
      const name = String(payload.item?.name || "").trim();
      if (!/^[A-Za-z0-9._-]{1,100}$/.test(name)) return { ok: false, code: "validation", message: "repository name is invalid" };
      if (payload.item?.forkedFrom) {
        const source = state.repositories.find((entry) => entry.id === payload.item.forkedFrom);
        if (!canViewRepository(state, source, actor)) return { ok: false, code: "forbidden", message: "fork source is not visible to the current account" };
      }
      const branches = Array.isArray(payload.item?.branches) ? structuredClone(payload.item.branches) : [];
      const defaultBranch = String(payload.item?.defaultBranch || "main");
      if (!branches.length || !branches.some((branch) => branch.name === defaultBranch)) return { ok: false, code: "validation", message: "repository default branch must exist" };
      item = {
        id: `${owner}/${name}`,
        owner,
        name,
        visibility: payload.item.visibility === "private" ? "private" : "public",
        description: String(payload.item.description || "").slice(0, 1_000),
        defaultBranch,
        branches,
        commits: Array.isArray(payload.item.commits) ? structuredClone(payload.item.commits).slice(0, 10_000) : [],
        accesses: [],
        administrators: [],
        protections: [],
        labels: Array.isArray(payload.item.labels) ? payload.item.labels.map(String).slice(0, 200) : ["bug", "enhancement"],
        milestones: Array.isArray(payload.item.milestones) ? payload.item.milestones.map(String).slice(0, 200) : [],
        forkedFrom: payload.item.forkedFrom || null,
      };
    } else if (payload.collection === "issues") {
      const repo = state.repositories.find((entry) => entry.id === payload.item?.repoId);
      const title = String(payload.item?.title || "").trim();
      if (!repo || !title || title.length > 256) return { ok: false, code: "validation", message: "issue title is required and must not exceed 256 characters" };
      const number = Math.max(0, ...state.issues.filter((entry) => entry.repoId === repo.id).map((entry) => Number(entry.number) || 0)) + 1;
      item = {
        id: `${repo.id}#${number}`,
        repoId: repo.id,
        number,
        title,
        description: String(payload.item.description || "").slice(0, 65_536),
        state: "open",
        author: actor,
        editable: true,
        assignees: [],
        labels: [],
        milestone: "",
        comments: [],
      };
    } else {
      return { ok: false, code: "unsupported_collection", message: "unsupported create collection" };
    }
    if (items.some((entry) => entry.id === item.id)) return { ok: false, code: "exists" };
    items.push(item);
    return { ok: true, item };
  }
  if (type === "patch") {
    const items = collection(state, payload.collection);
    const item = items.find((entry) => entry.id === payload.id);
    if (!item) return { ok: false, code: "not_found" };
    const requestedFields = Object.keys(payload.patch || {});
    if (!requestedFields.length || !patchFields[payload.collection] || requestedFields.some((field) => !patchFields[payload.collection].has(field))) {
      return { ok: false, code: "validation", message: "patch contains an undeclared field" };
    }
    if (payload.collection === "pullRequests" && payload.patch?.state === "merged") {
      return { ok: false, code: "protected_transition", message: "use pullRequest.merge so server-side policies are enforced" };
    }
    if (payload.collection === "repositories" && Array.isArray(payload.patch?.branches)) {
      const previous = new Map((item.branches || []).map((branch) => [branch.name, branch]));
      const next = new Map(payload.patch.branches.map((branch) => [branch.name, branch]));
      for (const branchName of new Set([...previous.keys(), ...next.keys()])) {
        if (JSON.stringify(previous.get(branchName)?.files || null) === JSON.stringify(next.get(branchName)?.files || null)) continue;
        const policy = evaluateDirectBranchWritePolicy(state, item, branchName, actor);
        if (!policy.allowed) return { ok: false, code: "protected_branch", message: "direct branch write is blocked by server-side policy", details: policy };
      }
    }
    Object.assign(item, payload.patch || {});
    return { ok: true, item };
  }
  if (type === "list.add") {
    const item = collection(state, payload.collection).find((entry) => entry.id === payload.id);
    if (!item) return { ok: false, code: "not_found" };
    if (!listFields[payload.collection]?.has(payload.field)) return { ok: false, code: "validation", message: "list mutation targets an undeclared field" };
    const values = Array.isArray(item[payload.field]) ? item[payload.field] : [];
    let nextValue = structuredClone(payload.value);
    if (payload.collection === "issues" && payload.field === "comments") {
      const body = String(payload.value?.body || "").trim();
      if (!body || body.length > 65_536) return { ok: false, code: "validation", message: "comment must contain 1–65536 characters" };
      nextValue = { id: randomUUID(), author: actor, body, createdAt: new Date().toISOString() };
    }
    if (payload.collection === "pullRequests" && payload.field === "reviewComments") {
      const body = String(payload.value?.body || "").trim();
      if (!body || body.length > 65_536) return { ok: false, code: "validation", message: "review comment must contain 1–65536 characters" };
      nextValue = { id: randomUUID(), author: actor, body, pending: Boolean(payload.value?.pending), createdAt: new Date().toISOString() };
    }
    if (payload.collection === "pullRequests" && payload.field === "reviews") {
      const status = String(payload.value?.status || "");
      if (!["approved", "changes_requested"].includes(status)) return { ok: false, code: "validation", message: "review decision is invalid" };
      nextValue = { id: randomUUID(), author: actor, status, summary: String(payload.value?.summary || "").slice(0, 65_536), createdAt: new Date().toISOString() };
    }
    const duplicate = values.some((value) =>
      payload.uniqueKey ? value?.[payload.uniqueKey] === nextValue?.[payload.uniqueKey] : sameValue(value, nextValue),
    );
    if (!duplicate) values.push(nextValue);
    item[payload.field] = values;
    return { ok: !duplicate, code: duplicate ? "exists" : undefined, item };
  }
  if (type === "list.remove") {
    const item = collection(state, payload.collection).find((entry) => entry.id === payload.id);
    if (!item) return { ok: false, code: "not_found" };
    if (!listFields[payload.collection]?.has(payload.field)) return { ok: false, code: "validation", message: "list mutation targets an undeclared field" };
    const values = Array.isArray(item[payload.field]) ? item[payload.field] : [];
    if (isolatedFixtureWorlds) {
      const key = removalKey(worldId, payload);
      return {
        ok: true,
        item,
        _effects: [{ type: "list.remove.override", key, value: JSON.stringify(payload.value) }],
      };
    }
    item[payload.field] = values.filter((value) =>
      payload.key ? value?.[payload.key] !== payload.value : !sameValue(value, payload.value),
    );
    return { ok: true, item };
  }
  throw new Error(`unsupported command: ${type}`);
}

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
    const worldId = requestWorldId(request);
    const token = bearerToken(request);
    const session = authentication.resolveSession(token, worldId);
    const actor = session?.username || "anonymous";
    if (url.pathname === "/api/health") return sendJson(response, ready ? 200 : 503, { ready });
    if (url.pathname === "/api/audit/verify" && request.method === "GET") {
      if (actor === "anonymous") return sendJson(response, 401, { error: "Authentication required", code: "authentication_required" });
      return sendJson(response, 200, verifyEnterpriseState(state));
    }
    if (url.pathname === "/api/audit/export.csv" && request.method === "GET") {
      const organization = url.searchParams.get("organization") || "";
      const org = organization && state.organizations.find((entry) => entry.name === organization);
      const owner = org && (org.owner === actor || org.members.some((member) => member.username === actor && member.role === "Owner"));
      if (!organization || actor === "anonymous" || !owner) {
        return sendJson(response, 403, { error: "Organization owner role is required" });
      }
      const body = auditCsv(stateForWorld(worldId, actor).auditEvents, {
        organization,
        actor: url.searchParams.get("actor") || "",
        action: url.searchParams.get("action") || "",
      });
      response.writeHead(200, {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": 'attachment; filename="audit-log.csv"',
      });
      return response.end(body);
    }
    if (url.pathname === "/api/state" && request.method === "GET") {
      // A navigation may request fresh state while a keepalive command from
      // the previous document is still committing. Read only after every
      // mutation that was already queued at this point has settled.
      await mutationQueue;
      return sendJson(response, 200, stateForWorld(worldId, actor));
    }
    if (url.pathname === "/api/command" && request.method === "POST") {
      const command = await readBody(request);
      if (!command || typeof command !== "object" || Array.isArray(command) || typeof command.type !== "string") {
        throw new RequestError(400, "command type is required", "invalid_command");
      }
      const outcome = await serializeMutation(async () => {
        const queuedSession = authentication.resolveSession(token, worldId);
        const effectiveActor = queuedSession?.username || "anonymous";
        const candidate = structuredClone(state);
        const rawResult = execute(candidate, command, worldId, effectiveActor, token);
        const effects = Array.isArray(rawResult._effects) ? rawResult._effects : [];
        const { _effects: _internalEffects, ...result } = rawResult;
        const audited = shouldAuditCommand(command.type);
        if (result.code === "integrity" || !audited) return { result, status: resultStatus(result) };

        const committed = result.ok ? candidate : structuredClone(state);
        appendAuditEvent(committed, { actor: effectiveActor, action: command.type, payload: command.payload, result });
        const postcondition = verifyEnterpriseState(committed);
        if (!postcondition.valid) {
          const failed = { ok: false, code: "postcondition_failed", message: "transaction failed integrity validation", details: postcondition };
          return { result: failed, status: 409 };
        }
        await persistSnapshot(committed);
        state = committed;
        if (result.ok) applyCommandEffects(effects);
        return { result, status: resultStatus(result) };
      });
      return sendJson(response, outcome.status, outcome.result);
    }
    if (url.pathname.startsWith("/api/")) return sendJson(response, 404, { error: "Not found" });

    const requested = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/+/, "");
    let resolved = path.resolve(publicDir, requested);
    if (!resolved.startsWith(publicDir + path.sep)) resolved = path.join(publicDir, "index.html");
    let data;
    try {
      data = await readFile(resolved);
    } catch {
      resolved = path.join(publicDir, "index.html");
      data = await readFile(resolved);
    }
    response.writeHead(200, { "content-type": contentTypes[path.extname(resolved)] || "application/octet-stream" });
    response.end(data);
  } catch (error) {
    sendJson(response, error.status || 500, { error: error.message, ...(error.code ? { code: error.code } : {}) });
  }
});

server.listen(port, host, () => console.log(`Langqi Forge GitHub kernel listening on ${host}:${port}`));
