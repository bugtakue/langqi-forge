import { createHash, randomUUID } from "node:crypto";

const FORM_COMPONENT_TYPES = new Set(["markdown", "input", "textarea", "dropdown", "checkboxes"]);
const TERMINAL_JOB_STATES = new Set(["success", "failure", "cancelled", "skipped"]);

function clone(value) {
  return structuredClone(value);
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function cleanString(value, maximum = 500) {
  return String(value ?? "").trim().slice(0, maximum);
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value) {
  return createHash("sha256").update(canonical(value)).digest("hex");
}

function enterpriseBusinessStateHash(state) {
  const collections = [
    "accounts",
    "organizations",
    "teams",
    "repositories",
    "issues",
    "pullRequests",
    "workflows",
    "workflowRuns",
    "environments",
    "rulesets",
    "issueForms",
    "identityProviders",
    "scimUsers",
    "dataPolicies",
    "repositoryRelations",
  ];
  return digest(Object.fromEntries(collections.map((collection) => [collection, asArray(state[collection])])));
}

function redact(value, key = "") {
  if (/password|secret|token|certificate|private.?key/i.test(key)) return "[REDACTED]";
  if (Array.isArray(value)) return value.map((entry) => redact(entry));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([name, entry]) => [name, redact(entry, name)]));
  }
  return value;
}

