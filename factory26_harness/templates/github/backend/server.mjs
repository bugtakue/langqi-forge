import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../frontend/dist");
const dataDir = path.join(here, "data");
const statePath = path.join(dataDir, "github-state.json");
const port = Number.parseInt(process.env.PORT || "3000", 10);
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
    password: env(`${prefix}_PASSWORD`, "Fixture-password-123!"),
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
    accounts.push({ id: username, username, email: `${username}@example.test`, password: "Fixture-password-123!" });
  }

  const organizationOwner = env("E2E_ORGANIZATION_OWNER_USERNAME", "fixture-06-organization-owner");
  const existingMember = env(
    "E2E_ORGANIZATION_EXISTING_MEMBER_USERNAME",
    "fixture-08-organization-existing-member",
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
      maintainers: [env("E2E_TEAM_MAINTAINER_USERNAME", "fixture-07-team-maintainer")],
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
    repository("acme", "managed-repo"),
    repository("acme", "private-repo", { visibility: "private" }),
    repository("acme", "access-repo", {
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
        { subject: env("E2E_ISSUE_COMMENTER_USERNAME", "fixture-user-22"), role: "read" },
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

  return { version: 1, accounts, organizations, teams, repositories, issues, pullRequests };
}

const allowedCollections = new Set([
  "accounts",
  "organizations",
  "teams",
  "repositories",
  "issues",
  "pullRequests",
]);
let ready = false;
let state = seededState();
let persistence = Promise.resolve();
const isolatedFixtureWorlds = process.env.FACTORY26_RESET_FIXTURES === "1";
const passwordOverrides = new Map();
const listRemovalOverrides = new Map();

await mkdir(dataDir, { recursive: true });
if (process.env.FACTORY26_RESET_FIXTURES !== "1") {
  try {
    const loaded = JSON.parse(await readFile(statePath, "utf8"));
    if (loaded && Array.isArray(loaded.accounts)) state = loaded;
  } catch {
    // A fresh deterministic fixture is the safe fallback.
  }
}
await writeFile(statePath, JSON.stringify(state, null, 2));
ready = true;

function persist() {
  const snapshot = JSON.stringify(state, null, 2);
  persistence = persistence.then(async () => {
    const temporary = `${statePath}.${randomUUID()}.tmp`;
    await writeFile(temporary, snapshot);
    await rename(temporary, statePath);
  });
  return persistence;
}

function sendJson(response, status, value) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(value));
}

async function readBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 1_000_000) throw new Error("request body too large");
    chunks.push(chunk);
  }
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

function collection(name) {
  if (!allowedCollections.has(name)) throw new Error("unsupported collection");
  return state[name];
}

function sameValue(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function removalKey(worldId, payload) {
  return `${worldId}:${payload.collection}:${payload.id}:${payload.field}:${payload.key || ""}`;
}

function stateForWorld(worldId) {
  if (!isolatedFixtureWorlds) return state;
  const projected = structuredClone(state);
  for (const [key, removedValues] of listRemovalOverrides) {
    const [entryWorld, collectionName, id, field, valueKey] = key.split(":");
    if (entryWorld !== worldId || !allowedCollections.has(collectionName)) continue;
    const item = projected[collectionName].find((entry) => entry.id === id);
    if (!item || !Array.isArray(item[field])) continue;
    item[field] = item[field].filter((value) => {
      const candidate = valueKey ? value?.[valueKey] : value;
      return !removedValues.has(JSON.stringify(candidate));
    });
  }
  return projected;
}

function execute(command, worldId = "global") {
  const { type, payload = {} } = command;
  if (type === "account.create") {
    const duplicate = state.accounts.find(
      (item) => item.username === payload.username || item.email === payload.email,
    );
    if (duplicate) return { ok: false, code: duplicate.username === payload.username ? "username_exists" : "email_exists" };
    const account = { id: payload.username, ...payload };
    state.accounts.push(account);
    return { ok: true, item: account };
  }
  if (type === "account.authenticate") {
    const item = state.accounts.find(
      (account) =>
        (account.username === payload.login || account.email === payload.login) &&
        (passwordOverrides.get(`${worldId}:${account.username}`) || account.password) === payload.password,
    );
    return {
      ok: Boolean(item),
      code: item ? undefined : "invalid_credentials",
      item: item ? { username: item.username, email: item.email } : null,
    };
  }
  if (type === "account.password") {
    const item = state.accounts.find(
      (account) => account.username === payload.username || account.email === payload.email,
    );
    if (!item) return { ok: false, code: "not_found" };
    const currentPassword = passwordOverrides.get(`${worldId}:${item.username}`) || item.password;
    if (payload.currentPassword !== undefined && currentPassword !== payload.currentPassword) {
      return { ok: false, code: "incorrect_current_password" };
    }
    if (isolatedFixtureWorlds) passwordOverrides.set(`${worldId}:${item.username}`, payload.password);
    else item.password = payload.password;
    return { ok: true };
  }
  if (type === "pullRequest.create") {
    const numbers = state.pullRequests
      .filter((pull) => pull.repoId === payload.item.repoId)
      .map((pull) => Number(pull.number) || 0);
    const number = Math.max(0, ...numbers) + 1;
    const item = {
      ...payload.item,
      id: `${payload.item.repoId}#${number}`,
      number,
    };
    state.pullRequests.push(item);
    return { ok: true, item };
  }
  if (type === "create") {
    const items = collection(payload.collection);
    if (items.some((item) => item.id === payload.item.id)) return { ok: false, code: "exists" };
    items.push(payload.item);
    return { ok: true, item: payload.item };
  }
  if (type === "patch") {
    const items = collection(payload.collection);
    const item = items.find((entry) => entry.id === payload.id);
    if (!item) return { ok: false, code: "not_found" };
    Object.assign(item, payload.patch || {});
    return { ok: true, item };
  }
  if (type === "list.add") {
    const item = collection(payload.collection).find((entry) => entry.id === payload.id);
    if (!item) return { ok: false, code: "not_found" };
    const values = Array.isArray(item[payload.field]) ? item[payload.field] : [];
    const duplicate = values.some((value) =>
      payload.uniqueKey ? value?.[payload.uniqueKey] === payload.value?.[payload.uniqueKey] : sameValue(value, payload.value),
    );
    if (!duplicate) values.push(payload.value);
    item[payload.field] = values;
    return { ok: !duplicate, code: duplicate ? "exists" : undefined, item };
  }
  if (type === "list.remove") {
    const item = collection(payload.collection).find((entry) => entry.id === payload.id);
    if (!item) return { ok: false, code: "not_found" };
    const values = Array.isArray(item[payload.field]) ? item[payload.field] : [];
    if (isolatedFixtureWorlds) {
      const key = removalKey(worldId, payload);
      const removedValues = listRemovalOverrides.get(key) || new Set();
      removedValues.add(JSON.stringify(payload.value));
      listRemovalOverrides.set(key, removedValues);
      return { ok: true, item };
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
    const worldId = String(request.headers["x-langqi-world"] || "global");
    if (url.pathname === "/api/health") return sendJson(response, ready ? 200 : 503, { ready });
    if (url.pathname === "/api/state" && request.method === "GET") return sendJson(response, 200, stateForWorld(worldId));
    if (url.pathname === "/api/command" && request.method === "POST") {
      const result = execute(await readBody(request), worldId);
      if (result.ok) await persist();
      return sendJson(response, result.ok ? 200 : 409, result);
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
    sendJson(response, 500, { error: error.message });
  }
});

server.listen(port, "127.0.0.1", () => console.log(`Langqi Forge GitHub kernel listening on ${port}`));
