import assert from "node:assert/strict";
import test from "node:test";
import { pathToFileURL } from "node:url";

const enterpriseModule = process.env.ENTERPRISE_MODULE
  ? pathToFileURL(process.env.ENTERPRISE_MODULE).href
  : new URL("../factory26_harness/templates/github/backend/enterprise.mjs", import.meta.url).href;
const {
  appendAuditEvent,
  auditCsv,
  evaluateDirectBranchWritePolicy,
  evaluatePullRequestPolicy,
  executeEnterpriseCommand,
  normalizeEnterpriseState,
  topologicalJobs,
  verifyAuditChain,
  verifyEnterpriseState,
} = await import(enterpriseModule);

function stateFixture() {
  return normalizeEnterpriseState({
    version: 1,
    accounts: [
      { id: "owner", username: "owner", email: "owner@example.test", password: "owner-password" },
      { id: "writer", username: "writer", email: "writer@example.test", password: "writer-password" },
      { id: "reviewer", username: "reviewer", email: "reviewer@example.test", password: "reviewer-password" },
    ],
    organizations: [
      {
        id: "acme",
        name: "acme",
        displayName: "Acme",
        owner: "owner",
        members: [
          { username: "owner", role: "Owner" },
          { username: "writer", role: "Member" },
          { username: "reviewer", role: "Member" },
        ],
      },
    ],
    teams: [],
    repositories: [
      {
        id: "acme/pr-repo",
        owner: "acme",
        name: "pr-repo",
        visibility: "private",
        accesses: [
          { subject: "writer", role: "write" },
          { subject: "reviewer", role: "admin" },
        ],
        branches: [{ name: "main", files: {} }],
      },
      {
        id: "acme/issues-repo",
        owner: "acme",
        name: "issues-repo",
        visibility: "private",
        accesses: [{ subject: "writer", role: "write" }],
        branches: [{ name: "main", files: {} }],
      },
    ],
    issues: [],
    pullRequests: [],
  });
}

test("workflow graph is deterministically ordered and cycles fail closed", () => {
  const ordered = topologicalJobs([
    { id: "deploy", needs: ["build"], steps: ["deploy"] },
    { id: "test", needs: [], steps: ["test"] },
    { id: "build", needs: ["test"], steps: ["build"] },
  ]);
  assert.deepEqual(ordered.map((job) => job.id), ["test", "build", "deploy"]);
  assert.throws(
    () => topologicalJobs([{ id: "a", needs: ["b"] }, { id: "b", needs: ["a"] }]),
    /cycle/,
  );
});

test("workflow dispatch waits for an independent protected-environment reviewer", () => {
  const state = stateFixture();
  state.environments = [
    {
      id: "acme/pr-repo:production",
      repoId: "acme/pr-repo",
      name: "production",
      requiredReviewers: ["reviewer"],
      preventSelfReview: true,
      waitTimerMinutes: 0,
      protectedBranchesOnly: true,
      secretNames: [],
    },
  ];
  const workflow = executeEnterpriseCommand(
    state,
    {
      type: "workflow.upsert",
      payload: {
        id: "acme/pr-repo:release",
        repoId: "acme/pr-repo",
        name: "Release",
        triggers: { workflowDispatch: { inputs: [{ id: "ticket", required: true }] }, schedules: [] },
        jobs: [
          { id: "test", needs: [], steps: ["npm test"] },
          { id: "deploy", needs: ["test"], environment: "production", steps: ["deploy"] },
        ],
      },
    },
    { actor: "owner" },
  );
  assert.equal(workflow.ok, true);

  const missing = executeEnterpriseCommand(
    state,
    { type: "workflow.dispatch", payload: { workflowId: workflow.item.id, inputs: {} } },
    { actor: "writer" },
  );
  assert.equal(missing.code, "validation");

  const dispatched = executeEnterpriseCommand(
    state,
    { type: "workflow.dispatch", payload: { workflowId: workflow.item.id, inputs: { ticket: "REL-42" } } },
    { actor: "writer" },
  );
  assert.equal(dispatched.ok, true);
  assert.equal(dispatched.item.status, "waiting");
  assert.equal(dispatched.item.jobs.find((job) => job.id === "test").status, "success");
  assert.equal(dispatched.item.jobs.find((job) => job.id === "deploy").status, "waiting");

  const denied = executeEnterpriseCommand(
    state,
    { type: "workflow.approve_environment", payload: { runId: dispatched.item.id, jobId: "deploy" } },
    { actor: "writer" },
  );
  assert.equal(denied.code, "forbidden");

  const approved = executeEnterpriseCommand(
    state,
    { type: "workflow.approve_environment", payload: { runId: dispatched.item.id, jobId: "deploy" } },
    { actor: "reviewer" },
  );
  assert.equal(approved.ok, true);
  assert.equal(approved.item.status, "success");
});