function csvCell(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function fail(code, message, details = undefined) {
  return { ok: false, code, message, ...(details ? { details } : {}) };
}

function findRepository(state, repoId) {
  return state.repositories.find((entry) => entry.id === repoId);
}

function findOrganization(state, organization) {
  return state.organizations.find((entry) => entry.name === organization || entry.id === organization);
}

function isOrganizationOwner(state, organization, actor) {
  const org = findOrganization(state, organization);
  return Boolean(org && (org.owner === actor || org.members.some((member) => member.username === actor && member.role === "Owner")));
}

function canAdminRepository(state, repo, actor) {
  if (!repo || !actor) return false;
  if (repo.owner === actor || isOrganizationOwner(state, repo.owner, actor)) return true;
  return asArray(repo.accesses).some((access) => access.subject === actor && access.role === "admin");
}

function canWriteRepository(state, repo, actor) {
  if (canAdminRepository(state, repo, actor)) return true;
  return Boolean(repo && actor && asArray(repo.accesses).some((access) => access.subject === actor && ["write", "admin"].includes(access.role)));
}

function canMaintainRepository(state, repo, actor) {
  if (canAdminRepository(state, repo, actor)) return true;
  return Boolean(repo && actor && asArray(repo.accesses).some((access) => access.subject === actor && ["maintain", "admin"].includes(access.role)));
}

function seedWorkflow() {
  return {
    id: "acme/pr-repo:ci",
    repoId: "acme/pr-repo",
    name: "CI",
    path: ".github/workflows/ci.yml",
    enabled: true,
    triggers: {
      push: true,
      pullRequest: true,
      workflowDispatch: {
        inputs: [
          { id: "release", label: "Release candidate", type: "boolean", required: false, default: false },
        ],
      },
      schedules: [{ cron: "0 6 * * 1-5", timezone: "UTC" }],
    },
    jobs: [
      { id: "test", name: "Test", needs: [], runsOn: "ubuntu-latest", environment: "", steps: ["npm ci", "npm test"] },
      { id: "package", name: "Package", needs: ["test"], runsOn: "ubuntu-latest", environment: "", steps: ["npm run build"] },
      { id: "deploy", name: "Deploy", needs: ["package"], runsOn: "ubuntu-latest", environment: "production", steps: ["deploy"] },
    ],
    createdAt: "2026-08-31T00:00:00.000Z",
    updatedAt: "2026-08-31T00:00:00.000Z",
  };
}

export function seedEnterpriseState() {
  return {
    workflows: [seedWorkflow()],
    workflowRuns: [],
    environments: [
      {
        id: "acme/pr-repo:production",
        repoId: "acme/pr-repo",
        name: "production",
        requiredReviewers: ["fixture-user-30"],
        preventSelfReview: true,
        waitTimerMinutes: 0,
        protectedBranchesOnly: true,
        secretNames: ["DEPLOY_TOKEN"],
      },
    ],
    rulesets: [
      {
        id: "acme/pr-repo:main-guard",
        repoId: "acme/pr-repo",
        name: "Main branch guard",
        target: "branch",
        enforcement: "evaluate",
        include: ["refs/heads/main"],
        exclude: [],
        bypassActors: [],
        requiredApprovals: 1,
        requiredStatusChecks: ["test"],
        requireCodeOwnerReview: true,
        blockForcePush: true,
        codeownersText: "/src/ @acme/platform-team\n*.md @fixture-user-30",
        codeowners: [
          { pattern: "/src/", owners: ["@acme/platform-team"] },
          { pattern: "*.md", owners: ["@fixture-user-30"] },
        ],
      },
    ],
    issueForms: [
      {
        id: "acme/issues-repo:bug-report",
        repoId: "acme/issues-repo",
        name: "Bug report",
        description: "Report a reproducible product defect",
        titlePrefix: "[Bug] ",
        labels: ["bug"],
        body: [
          { type: "markdown", id: "intro", value: "Thanks for helping us improve." },
          { type: "textarea", id: "reproduction", label: "Reproduction steps", required: true, placeholder: "1. Open…" },
          { type: "textarea", id: "expected", label: "Expected behavior", required: true },
          { type: "dropdown", id: "severity", label: "Severity", required: true, options: ["Low", "Medium", "High"] },
          { type: "checkboxes", id: "checks", label: "Checks", required: true, options: ["I searched existing issues"] },
        ],
      },
    ],
    identityProviders: [],
    scimUsers: [],
    dataPolicies: [],
    repositoryRelations: [],
    auditEvents: [],
  };
}

export const ENTERPRISE_COLLECTIONS = Object.freeze(Object.keys(seedEnterpriseState()));

export function normalizeEnterpriseState(state) {
  const defaults = seedEnterpriseState();
  for (const [collection, entries] of Object.entries(defaults)) {
    if (!Array.isArray(state[collection])) state[collection] = clone(entries);
  }
  state.version = Math.max(Number(state.version) || 1, 2);
  return state;
}

export function appendAuditEvent(state, { actor = "anonymous", action, payload = {}, result = {} } = {}) {
  normalizeEnterpriseState(state);
  const integrity = verifyAuditChain(state.auditEvents);
  if (!integrity.valid) throw new Error(`audit chain integrity failed at event ${integrity.brokenAt || "unknown"}`);
  const previous = state.auditEvents.at(-1);
  const safePayload = redact(payload);
  const resource = cleanString(
    payload.repoId || payload.organization || payload.id || payload.item?.id || result.item?.id || "system",
    240,
  );
  const repositoryId = cleanString(payload.repoId || payload.item?.repoId || "", 240);
  const repositoryOwner = repositoryId.includes("/") ? repositoryId.split("/", 1)[0] : "";
  const inferredOrganization = state.organizations.some((entry) => entry.name === repositoryOwner) ? repositoryOwner : "";
  const event = {
    id: randomUUID(),
    sequence: (previous?.sequence || 0) + 1,
    timestamp: new Date().toISOString(),
    actor: cleanString(actor || "anonymous", 160),
    action: cleanString(action || "unknown", 160),
    resource,
    organization: cleanString(payload.organization || payload.org || inferredOrganization, 160),
    repository: repositoryId,
    outcome: result.ok === false ? "denied" : "success",
    metadata: safePayload,
    stateHash: enterpriseBusinessStateHash(state),
    previousHash: previous?.hash || "GENESIS",
  };
  event.hash = digest(event);
  state.auditEvents.push(event);
  return event;
}

export function verifyAuditChain(events) {
  let previousHash = "GENESIS";
  for (let index = 0; index < asArray(events).length; index += 1) {
    const event = events[index];
    if (event.sequence !== index + 1 || event.previousHash !== previousHash) {
      return { valid: false, brokenAt: index + 1, reason: "sequence_or_link_mismatch" };
    }
    const { hash, ...unsigned } = event;
    if (digest(unsigned) !== hash) return { valid: false, brokenAt: index + 1, reason: "hash_mismatch" };
    previousHash = hash;
  }
  return { valid: true, count: asArray(events).length, headHash: previousHash };
}

export function verifyEnterpriseState(state) {
  const chain = verifyAuditChain(state?.auditEvents);
  if (!chain.valid) return { ...chain, layer: "audit_chain" };
  if (chain.count === 0) {
    return { ...chain, stateBound: false, stateHash: enterpriseBusinessStateHash(state || {}) };
  }
  const expectedStateHash = state.auditEvents.at(-1)?.stateHash;
  if (!/^[a-f0-9]{64}$/.test(expectedStateHash || "")) {
    return { valid: false, layer: "business_state", reason: "state_hash_missing", count: chain.count };
  }
  const actualStateHash = enterpriseBusinessStateHash(state);
  if (actualStateHash !== expectedStateHash) {
    return {
      valid: false,
      layer: "business_state",
      reason: "state_hash_mismatch",
      count: chain.count,
      expectedStateHash,
      actualStateHash,
    };
  }
  return { ...chain, stateBound: true, stateHash: actualStateHash };
}

export function auditCsv(events, filters = {}) {
  const rows = asArray(events).filter((event) => {
    if (filters.organization && event.organization !== filters.organization) return false;
    if (filters.actor && event.actor !== filters.actor) return false;
    if (filters.action && !event.action.includes(filters.action)) return false;
    return true;
  });
  const header = ["sequence", "timestamp", "actor", "action", "resource", "outcome", "state_hash", "previous_hash", "hash", "metadata"];
  return [
    header.map(csvCell).join(","),
    ...rows.map((event) =>
      [
        event.sequence,
        event.timestamp,
        event.actor,
        event.action,
        event.resource,
        event.outcome,
        event.stateHash,
        event.previousHash,
        event.hash,
        event.metadata,
      ]
        .map(csvCell)
        .join(","),
    ),
  ].join("\n");
}

function validateCron(cron) {
  const value = cleanString(cron, 100);
  return value.split(/\s+/).length === 5 && /^[\d*/?,\-\s]+$/.test(value);
}

function normalizeJobs(value) {
  const jobs = asArray(value).map((job) => ({
    id: cleanString(job.id, 80),
    name: cleanString(job.name || job.id, 120),
    needs: [...new Set(asArray(job.needs).map((entry) => cleanString(entry, 80)).filter(Boolean))],
    runsOn: cleanString(job.runsOn || "ubuntu-latest", 80),
    environment: cleanString(job.environment, 100),
    steps: asArray(job.steps).map((entry) => cleanString(typeof entry === "string" ? entry : entry.name || entry.run, 300)).filter(Boolean),
  }));
  if (!jobs.length) throw new Error("workflow requires at least one job");
  const ids = new Set();
  for (const job of jobs) {
    if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(job.id)) throw new Error(`invalid job id: ${job.id || "<empty>"}`);
    if (ids.has(job.id)) throw new Error(`duplicate job id: ${job.id}`);
    ids.add(job.id);
  }
  for (const job of jobs) {
    for (const dependency of job.needs) {
      if (!ids.has(dependency)) throw new Error(`unknown job dependency: ${dependency}`);
      if (dependency === job.id) throw new Error(`job cannot depend on itself: ${job.id}`);
    }
  }
  return jobs;
}

export function topologicalJobs(value) {
  const jobs = normalizeJobs(value);
  const byId = new Map(jobs.map((job) => [job.id, job]));
  const pending = new Set(byId.keys());
  const ordered = [];
  while (pending.size) {
    const ready = [...pending].filter((id) => byId.get(id).needs.every((dependency) => !pending.has(dependency))).sort();
    if (!ready.length) throw new Error("workflow job graph contains a cycle");
    for (const id of ready) {
      ordered.push(byId.get(id));
      pending.delete(id);
    }
  }
  return ordered;
}

