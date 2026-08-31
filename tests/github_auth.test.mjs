import assert from "node:assert/strict";
import test from "node:test";
import { pathToFileURL } from "node:url";

const authModule = process.env.GITHUB_AUTH_MODULE
  ? pathToFileURL(process.env.GITHUB_AUTH_MODULE).href
  : new URL("../factory26_harness/templates/github/backend/auth.mjs", import.meta.url).href;
const authorizationModule = process.env.GITHUB_AUTHORIZATION_MODULE
  ? pathToFileURL(process.env.GITHUB_AUTHORIZATION_MODULE).href
  : new URL("../factory26_harness/templates/github/backend/authorization.mjs", import.meta.url).href;

const {
  SessionStore,
  hashPassword,
  publicAccount,
  validateEmail,
  validatePassword,
  validateUsername,
  verifyPassword,
} = await import(authModule);
const {
  authorizeGenericCommand,
  canViewRepository,
  repositoryRole,
} = await import(authorizationModule);

test("credentials enforce the published contract and never expose a reusable secret", () => {
  assert.equal(validateUsername("a").ok, true);
  assert.equal(validateUsername("alpha-9").ok, true);
  for (const candidate of ["Alpha", "-alpha", "alpha-", "alpha--beta", "a".repeat(40)]) {
    assert.equal(validateUsername(candidate).ok, false, candidate);
  }
  assert.equal(validateEmail(" Person@Example.Test ").value, "person@example.test");
  assert.equal(validateEmail("a@example").ok, false);
  assert.equal(validatePassword("Valid-password-123!").ok, true);
  assert.equal(validatePassword("missing-complexity").ok, false);

  const encoded = hashPassword("Valid-password-123!");
  assert.doesNotMatch(encoded, /Valid-password/);
  assert.equal(verifyPassword({ passwordHash: encoded }, "Valid-password-123!"), true);
  assert.equal(verifyPassword({ passwordHash: encoded }, "Wrong-password-123!"), false);
  assert.deepEqual(
    publicAccount({ username: "alpha", password: "legacy", passwordHash: encoded, emailVerified: true }),
    { username: "alpha", emailVerified: true },
  );
});

test("opaque sessions are bound to one browser world and can be revoked", () => {
  const sessions = new SessionStore();
  const token = sessions.createSession("writer", "world-a");
  assert.equal(sessions.resolveSession(token, "world-a").username, "writer");
  assert.equal(sessions.resolveSession(token, "world-b"), null);

  const second = sessions.createSession("writer", "world-a");
  sessions.destroyAccountSessions("writer", "world-a");
  assert.equal(sessions.resolveSession(second, "world-a"), null);
});

function fixtureState() {
  return {
    organizations: [{ id: "acme", name: "acme", owner: "owner", members: [{ username: "owner", role: "Owner" }] }],
    teams: [{ id: "acme/platform", organization: "acme", name: "platform", members: ["team-user"], maintainers: ["maintainer"] }],
    repositories: [
      { id: "acme/private", owner: "acme", visibility: "private", accesses: [{ subject: "writer", role: "write" }, { subject: "platform", role: "triage" }] },
    ],
    issues: [{ id: "acme/private#1", repoId: "acme/private", author: "writer" }],
    pullRequests: [{ id: "acme/private#2", repoId: "acme/private", author: "writer" }],
  };
}

test("server authorization rejects forged anonymous writes and resolves team roles", () => {
  const state = fixtureState();
  const repo = state.repositories[0];
  assert.equal(canViewRepository(state, repo, "anonymous"), false);
  assert.equal(repositoryRole(state, repo, "team-user"), "triage");
  assert.equal(repositoryRole(state, repo, "platform"), "");
  assert.equal(repositoryRole(state, repo, "owner"), "admin");
  assert.equal(
    authorizeGenericCommand(state, "patch", { collection: "repositories", id: repo.id, patch: { visibility: "public" } }, "writer").code,
    "forbidden",
  );
  assert.equal(
    authorizeGenericCommand(state, "list.add", { collection: "issues", id: "acme/private#1", field: "comments" }, "anonymous").code,
    "authentication_required",
  );
  assert.equal(
    authorizeGenericCommand(state, "list.add", { collection: "issues", id: "acme/private#1", field: "labels" }, "team-user").ok,
    true,
  );
});

test("team grants are scoped to the repository owner organization", () => {
  const state = fixtureState();
  state.teams.push({
    id: "other/platform",
    organization: "other",
    name: "platform",
    members: ["cross-org-user"],
    maintainers: [],
  });
  assert.equal(repositoryRole(state, state.repositories[0], "cross-org-user"), "");
});