test("protected environments reject a run initiator even when that actor is a reviewer", () => {
  const state = stateFixture();
  state.environments = [{
    id: "acme/pr-repo:production",
    repoId: "acme/pr-repo",
    name: "production",
    requiredReviewers: ["writer"],
    preventSelfReview: true,
    waitTimerMinutes: 0,
    protectedBranchesOnly: true,
    secretNames: [],
  }];
  const workflow = executeEnterpriseCommand(state, {
    type: "workflow.upsert",
    payload: {
      id: "acme/pr-repo:self-review",
      repoId: "acme/pr-repo",
      name: "Self review guard",
      triggers: { workflowDispatch: { inputs: [] }, schedules: [] },
      jobs: [{ id: "deploy", needs: [], environment: "production", steps: ["deploy"] }],
    },
  }, { actor: "owner" });
  const run = executeEnterpriseCommand(state, {
    type: "workflow.dispatch",
    payload: { workflowId: workflow.item.id, inputs: {} },
  }, { actor: "writer" });
  assert.equal(run.item.status, "waiting");
  const denied = executeEnterpriseCommand(state, {
    type: "workflow.approve_environment",
    payload: { runId: run.item.id, jobId: "deploy" },
  }, { actor: "writer" });
  assert.equal(denied.code, "self_review_forbidden");
  assert.equal(run.item.status, "waiting");
});

test("rulesets enforce CODEOWNERS syntax and separation of duties", () => {
  const state = stateFixture();
  state.rulesets = [];
  const invalidOwners = executeEnterpriseCommand(
    state,
    { type: "ruleset.upsert", payload: { repoId: "acme/pr-repo", name: "Bad", codeownersText: "/src reviewer" } },
    { actor: "owner" },
  );
  assert.equal(invalidOwners.code, "validation");

  const conflict = executeEnterpriseCommand(
    state,
    { type: "ruleset.upsert", payload: { repoId: "acme/pr-repo", name: "Conflict", requiredReviewers: ["reviewer"], bypassActors: ["reviewer"], codeownersText: "/src/ @reviewer" } },
    { actor: "owner" },
  );
  assert.equal(conflict.code, "validation");

  const created = executeEnterpriseCommand(
    state,
    { type: "ruleset.upsert", payload: { repoId: "acme/pr-repo", name: "Guard", requiredApprovals: 2, requiredStatusChecks: ["test"], requireCodeOwnerReview: true, codeownersText: "/src/ @reviewer\n*.md @writer" } },
    { actor: "owner" },
  );
  assert.equal(created.ok, true);
  const evaluation = executeEnterpriseCommand(
    state,
    { type: "ruleset.evaluate", payload: { repoId: "acme/pr-repo", paths: ["src/index.js", "README.md"] } },
    { actor: "writer" },
  );
  assert.equal(evaluation.evaluation.requiredApprovals, 2);
  assert.deepEqual(evaluation.evaluation.requiredOwners, ["@reviewer", "@writer"]);
});