function normalizeWorkflow(state, raw, existing = null) {
  const repoId = cleanString(raw.repoId || existing?.repoId, 240);
  const repo = findRepository(state, repoId);
  if (!repo) throw new Error("repository not found");
  const name = cleanString(raw.name || existing?.name, 120);
  if (!name) throw new Error("workflow name is required");
  const jobs = topologicalJobs(raw.jobs || existing?.jobs || []);
  const triggers = clone(raw.triggers || existing?.triggers || { workflowDispatch: { inputs: [] } });
  triggers.schedules = asArray(triggers.schedules).map((entry) => ({
    cron: cleanString(entry.cron, 100),
    timezone: cleanString(entry.timezone || "UTC", 80),
  }));
  if (triggers.schedules.some((entry) => !validateCron(entry.cron))) throw new Error("cron schedule must contain five valid fields");
  const id = cleanString(raw.id || existing?.id || `${repoId}:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`, 320);
  return {
    id,
    repoId,
    name,
    path: cleanString(raw.path || existing?.path || `.github/workflows/${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.yml`, 300),
    enabled: raw.enabled === undefined ? existing?.enabled !== false : Boolean(raw.enabled),
    triggers,
    jobs,
    createdAt: existing?.createdAt || new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

function inputDefinitions(workflow) {
  return asArray(workflow.triggers?.workflowDispatch?.inputs);
}

function normalizeDispatchInputs(workflow, rawInputs) {
  const provided = rawInputs && typeof rawInputs === "object" ? rawInputs : {};
  const output = {};
  for (const definition of inputDefinitions(workflow)) {
    const id = cleanString(definition.id, 80);
    let value = provided[id];
    if ((value === undefined || value === "") && definition.default !== undefined) value = definition.default;
    if (definition.required && (value === undefined || value === "" || (definition.type === "boolean" && value !== true))) {
      throw new Error(`required workflow input is missing: ${id}`);
    }
    if (value !== undefined) output[id] = value;
  }
  return output;
}

function synchronizePullRequestChecks(state, run) {
  if (!run.pullRequestId) return;
  const pull = state.pullRequests.find((entry) => entry.id === run.pullRequestId && entry.repoId === run.repoId);
  if (!pull) return;
  pull.checks ||= {};
  pull.checkProvenance ||= {};
  for (const job of run.jobs) {
    const status = job.status === "success" ? "success" : ["failure", "cancelled", "skipped"].includes(job.status) ? "failure" : "pending";
    pull.checks[job.id] = status;
    pull.checkProvenance[job.id] = { workflowRunId: run.id, jobId: job.id, status, updatedAt: new Date().toISOString() };
  }
  pull.checkUpdatedBy = `actions:${run.workflowId}`;
  pull.checkUpdatedAt = new Date().toISOString();
}

function advanceRun(state, run) {
  let changed = true;
  while (changed) {
    changed = false;
    for (const job of run.jobs) {
      if (job.status !== "queued") continue;
      const dependencies = job.needs.map((id) => run.jobs.find((candidate) => candidate.id === id));
      if (dependencies.some((dependency) => dependency && !TERMINAL_JOB_STATES.has(dependency.status))) continue;
      if (dependencies.some((dependency) => dependency?.status !== "success")) {
        job.status = "skipped";
        job.completedAt = new Date().toISOString();
        changed = true;
        continue;
      }
      const environment = state.environments.find((entry) => entry.repoId === run.repoId && entry.name === job.environment);
      const approved = run.approvals.some((approval) => approval.jobId === job.id);
      if (environment && environment.requiredReviewers.length && !approved) {
        job.status = "waiting";
        job.logs.push(`Waiting for approval to deploy to ${environment.name}.`);
        changed = true;
        continue;
      }
      job.status = "success";
      job.startedAt = job.startedAt || new Date().toISOString();
      job.completedAt = new Date().toISOString();
      job.logs.push(...job.steps.map((step) => `$ ${step}\ncompleted`));
      changed = true;
    }
  }
  const statuses = run.jobs.map((job) => job.status);
  run.status = statuses.some((status) => status === "waiting")
    ? "waiting"
    : statuses.every((status) => TERMINAL_JOB_STATES.has(status))
      ? statuses.every((status) => ["success", "skipped"].includes(status)) ? "success" : "failure"
      : "in_progress";
  if (["success", "failure", "cancelled"].includes(run.status)) run.completedAt = run.completedAt || new Date().toISOString();
  synchronizePullRequestChecks(state, run);
  return run;
}

function createWorkflowRun(state, workflow, payload, actor) {
  if (!workflow.enabled) throw new Error("workflow is disabled");
  const inputs = normalizeDispatchInputs(workflow, payload.inputs);
  const pullRequestId = cleanString(payload.pullRequestId, 320);
  if (pullRequestId && !state.pullRequests.some((entry) => entry.id === pullRequestId && entry.repoId === workflow.repoId)) {
    throw new Error("workflow pull request must belong to the same repository");
  }
  const number = Math.max(0, ...state.workflowRuns.filter((entry) => entry.workflowId === workflow.id).map((entry) => Number(entry.number) || 0)) + 1;
  const run = {
    id: `${workflow.id}:run:${number}`,
    workflowId: workflow.id,
    repoId: workflow.repoId,
    number,
    event: cleanString(payload.event || "workflow_dispatch", 80),
    ref: cleanString(payload.ref || "main", 200),
    pullRequestId,
    inputs,
    actor,
    status: "queued",
    createdAt: new Date().toISOString(),
    completedAt: "",
    approvals: [],
    jobs: topologicalJobs(workflow.jobs).map((job) => ({ ...clone(job), status: "queued", startedAt: "", completedAt: "", logs: [] })),
  };
  state.workflowRuns.push(run);
  return advanceRun(state, run);
}

function parseCodeowners(text) {
  const entries = [];
  for (const rawLine of cleanString(text, 20_000).split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const [pattern, ...owners] = line.split(/\s+/);
    if (!pattern || !owners.length || owners.some((owner) => !owner.startsWith("@"))) {
      throw new Error(`invalid CODEOWNERS line: ${line}`);
    }
    entries.push({ pattern, owners: [...new Set(owners)] });
  }
  return entries;
}

function globMatches(pattern, path) {
  const escaped = pattern
    .replace(/^\//, "")
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replaceAll("**", "§§")
    .replaceAll("*", "[^/]*")
    .replaceAll("§§", ".*");
  const suffix = pattern.endsWith("/") ? ".*" : "";
  return new RegExp(`^(?:.*\/)?${escaped}${suffix}$`).test(path.replace(/^\//, ""));
}

function normalizeRuleset(state, raw, existing = null) {
  const repoId = cleanString(raw.repoId || existing?.repoId, 240);
  if (!findRepository(state, repoId)) throw new Error("repository not found");
  const name = cleanString(raw.name || existing?.name, 120);
  if (!name) throw new Error("ruleset name is required");
  const codeownersText = String(raw.codeownersText ?? existing?.codeownersText ?? "");
  const bypassActors = [...new Set(asArray(raw.bypassActors ?? existing?.bypassActors).map((entry) => cleanString(entry, 160)).filter(Boolean))];
  const requiredReviewers = [...new Set(asArray(raw.requiredReviewers ?? existing?.requiredReviewers).map((entry) => cleanString(entry, 160)).filter(Boolean))];
  if (bypassActors.some((actor) => requiredReviewers.includes(actor))) throw new Error("a required reviewer cannot also bypass the ruleset");
  return {
    id: cleanString(raw.id || existing?.id || `${repoId}:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`, 320),
    repoId,
    name,
    target: cleanString(raw.target || existing?.target || "branch", 40),
    enforcement: ["active", "evaluate", "disabled"].includes(raw.enforcement) ? raw.enforcement : existing?.enforcement || "active",
    include: asArray(raw.include ?? existing?.include ?? ["refs/heads/main"]).map((entry) => cleanString(entry, 240)).filter(Boolean),
    exclude: asArray(raw.exclude ?? existing?.exclude).map((entry) => cleanString(entry, 240)).filter(Boolean),
    bypassActors,
    requiredReviewers,
    requiredApprovals: Math.max(0, Math.min(10, Number(raw.requiredApprovals ?? existing?.requiredApprovals ?? 1) || 0)),
    requiredStatusChecks: [...new Set(asArray(raw.requiredStatusChecks ?? existing?.requiredStatusChecks).map((entry) => cleanString(entry, 120)).filter(Boolean))],
    requireCodeOwnerReview: Boolean(raw.requireCodeOwnerReview ?? existing?.requireCodeOwnerReview),
    blockForcePush: raw.blockForcePush === undefined ? existing?.blockForcePush !== false : Boolean(raw.blockForcePush),
    codeownersText,
    codeowners: parseCodeowners(codeownersText),
  };
}

function latestReviewDecisions(pull) {
  const decisions = new Map();
  for (const review of asArray(pull.reviews)) {
    const author = cleanString(review.author, 160);
    if (author) decisions.set(author, cleanString(review.status, 40));
  }
  return decisions;
}

function referenceMatches(pattern, reference) {
  return globMatches(cleanString(pattern, 240), cleanString(reference, 240));
}

function rulesetTargetsPull(ruleset, pull) {
  const reference = `refs/heads/${pull.base}`;
  return asArray(ruleset.include).some((pattern) => referenceMatches(pattern, reference))
    && !asArray(ruleset.exclude).some((pattern) => referenceMatches(pattern, reference));
}

export function evaluateDirectBranchWritePolicy(state, repo, branchName, actor) {
  if (!canWriteRepository(state, repo, actor)) return { allowed: false, reasons: ["write_permission_required"], policyIds: [] };
  const reasons = [];
  const policyIds = [];
  for (const protection of asArray(repo.protections).filter((entry) => referenceMatches(entry.pattern, branchName))) {
    reasons.push(`protected_branch:${protection.pattern}`);
    policyIds.push(`branch-protection:${protection.pattern}`);
  }
  const reference = `refs/heads/${branchName}`;
  for (const ruleset of state.rulesets.filter((entry) => entry.repoId === repo.id && entry.enforcement === "active" && entry.blockForcePush)) {
    const targeted = asArray(ruleset.include).some((pattern) => referenceMatches(pattern, reference))
      && !asArray(ruleset.exclude).some((pattern) => referenceMatches(pattern, reference));
    if (!targeted || asArray(ruleset.bypassActors).some((entry) => actorMatchesOwner(state, actor, entry))) continue;
    reasons.push(`ruleset_blocks_direct_write:${ruleset.id}`);
    policyIds.push(ruleset.id);
  }
  return { allowed: reasons.length === 0, reasons, policyIds };
}

function actorMatchesOwner(state, actor, owner) {
  const normalized = cleanString(owner, 200).replace(/^@/, "");
  if (normalized === actor) return true;
  if (!normalized.includes("/")) return false;
  const [organization, teamName] = normalized.split("/", 2);
  const team = state.teams.find((entry) => entry.organization === organization && (entry.name === teamName || entry.id === `${organization}/${teamName}`));
  return Boolean(team && [...asArray(team.members), ...asArray(team.maintainers)].some((member) => (typeof member === "string" ? member : member.username) === actor));
}

export function evaluatePullRequestPolicy(state, pull, actor) {
  const repo = pull && findRepository(state, pull.repoId);
  if (!repo) return { allowed: false, reasons: ["repository_not_found"], policyIds: [] };
  const reasons = [];
  if (pull.state !== "open") reasons.push("pull_request_not_open");
  if (pull.draft) reasons.push("draft_pull_request");
  if (pull.mergeable === false) reasons.push("source_marked_unmergeable");

  const decisions = latestReviewDecisions(pull);
  const approvedActors = new Set([...decisions].filter(([, status]) => status === "approved").map(([reviewer]) => reviewer));
  const changesRequested = [...decisions].filter(([, status]) => status === "changes_requested").map(([reviewer]) => reviewer);
  const nonAuthorApprovals = [...approvedActors].filter((reviewer) => reviewer !== pull.author);
  const requiredStatusChecks = new Set();
  const policyIds = [];
  let requiredApprovals = 0;
  let changesRequestedBlocks = false;

  for (const protection of asArray(repo.protections).filter((entry) => referenceMatches(entry.pattern, pull.base))) {
    policyIds.push(`branch-protection:${protection.pattern}`);
    requiredApprovals = Math.max(requiredApprovals, Number(protection.approvals) || 0);
    if (protection.statusCheck) requiredStatusChecks.add(protection.statusCheck);
    changesRequestedBlocks = true;
  }

  const activeRulesets = state.rulesets.filter((ruleset) => ruleset.repoId === pull.repoId && ruleset.enforcement === "active" && rulesetTargetsPull(ruleset, pull));
  for (const ruleset of activeRulesets) {
    const bypassed = asArray(ruleset.bypassActors).some((entry) => actorMatchesOwner(state, actor, entry));
    if (bypassed) continue;
    policyIds.push(ruleset.id);
    requiredApprovals = Math.max(requiredApprovals, Number(ruleset.requiredApprovals) || 0);
    asArray(ruleset.requiredStatusChecks).forEach((check) => requiredStatusChecks.add(check));
    changesRequestedBlocks = true;
    for (const reviewer of asArray(ruleset.requiredReviewers)) {
      if (![...approvedActors].some((approved) => actorMatchesOwner(state, approved, reviewer))) reasons.push(`required_reviewer_missing:${reviewer}`);
    }
    if (ruleset.requireCodeOwnerReview) {
      for (const path of asArray(pull.files)) {
        const ownerGroups = asArray(ruleset.codeowners).filter((entry) => globMatches(entry.pattern, path));
        if (ownerGroups.length && !ownerGroups.some((entry) => entry.owners.some((owner) => [...approvedActors].some((approved) => actorMatchesOwner(state, approved, owner))))) {
          reasons.push(`codeowner_review_missing:${path}`);
        }
      }
    }
  }

  if (nonAuthorApprovals.length < requiredApprovals) reasons.push(`approvals_missing:${requiredApprovals - nonAuthorApprovals.length}`);
  if (changesRequestedBlocks && changesRequested.length) reasons.push(`changes_requested:${changesRequested.join(",")}`);
  for (const check of requiredStatusChecks) if (pull.checks?.[check] !== "success") reasons.push(`status_check_not_success:${check}`);

  return {
    allowed: reasons.length === 0,
    reasons: [...new Set(reasons)],
    policyIds,
    requiredApprovals,
    approvals: nonAuthorApprovals.length,
    requiredStatusChecks: [...requiredStatusChecks].sort(),
  };
}

function validateIssueForm(raw, existing = null) {
  const body = clone(asArray(raw.body ?? existing?.body));
  const ids = new Set();
  for (const component of body) {
    if (!FORM_COMPONENT_TYPES.has(component.type)) throw new Error(`unsupported issue-form component: ${component.type}`);
    component.id = cleanString(component.id, 80);
    if (!component.id || ids.has(component.id)) throw new Error("issue-form component ids must be unique and non-empty");
    ids.add(component.id);
    if (component.type !== "markdown" && !cleanString(component.label, 160)) throw new Error(`label is required for ${component.id}`);
    if (["dropdown", "checkboxes"].includes(component.type) && !asArray(component.options).length) throw new Error(`options are required for ${component.id}`);
  }
  return body;
}

function issueDescription(form, values) {
  return form.body
    .filter((component) => component.type !== "markdown")
    .map((component) => {
      const raw = values[component.id];
      const value = Array.isArray(raw) ? raw.map((entry) => `- [x] ${entry}`).join("\n") : String(raw ?? "");
      return `### ${component.label}\n\n${value || "_No response_"}`;
    })
    .join("\n\n");
}

function rewriteRepoReferences(state, oldId, newId) {
  for (const issue of state.issues) {
    if (issue.repoId !== oldId) continue;
    issue.repoId = newId;
    issue.id = `${newId}#${issue.number}`;
  }
  for (const pull of state.pullRequests) {
    if (pull.repoId !== oldId) continue;
    pull.repoId = newId;
    pull.id = `${newId}#${pull.number}`;
  }
  for (const collectionName of ["workflows", "environments", "rulesets", "issueForms"]) {
    for (const entry of state[collectionName]) {
      if (entry.repoId !== oldId) continue;
      entry.repoId = newId;
      if (entry.id.startsWith(`${oldId}:`)) entry.id = `${newId}:${entry.id.slice(oldId.length + 1)}`;
    }
  }
  for (const run of state.workflowRuns) {
    if (run.repoId === oldId) run.repoId = newId;
    if (run.workflowId.startsWith(`${oldId}:`)) run.workflowId = `${newId}:${run.workflowId.slice(oldId.length + 1)}`;
    if (run.id.startsWith(`${oldId}:`)) run.id = `${newId}:${run.id.slice(oldId.length + 1)}`;
  }
  for (const relation of state.repositoryRelations) {
    if (relation.repoId === oldId) relation.repoId = newId;
    if (relation.id.startsWith(`${oldId}:`)) relation.id = `${newId}:${relation.id.slice(oldId.length + 1)}`;
  }
}

function removeRepositoryData(state, repoId) {
  const collections = ["issues", "pullRequests", "workflows", "workflowRuns", "environments", "rulesets", "issueForms", "repositoryRelations"];
  for (const collectionName of collections) state[collectionName] = state[collectionName].filter((entry) => entry.repoId !== repoId);
}

function actorCanManageOrg(state, organization, actor) {
  return isOrganizationOwner(state, organization, actor);
}

export function executeEnterpriseCommand(state, command, context = {}) {
  normalizeEnterpriseState(state);
  const { type, payload = {} } = command || {};
  const actor = cleanString(context.actor || "anonymous", 160);
  const integrity = verifyEnterpriseState(state);
  if (type === "audit.verify") return { ok: true, item: integrity };
  if (!integrity.valid) return fail("integrity", "audit chain integrity failed; mutations are blocked", integrity);

  try {
    if (type === "repository.star" || type === "repository.watch") {
      const repo = findRepository(state, payload.repoId);
      if (!repo) return fail("not_found", "repository not found");
      if (!actor || actor === "anonymous") return fail("authentication_required", "sign in to update repository subscriptions");
      const id = `${repo.id}:${actor}`;
      let relation = state.repositoryRelations.find((entry) => entry.id === id);
      if (!relation) {
        relation = { id, repoId: repo.id, username: actor, starred: false, watching: "participating" };
        state.repositoryRelations.push(relation);
      }
      if (type === "repository.star") relation.starred = Boolean(payload.starred);
      else relation.watching = ["all", "participating", "ignore"].includes(payload.watching) ? payload.watching : "participating";
      return { ok: true, item: relation };
    }

    if (type === "repository.transfer") {
      const repo = findRepository(state, payload.repoId);
      if (!repo) return fail("not_found", "repository not found");
      if (!canAdminRepository(state, repo, actor)) return fail("forbidden", "repository administration is required");
      if (payload.confirmName !== repo.name) return fail("confirmation_required", "type the repository name to confirm transfer");
      const targetOwner = cleanString(payload.targetOwner, 160);
      if (!targetOwner || (!findOrganization(state, targetOwner) && !state.accounts.some((entry) => entry.username === targetOwner))) {
        return fail("target_not_found", "target owner not found");
      }
      const oldId = repo.id;
      const newId = `${targetOwner}/${repo.name}`;
      if (findRepository(state, newId)) return fail("exists", "target repository already exists");
      repo.owner = targetOwner;
      repo.id = newId;
      rewriteRepoReferences(state, oldId, newId);
      return { ok: true, item: repo, previousId: oldId };
    }

    if (type === "repository.delete") {
      const repo = findRepository(state, payload.repoId);
      if (!repo) return fail("not_found", "repository not found");
      if (!canAdminRepository(state, repo, actor)) return fail("forbidden", "repository administration is required");
      if (payload.confirmName !== repo.name) return fail("confirmation_required", "type the repository name to confirm deletion");
      state.repositories = state.repositories.filter((entry) => entry.id !== repo.id);
      removeRepositoryData(state, repo.id);
      return { ok: true, item: { id: repo.id, deleted: true } };
    }

    if (type === "pullRequest.evaluate" || type === "pullRequest.merge") {
      const pull = state.pullRequests.find((entry) => entry.id === payload.id);
      if (!pull) return fail("not_found", "pull request not found");
      const repo = findRepository(state, pull.repoId);
      const evaluation = evaluatePullRequestPolicy(state, pull, actor);
      if (type === "pullRequest.evaluate") return { ok: true, item: evaluation };
      if (!canMaintainRepository(state, repo, actor)) return fail("forbidden", "repository Maintain permission is required");
      if (!evaluation.allowed) return fail("policy_denied", "pull request does not satisfy merge policy", evaluation);
      const base = repo.branches.find((branch) => branch.name === pull.base);
      const head = repo.branches.find((branch) => branch.name === pull.head);
      if (!base || !head) return fail("branch_not_found", "pull-request base or head branch no longer exists");
      const changedFiles = asArray(pull.files).length ? pull.files : [...new Set([...Object.keys(base.files || {}), ...Object.keys(head.files || {})])].filter((file) => base.files?.[file] !== head.files?.[file]);
      base.files = { ...(base.files || {}), ...(head.files || {}) };
      const mergeCommit = {
        id: `merge-${pull.number}-${randomUUID()}`,
        message: `Merge pull request #${pull.number}: ${pull.title}`,
        author: actor,
        timestamp: new Date().toISOString(),
        changedFiles,
      };
      repo.commits = [mergeCommit, ...asArray(repo.commits)];
      pull.state = "merged";
      pull.mergedBy = actor;
      pull.mergedAt = mergeCommit.timestamp;
      pull.mergeCommit = mergeCommit.id;
      return { ok: true, item: pull, evaluation, mergeCommit };
    }

    if (type === "workflow.upsert") {
      const raw = payload.item || payload;
      const existing = raw.id ? state.workflows.find((entry) => entry.id === raw.id) : null;
      const item = normalizeWorkflow(state, raw, existing);
      if (!canAdminRepository(state, findRepository(state, item.repoId), actor)) return fail("forbidden", "repository administration is required");
      const duplicate = state.workflows.find((entry) => entry.repoId === item.repoId && entry.name === item.name && entry.id !== item.id);
      if (duplicate) return fail("exists", "workflow name already exists");
      if (existing) Object.assign(existing, item);
      else state.workflows.push(item);
      return { ok: true, item: existing || item };
    }

    if (type === "workflow.toggle") {
      const item = state.workflows.find((entry) => entry.id === payload.id);
      if (!item) return fail("not_found", "workflow not found");
      if (!canAdminRepository(state, findRepository(state, item.repoId), actor)) return fail("forbidden", "repository administration is required");
      item.enabled = Boolean(payload.enabled);
      item.updatedAt = new Date().toISOString();
      return { ok: true, item };
    }

    if (type === "workflow.dispatch") {
      const workflow = state.workflows.find((entry) => entry.id === payload.workflowId);
      if (!workflow) return fail("not_found", "workflow not found");
      if (!canWriteRepository(state, findRepository(state, workflow.repoId), actor)) return fail("forbidden", "repository write permission is required");
      return { ok: true, item: createWorkflowRun(state, workflow, payload, actor) };
    }

    if (type === "workflow.approve_environment") {
      const run = state.workflowRuns.find((entry) => entry.id === payload.runId);
      const job = run?.jobs.find((entry) => entry.id === payload.jobId && entry.status === "waiting");
      if (!run || !job) return fail("not_found", "waiting workflow job not found");
      const environment = state.environments.find((entry) => entry.repoId === run.repoId && entry.name === job.environment);
      if (!environment) return fail("not_found", "environment not found");
      if (environment.requiredReviewers.length && !environment.requiredReviewers.includes(actor)) return fail("forbidden", "actor is not an environment reviewer");
      if (environment.preventSelfReview && run.actor === actor) return fail("self_review_forbidden", "the run initiator cannot approve this deployment");
      run.approvals.push({ jobId: job.id, environment: environment.name, actor, timestamp: new Date().toISOString() });
      job.status = "queued";
      return { ok: true, item: advanceRun(state, run) };
    }

    if (type === "workflow.cancel") {
      const run = state.workflowRuns.find((entry) => entry.id === payload.runId);
      if (!run) return fail("not_found", "workflow run not found");
      if (!canWriteRepository(state, findRepository(state, run.repoId), actor)) return fail("forbidden", "repository write permission is required");
      for (const job of run.jobs) if (!TERMINAL_JOB_STATES.has(job.status)) job.status = "cancelled";
      run.status = "cancelled";
      run.completedAt = new Date().toISOString();
      synchronizePullRequestChecks(state, run);
      return { ok: true, item: run };
    }

    if (type === "workflow.rerun") {
      const original = state.workflowRuns.find((entry) => entry.id === payload.runId);
      const workflow = original && state.workflows.find((entry) => entry.id === original.workflowId);
      if (!original || !workflow) return fail("not_found", "workflow run not found");
      if (!canWriteRepository(state, findRepository(state, workflow.repoId), actor)) return fail("forbidden", "repository write permission is required");
      return { ok: true, item: createWorkflowRun(state, workflow, { inputs: original.inputs, ref: original.ref, event: "workflow_rerun", pullRequestId: original.pullRequestId }, actor) };
    }

    if (type === "environment.upsert") {
      const raw = payload.item || payload;
      const repo = findRepository(state, raw.repoId);
      if (!repo) return fail("not_found", "repository not found");
      if (!canAdminRepository(state, repo, actor)) return fail("forbidden", "repository administration is required");
      const name = cleanString(raw.name, 100);
      if (!name) return fail("validation", "environment name is required");
      const id = cleanString(raw.id || `${repo.id}:${name}`, 320);
      const existing = state.environments.find((entry) => entry.id === id);
      const item = {
        id,
        repoId: repo.id,
        name,
        requiredReviewers: [...new Set(asArray(raw.requiredReviewers).map((entry) => cleanString(entry, 160)).filter(Boolean))],
        preventSelfReview: Boolean(raw.preventSelfReview),
        waitTimerMinutes: Math.max(0, Math.min(43_200, Number(raw.waitTimerMinutes) || 0)),
        protectedBranchesOnly: Boolean(raw.protectedBranchesOnly),
        secretNames: [...new Set(asArray(raw.secretNames).map((entry) => cleanString(entry, 160)).filter(Boolean))],
      };
      if (existing) Object.assign(existing, item);
      else state.environments.push(item);
      return { ok: true, item: existing || item };
    }

    if (type === "ruleset.upsert") {
      const raw = payload.item || payload;
      const existing = raw.id ? state.rulesets.find((entry) => entry.id === raw.id) : null;
      const item = normalizeRuleset(state, raw, existing);
      if (!canAdminRepository(state, findRepository(state, item.repoId), actor)) return fail("forbidden", "repository administration is required");
      const duplicate = state.rulesets.find((entry) => entry.repoId === item.repoId && entry.name === item.name && entry.id !== item.id);
      if (duplicate) return fail("exists", "ruleset name already exists");
      if (existing) Object.assign(existing, item);
      else state.rulesets.push(item);
      return { ok: true, item: existing || item };
    }

    if (type === "ruleset.evaluate") {
      const repoRulesets = state.rulesets.filter((entry) => entry.repoId === payload.repoId && entry.enforcement === "active");
      const requiredOwners = new Set();
      for (const ruleset of repoRulesets) {
        for (const path of asArray(payload.paths)) {
          for (const entry of ruleset.codeowners) if (globMatches(entry.pattern, path)) entry.owners.forEach((owner) => requiredOwners.add(owner));
        }
      }
      return {
        ok: true,
        evaluation: {
          protected: repoRulesets.length > 0,
          rulesetIds: repoRulesets.map((entry) => entry.id),
          requiredOwners: [...requiredOwners].sort(),
          bypassAllowed: repoRulesets.some((entry) => entry.bypassActors.includes(actor)),
          requiredStatusChecks: [...new Set(repoRulesets.flatMap((entry) => entry.requiredStatusChecks))].sort(),
          requiredApprovals: Math.max(0, ...repoRulesets.map((entry) => entry.requiredApprovals)),
        },
      };
    }

    if (type === "ruleset.delete") {
      const item = state.rulesets.find((entry) => entry.id === payload.id);
      if (!item) return fail("not_found", "ruleset not found");
      if (!canAdminRepository(state, findRepository(state, item.repoId), actor)) return fail("forbidden", "repository administration is required");
      state.rulesets = state.rulesets.filter((entry) => entry.id !== item.id);
      return { ok: true, item: { id: item.id, deleted: true } };
    }

    if (type === "issueForm.upsert") {
      const raw = payload.item || payload;
      const repo = findRepository(state, raw.repoId);
      if (!repo) return fail("not_found", "repository not found");
      if (!canAdminRepository(state, repo, actor)) return fail("forbidden", "repository administration is required");
      const existing = raw.id ? state.issueForms.find((entry) => entry.id === raw.id) : null;
      const name = cleanString(raw.name || existing?.name, 120);
      if (!name) return fail("validation", "issue-form name is required");
      const item = {
        id: cleanString(raw.id || existing?.id || `${repo.id}:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`, 320),
        repoId: repo.id,
        name,
        description: cleanString(raw.description ?? existing?.description, 500),
        titlePrefix: cleanString(raw.titlePrefix ?? existing?.titlePrefix, 80),
        labels: asArray(raw.labels ?? existing?.labels).map((entry) => cleanString(entry, 100)).filter(Boolean),
        body: validateIssueForm(raw, existing),
      };
      if (existing) Object.assign(existing, item);
      else state.issueForms.push(item);
      return { ok: true, item: existing || item };
    }

    if (type === "issueForm.submit") {
      const form = state.issueForms.find((entry) => entry.id === payload.formId);
      if (!form) return fail("not_found", "issue form not found");
      if (!actor || actor === "anonymous") return fail("authentication_required", "sign in to submit an issue form");
      const values = payload.values && typeof payload.values === "object" ? payload.values : {};
      for (const component of form.body) {
        if (!component.required) continue;
        const value = values[component.id];
        if (value === undefined || value === "" || (Array.isArray(value) && !value.length)) return fail("validation", `${component.label} is required`, { field: component.id });
      }
      const number = Math.max(0, ...state.issues.filter((entry) => entry.repoId === form.repoId).map((entry) => Number(entry.number) || 0)) + 1;
      const title = `${form.titlePrefix}${cleanString(payload.title, 240)}`.trim();
      if (!title) return fail("validation", "issue title is required");
      const item = {
        id: `${form.repoId}#${number}`,
        repoId: form.repoId,
        number,
        title,
        description: issueDescription(form, values),
        state: "open",
        author: actor,
        editable: true,
        assignees: [],
        labels: clone(form.labels),
        milestone: "",
        comments: [],
        formId: form.id,
        formData: clone(values),
      };
      state.issues.push(item);
      return { ok: true, item };
    }

    if (type === "identityProvider.upsert") {
      const organization = cleanString(payload.organization, 160);
      if (!findOrganization(state, organization)) return fail("not_found", "organization not found");
      if (!actorCanManageOrg(state, organization, actor)) return fail("forbidden", "organization owner role is required");
      const id = `${organization}:saml`;
      const existing = state.identityProviders.find((entry) => entry.id === id);
      const item = {
        id,
        organization,
        protocol: "SAML",
        enabled: Boolean(payload.enabled),
        signOnUrl: cleanString(payload.signOnUrl, 500),
        issuer: cleanString(payload.issuer, 300),
        certificateFingerprint: payload.certificate ? digest(String(payload.certificate)) : existing?.certificateFingerprint || "",
        enforceSso: Boolean(payload.enforceSso),
        scimEnabled: Boolean(payload.scimEnabled),
      };
      if (existing) Object.assign(existing, item);
      else state.identityProviders.push(item);
      return { ok: true, item: existing || item };
    }

    if (type === "scim.provision") {
      const organization = cleanString(payload.organization, 160);
      if (!actorCanManageOrg(state, organization, actor)) return fail("forbidden", "organization owner role is required");
      const provider = state.identityProviders.find((entry) => entry.organization === organization && entry.scimEnabled);
      if (!provider) return fail("scim_disabled", "SCIM must be enabled before provisioning");
      const userName = cleanString(payload.userName, 160);
      if (!userName) return fail("validation", "SCIM userName is required");
      const id = `${organization}:${userName}`;
      let item = state.scimUsers.find((entry) => entry.id === id);
      const next = { id, organization, userName, displayName: cleanString(payload.displayName || userName, 200), active: payload.active !== false, groups: asArray(payload.groups).map((entry) => cleanString(entry, 160)).filter(Boolean), externalId: cleanString(payload.externalId, 200) };
      if (item) Object.assign(item, next);
      else {
        item = next;
        state.scimUsers.push(item);
      }
      if (!state.accounts.some((entry) => entry.username === userName)) state.accounts.push({ id: userName, username: userName, email: cleanString(payload.email || `${userName}@example.test`, 240), password: randomUUID(), managedByScim: true });
      const org = findOrganization(state, organization);
      if (!org.members.some((entry) => entry.username === userName)) org.members.push({ username: userName, role: "Member", source: "SCIM" });
      return { ok: true, item };
    }

    if (type === "scim.deactivate") {
      const item = state.scimUsers.find((entry) => entry.id === payload.id);
      if (!item) return fail("not_found", "SCIM user not found");
      if (!actorCanManageOrg(state, item.organization, actor)) return fail("forbidden", "organization owner role is required");
      item.active = false;
      const org = findOrganization(state, item.organization);
      org.members = org.members.filter((entry) => entry.username !== item.userName);
      return { ok: true, item };
    }

    if (type === "dataPolicy.upsert") {
      const organization = cleanString(payload.organization || payload.item?.organization, 160);
      if (!actorCanManageOrg(state, organization, actor)) return fail("forbidden", "organization owner role is required");
      const raw = payload.item || payload;
      const name = cleanString(raw.name, 120);
      if (!name) return fail("validation", "policy name is required");
      const id = cleanString(raw.id || `${organization}:${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`, 320);
      const existing = state.dataPolicies.find((entry) => entry.id === id);
      const item = {
        id,
        organization,
        name,
        dataset: cleanString(raw.dataset, 160),
        subjects: asArray(raw.subjects).map((entry) => cleanString(entry, 160)).filter(Boolean),
        rowField: cleanString(raw.rowField, 120),
        allowedRowValues: asArray(raw.allowedRowValues).map((entry) => cleanString(entry, 160)),
        hiddenFields: asArray(raw.hiddenFields).map((entry) => cleanString(entry, 120)).filter(Boolean),
        readOnlyFields: asArray(raw.readOnlyFields).map((entry) => cleanString(entry, 120)).filter(Boolean),
      };
      if (existing) Object.assign(existing, item);
      else state.dataPolicies.push(item);
      return { ok: true, item: existing || item };
    }

    if (type === "dataPolicy.evaluate") {
      const rows = asArray(payload.rows);
      const policies = state.dataPolicies.filter((entry) => entry.organization === payload.organization && (!entry.subjects.length || entry.subjects.includes(actor)));
      const visibleRows = rows.filter((row) => policies.every((policy) => !policy.rowField || policy.allowedRowValues.includes(String(row?.[policy.rowField] ?? ""))));
      const hiddenFields = new Set(policies.flatMap((entry) => entry.hiddenFields));
      return {
        ok: true,
        item: visibleRows.map((row) => Object.fromEntries(Object.entries(row || {}).filter(([field]) => !hiddenFields.has(field)))),
        policyIds: policies.map((entry) => entry.id),
        readOnlyFields: [...new Set(policies.flatMap((entry) => entry.readOnlyFields))],
      };
    }

    return null;
  } catch (error) {
    return fail("validation", error.message);
  }
}

export function shouldAuditCommand(type) {
  return typeof type === "string" && !["audit.verify", "dataPolicy.evaluate", "pullRequest.evaluate", "ruleset.evaluate"].includes(type);
}