test("active rulesets enforce checks, independent reviews, CODEOWNERS, and an atomic real merge", () => {
  const state = stateFixture();
  state.rulesets = [];
  const repo = state.repositories.find((entry) => entry.id === "acme/pr-repo");
  repo.branches = [
    { name: "main", files: { "README.md": "base", "src/existing.js": "old" } },
    { name: "feature", files: { "README.md": "feature", "src/existing.js": "new", "src/new.js": "created" } },
  ];
  repo.commits = [];
  const pull = {
    id: "acme/pr-repo#42",
    repoId: repo.id,
    number: 42,
    title: "Controlled change",
    state: "open",
    draft: false,
    mergeable: true,
    base: "main",
    head: "feature",
    author: "writer",
    files: ["src/existing.js", "src/new.js"],
    reviews: [],
    checks: { test: "pending" },
  };
  state.pullRequests.push(pull);
  assert.equal(executeEnterpriseCommand(state, {
    type: "ruleset.upsert",
    payload: { repoId: repo.id, name: "Merge gate", include: ["refs/heads/main"], requiredApprovals: 1, requiredStatusChecks: ["test"], requireCodeOwnerReview: true, codeownersText: "/src/ @reviewer" },
  }, { actor: "owner" }).ok, true);

  const directWrite = evaluateDirectBranchWritePolicy(state, repo, "main", "owner");
  assert.equal(directWrite.allowed, false);
  assert.ok(directWrite.reasons.some((reason) => reason.startsWith("ruleset_blocks_direct_write:")));

  const pending = evaluatePullRequestPolicy(state, pull, "owner");
  assert.equal(pending.allowed, false);
  assert.ok(pending.reasons.includes("approvals_missing:1"));
  assert.ok(pending.reasons.includes("status_check_not_success:test"));
  const before = structuredClone(repo.branches[0]);
  assert.equal(executeEnterpriseCommand(state, { type: "pullRequest.merge", payload: { id: pull.id } }, { actor: "owner" }).code, "policy_denied");
  assert.deepEqual(repo.branches[0], before);
  assert.equal(pull.state, "open");

  pull.reviews.push({ id: "r1", author: "reviewer", status: "approved" });
  const workflow = state.workflows.find((entry) => entry.repoId === repo.id);
  const run = executeEnterpriseCommand(state, { type: "workflow.dispatch", payload: { workflowId: workflow.id, pullRequestId: pull.id, inputs: {} } }, { actor: "writer" });
  assert.equal(run.ok, true);
  assert.equal(run.item.status, "waiting");
  assert.equal(pull.checks.test, "success");
  assert.equal(pull.checkProvenance.test.workflowRunId, run.item.id);
  assert.match(pull.checkUpdatedBy, /^actions:/);
  const eligible = evaluatePullRequestPolicy(state, pull, "owner");
  assert.equal(eligible.allowed, true);
  const merged = executeEnterpriseCommand(state, { type: "pullRequest.merge", payload: { id: pull.id } }, { actor: "owner" });
  assert.equal(merged.ok, true);
  assert.equal(pull.state, "merged");
  assert.equal(repo.branches[0].files["src/new.js"], "created");
  assert.equal(repo.commits[0].id, pull.mergeCommit);
  assert.equal(repo.commits[0].author, "owner");
});

test("issue forms validate required structured responses", () => {
  const state = stateFixture();
  const missing = executeEnterpriseCommand(
    state,
    { type: "issueForm.submit", payload: { formId: "acme/issues-repo:bug-report", title: "Broken", values: {} } },
    { actor: "writer" },
  );
  assert.equal(missing.code, "validation");

  const submitted = executeEnterpriseCommand(
    state,
    { type: "issueForm.submit", payload: { formId: "acme/issues-repo:bug-report", title: "Broken", values: { reproduction: "Open the page", expected: "It loads", severity: "High", checks: ["I searched existing issues"] } } },
    { actor: "writer" },
  );
  assert.equal(submitted.ok, true);
  assert.equal(submitted.item.formId, "acme/issues-repo:bug-report");
  assert.match(submitted.item.description, /Reproduction steps/);
});

test("audit chain is append-only, verifiable, redacted, and exportable", () => {
  const state = stateFixture();
  appendAuditEvent(state, { actor: "owner", action: "identityProvider.upsert", payload: { organization: "acme", certificate: "PRIVATE", password: "do-not-store" }, result: { ok: true } });
  appendAuditEvent(state, { actor: "writer", action: "workflow.dispatch", payload: { repoId: "acme/pr-repo", token: "secret-token" }, result: { ok: true } });
  assert.deepEqual(verifyAuditChain(state.auditEvents).valid, true);
  assert.equal(verifyEnterpriseState(state).valid, true);
  assert.equal(state.auditEvents[0].metadata.password, "[REDACTED]");
  assert.equal(state.auditEvents[1].organization, "acme");
  assert.doesNotMatch(JSON.stringify(state.auditEvents), /secret-token|do-not-store|PRIVATE/);
  assert.match(auditCsv(state.auditEvents, { organization: "acme" }), /workflow\.dispatch/);

  state.auditEvents[0].actor = "tampered";
  assert.equal(verifyAuditChain(state.auditEvents).valid, false);
  const before = state.workflows.length;
  const blocked = executeEnterpriseCommand(state, {
    type: "workflow.upsert",
    payload: { repoId: "acme/pr-repo", name: "Must not commit", jobs: [{ id: "build", needs: [], steps: ["npm test"] }] },
  }, { actor: "owner" });
  assert.equal(blocked.code, "integrity");
  assert.equal(state.workflows.length, before);
  assert.throws(
    () => appendAuditEvent(state, { actor: "owner", action: "workflow.upsert", result: blocked }),
    /audit chain integrity failed/,
  );

  const stateTamper = stateFixture();
  appendAuditEvent(stateTamper, { actor: "system", action: "system.genesis", result: { ok: true } });
  stateTamper.repositories[0].visibility = "public";
  const stateIntegrity = verifyEnterpriseState(stateTamper);
  assert.equal(stateIntegrity.valid, false);
  assert.equal(stateIntegrity.layer, "business_state");
  assert.equal(stateIntegrity.reason, "state_hash_mismatch");
  assert.equal(executeEnterpriseCommand(stateTamper, { type: "repository.star", payload: { repoId: "acme/pr-repo", starred: true } }, { actor: "writer" }).code, "integrity");
});

test("SAML gates SCIM and row/field policies filter without mutating input", () => {
  const state = stateFixture();
  const disabled = executeEnterpriseCommand(
    state,
    { type: "scim.provision", payload: { organization: "acme", userName: "managed" } },
    { actor: "owner" },
  );
  assert.equal(disabled.code, "scim_disabled");

  assert.equal(executeEnterpriseCommand(
    state,
    { type: "identityProvider.upsert", payload: { organization: "acme", enabled: true, scimEnabled: true, signOnUrl: "https://idp.example.test/sso" } },
    { actor: "owner" },
  ).ok, true);
  assert.equal(executeEnterpriseCommand(
    state,
    { type: "scim.provision", payload: { organization: "acme", userName: "managed", email: "managed@example.test" } },
    { actor: "owner" },
  ).ok, true);

  assert.equal(executeEnterpriseCommand(
    state,
    { type: "dataPolicy.upsert", payload: { organization: "acme", name: "Sales scope", subjects: ["writer"], rowField: "department", allowedRowValues: ["sales"], hiddenFields: ["salary"], readOnlyFields: ["id"] } },
    { actor: "owner" },
  ).ok, true);
  const rows = [{ id: 1, department: "sales", salary: 10 }, { id: 2, department: "legal", salary: 20 }];
  const evaluated = executeEnterpriseCommand(
    state,
    { type: "dataPolicy.evaluate", payload: { organization: "acme", rows } },
    { actor: "writer" },
  );
  assert.deepEqual(evaluated.item, [{ id: 1, department: "sales" }]);
  assert.deepEqual(rows, [{ id: 1, department: "sales", salary: 10 }, { id: 2, department: "legal", salary: 20 }]);
});
