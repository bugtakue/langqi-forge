function decode(value) {
  return decodeURIComponent(value || "");
}

function parseList(value) {
  return String(value || "")
    .split(/[\n,]/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function resultMessage(ctx, result, success) {
  const text = result.ok ? success : result.message || result.code || "The operation could not be completed.";
  return `<div class="${result.ok ? "success" : "error"}">${ctx.escapeHtml(text)}</div>`;
}

function repository(ctx, owner, name) {
  return ctx.state.repositories.find((entry) => entry.owner === decode(owner) && entry.name === decode(name));
}

function organization(ctx, name) {
  return ctx.state.organizations.find((entry) => entry.name === decode(name));
}

function repositoryShell(ctx, repo, title, content) {
  ctx.layout(`<section class="stack"><h1>${ctx.escapeHtml(title)}</h1>${ctx.repoTabs(repo)}${content}</section>`);
}

function actionsView(ctx, repo) {
  if (!ctx.canViewRepository(repo)) return false;
  const workflows = (ctx.state.workflows || []).filter((entry) => entry.repoId === repo.id);
  const runs = (ctx.state.workflowRuns || []).filter((entry) => entry.repoId === repo.id).slice().reverse().slice(0, 12);
  repositoryShell(
    ctx,
    repo,
    "Actions",
    `<div class="toolbar"><p class="muted">Workflow automation with DAG jobs, schedules, and protected environments.</p>${ctx.canAdminRepository(repo) ? ctx.link(`/${repo.owner}/${repo.name}/actions/new`, "New workflow", 'class="btn"') : ""}</div>
     <div class="split">
       <nav class="side-nav" aria-label="Workflows">${workflows.map((workflow) => ctx.link(`/${repo.owner}/${repo.name}/actions/workflows/${encodeURIComponent(workflow.id)}`, workflow.name)).join("") || "<p>No workflows.</p>"}</nav>
       <section class="stack"><h2>Recent workflow runs</h2>${runs.map((run) => `<article class="card"><div class="toolbar"><strong>${ctx.link(`/${repo.owner}/${repo.name}/actions/runs/${encodeURIComponent(run.id)}`, `Run #${run.number}`)}</strong><span class="status-dot ${ctx.escapeHtml(run.status)}">${ctx.escapeHtml(run.status)}</span></div><p>${ctx.escapeHtml(run.workflowId)} · ${ctx.escapeHtml(run.ref)}</p></article>`).join("") || '<div class="panel">No workflow runs yet.</div>'}</section>
     </div>`,
  );
  return true;
}

function parseJobs(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [id, needs = "", steps = "", environment = ""] = line.split("|");
      return {
        id: id.trim(),
        name: id.trim(),
        needs: parseList(needs),
        steps: steps.split(";").map((entry) => entry.trim()).filter(Boolean),
        environment: environment.trim(),
        runsOn: "ubuntu-latest",
      };
    });
}

function workflowEditorView(ctx, repo) {
  if (ctx.authRequired()) return true;
  if (!ctx.canAdminRepository(repo)) {
    repositoryShell(ctx, repo, "New workflow", '<div class="error">Repository administrator permission is required.</div>');
    return true;
  }
  repositoryShell(
    ctx,
    repo,
    "Create workflow",
    `<div id="enterprise-message"></div><form class="panel stack" data-form="workflow-editor">
       <div class="form-row"><label for="workflow-name">Workflow name</label><input id="workflow-name" name="name" required placeholder="Build and deploy" /></div>
       <label class="checkbox-row"><input type="checkbox" name="push" checked /> Run on push</label>
       <label class="checkbox-row"><input type="checkbox" name="pullRequest" checked /> Run on pull requests</label>
       <label class="checkbox-row"><input type="checkbox" name="manual" checked /> Allow manual dispatch</label>
       <div class="form-row"><label for="workflow-cron">Cron schedule (optional, UTC)</label><input id="workflow-cron" name="cron" placeholder="0 6 * * 1-5" /></div>
       <div class="form-row"><label for="workflow-jobs">Jobs, one per line: id | dependencies | steps separated by ; | environment</label><textarea id="workflow-jobs" name="jobs" required>test||npm ci;npm test|
package|test|npm run build|
deploy|package|deploy|production</textarea></div>
       <p class="muted">Dependencies form a directed acyclic graph. Cycles and unknown job IDs fail closed.</p>
       <button class="btn" type="submit">Create workflow</button>
     </form>`,
  );
  ctx.root.querySelector('[data-form="workflow-editor"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await ctx.command("workflow.upsert", {
      repoId: repo.id,
      name: data.name,
      enabled: true,
      triggers: {
        push: Boolean(data.push),
        pullRequest: Boolean(data.pullRequest),
        workflowDispatch: data.manual ? { inputs: [] } : null,
        schedules: data.cron ? [{ cron: data.cron, timezone: "UTC" }] : [],
      },
      jobs: parseJobs(data.jobs),
    });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Workflow created.");
    if (result.ok) ctx.navigate(`/${repo.owner}/${repo.name}/actions/workflows/${encodeURIComponent(result.item.id)}`);
  });
  return true;
}

function workflowView(ctx, repo, workflowId) {
  const workflow = (ctx.state.workflows || []).find((entry) => entry.id === workflowId && entry.repoId === repo.id);
  if (!workflow) return false;
  const inputDefinitions = workflow.triggers?.workflowDispatch?.inputs || [];
  const schedules = workflow.triggers?.schedules || [];
  repositoryShell(
    ctx,
    repo,
    workflow.name,
    `<div id="enterprise-message"></div>
     <div class="grid"><article class="card"><h2>Triggers</h2><p>Push: ${workflow.triggers?.push ? "enabled" : "disabled"}</p><p>Pull request: ${workflow.triggers?.pullRequest ? "enabled" : "disabled"}</p>${schedules.map((entry) => `<p>Schedule: <code>${ctx.escapeHtml(entry.cron)}</code> ${ctx.escapeHtml(entry.timezone)}</p>`).join("") || "<p>No schedule.</p>"}</article><article class="card"><h2>Job graph</h2>${workflow.jobs.map((job) => `<p><strong>${ctx.escapeHtml(job.id)}</strong>${job.needs.length ? ` ← ${ctx.escapeHtml(job.needs.join(", "))}` : ""}${job.environment ? ` · environment ${ctx.escapeHtml(job.environment)}` : ""}</p>`).join("")}</article></div>
     ${workflow.triggers?.workflowDispatch ? `<form class="panel stack" data-form="workflow-dispatch"><h2>Run workflow</h2><div class="form-row"><label for="workflow-ref">Branch or tag</label><select id="workflow-ref" name="ref">${repo.branches.map((branch) => `<option value="${ctx.escapeHtml(branch.name)}">${ctx.escapeHtml(branch.name)}</option>`).join("")}</select></div>${inputDefinitions.map((input) => input.type === "boolean" ? `<label class="checkbox-row"><input type="checkbox" name="${ctx.escapeHtml(input.id)}" ${input.default ? "checked" : ""} /> ${ctx.escapeHtml(input.label || input.id)}${input.required ? " (required)" : ""}</label>` : `<div class="form-row"><label for="workflow-input-${ctx.escapeHtml(input.id)}">${ctx.escapeHtml(input.label || input.id)}</label><input id="workflow-input-${ctx.escapeHtml(input.id)}" name="${ctx.escapeHtml(input.id)}" ${input.required ? "required" : ""} value="${ctx.escapeHtml(input.default || "")}" /></div>`).join("")}<button class="btn" type="submit" ${workflow.enabled ? "" : "disabled"}>Run workflow</button></form>` : '<div class="panel">Manual dispatch is not configured.</div>'}
     ${ctx.canAdminRepository(repo) ? `<button class="btn secondary" type="button" data-action="toggle-workflow">${workflow.enabled ? "Disable workflow" : "Enable workflow"}</button>` : ""}`,
  );
  ctx.root.querySelector('[data-form="workflow-dispatch"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const inputs = Object.fromEntries(inputDefinitions.map((input) => [input.id, input.type === "boolean" ? form.has(input.id) : form.get(input.id)]));
    const result = await ctx.command("workflow.dispatch", { workflowId: workflow.id, ref: form.get("ref"), inputs });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Workflow run created.");
    if (result.ok) ctx.navigate(`/${repo.owner}/${repo.name}/actions/runs/${encodeURIComponent(result.item.id)}`);
  });
  ctx.root.querySelector('[data-action="toggle-workflow"]')?.addEventListener("click", async () => {
    await ctx.command("workflow.toggle", { id: workflow.id, enabled: !workflow.enabled });
    ctx.render();
  });
  return true;
}

function workflowRunView(ctx, repo, runId) {
  const run = (ctx.state.workflowRuns || []).find((entry) => entry.id === runId && entry.repoId === repo.id);
  if (!run) return false;
  repositoryShell(
    ctx,
    repo,
    `Workflow run #${run.number}`,
    `<div id="enterprise-message"></div><div class="panel stack"><div class="toolbar"><span class="status-dot ${ctx.escapeHtml(run.status)}">${ctx.escapeHtml(run.status)}</span><span>${ctx.escapeHtml(run.event)} on ${ctx.escapeHtml(run.ref)}</span></div><p>Triggered by ${ctx.escapeHtml(run.actor)}</p></div>
     <section class="stack"><h2>Jobs</h2>${run.jobs.map((job) => `<article class="card stack"><div class="toolbar"><strong>${ctx.escapeHtml(job.name)}</strong><span class="status-dot ${ctx.escapeHtml(job.status)}">${ctx.escapeHtml(job.status)}</span></div>${job.environment ? `<p>Environment: ${ctx.escapeHtml(job.environment)}</p>` : ""}${job.logs.length ? `<pre>${ctx.escapeHtml(job.logs.join("\n"))}</pre>` : ""}${job.status === "waiting" ? `<button class="btn" type="button" data-approve-job="${ctx.escapeHtml(job.id)}">Approve deployment</button>` : ""}</article>`).join("")}</section>
     <div class="toolbar">${!["success", "failure", "cancelled"].includes(run.status) ? '<button class="btn danger" type="button" data-action="cancel-run">Cancel workflow</button>' : ""}<button class="btn secondary" type="button" data-action="rerun">Re-run all jobs</button></div>`,
  );
  ctx.root.querySelectorAll("[data-approve-job]").forEach((button) => button.addEventListener("click", async () => {
    const result = await ctx.command("workflow.approve_environment", { runId: run.id, jobId: button.dataset.approveJob });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Deployment approved.");
    if (result.ok) ctx.render();
  }));
  ctx.root.querySelector('[data-action="cancel-run"]')?.addEventListener("click", async () => {
    await ctx.command("workflow.cancel", { runId: run.id });
    ctx.render();
  });
  ctx.root.querySelector('[data-action="rerun"]').addEventListener("click", async () => {
    const result = await ctx.command("workflow.rerun", { runId: run.id });
    if (result.ok) ctx.navigate(`/${repo.owner}/${repo.name}/actions/runs/${encodeURIComponent(result.item.id)}`);
  });
  return true;
}

function settingsNavigation(ctx, repo) {
  return `<nav class="side-nav">${ctx.link(`/${repo.owner}/${repo.name}/settings`, "General")} ${ctx.link(`/${repo.owner}/${repo.name}/settings/access`, "Manage access")} ${ctx.link(`/${repo.owner}/${repo.name}/settings/branches`, "Branches")} ${ctx.link(`/${repo.owner}/${repo.name}/settings/rules`, "Rulesets")} ${ctx.link(`/${repo.owner}/${repo.name}/settings/environments`, "Environments")} ${ctx.link(`/${repo.owner}/${repo.name}/settings/repository-lifecycle`, "Danger zone")}</nav>`;
}

function rulesetsView(ctx, repo) {
  if (ctx.authRequired()) return true;
  const rulesets = (ctx.state.rulesets || []).filter((entry) => entry.repoId === repo.id);
  ctx.layout(`<div class="split">${settingsNavigation(ctx, repo)}<section class="stack"><h1>Repository rulesets</h1><p class="muted">Layer branch policy, status checks, CODEOWNERS, and bypass controls.</p><div id="enterprise-message"></div>${rulesets.map((ruleset) => `<article class="card stack"><div class="toolbar"><h2>${ctx.escapeHtml(ruleset.name)}</h2><span class="badge">${ctx.escapeHtml(ruleset.enforcement)}</span></div><p>${ruleset.requiredApprovals} approval(s) · checks: ${ctx.escapeHtml(ruleset.requiredStatusChecks.join(", ") || "none")}</p><pre>${ctx.escapeHtml(ruleset.codeownersText || "# No CODEOWNERS entries")}</pre></article>`).join("") || '<div class="panel">No rulesets.</div>'}${ctx.canAdminRepository(repo) ? `<form class="panel stack" data-form="ruleset"><h2>New ruleset</h2><div class="form-row"><label for="ruleset-name">Ruleset name</label><input id="ruleset-name" name="name" required /></div><div class="form-row"><label for="ruleset-include">Target branches</label><input id="ruleset-include" name="include" value="refs/heads/main" /></div><div class="form-row"><label for="ruleset-checks">Required status checks</label><input id="ruleset-checks" name="checks" value="test" /></div><div class="form-row"><label for="ruleset-approvals">Required approvals</label><input id="ruleset-approvals" name="approvals" type="number" min="0" max="10" value="1" /></div><label class="checkbox-row"><input type="checkbox" name="codeOwnerReview" checked /> Require CODEOWNER review</label><div class="form-row"><label for="codeowners">CODEOWNERS</label><textarea id="codeowners" name="codeowners" placeholder="/src/ @team/backend"></textarea></div><div class="form-row"><label for="bypass-actors">Bypass actors</label><input id="bypass-actors" name="bypassActors" placeholder="@release-manager" /></div><button class="btn" type="submit">Create ruleset</button></form>` : '<div class="error">Repository administrator permission is required.</div>'}</section></div>`);
  ctx.root.querySelector('[data-form="ruleset"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await ctx.command("ruleset.upsert", { repoId: repo.id, name: data.name, enforcement: "active", include: parseList(data.include), requiredStatusChecks: parseList(data.checks), requiredApprovals: Number(data.approvals), requireCodeOwnerReview: Boolean(data.codeOwnerReview), blockForcePush: true, bypassActors: parseList(data.bypassActors), codeownersText: data.codeowners });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Ruleset created.");
    if (result.ok) ctx.render();
  });
  return true;
}

function environmentsView(ctx, repo) {
  if (ctx.authRequired()) return true;
  const environments = (ctx.state.environments || []).filter((entry) => entry.repoId === repo.id);
  ctx.layout(`<div class="split">${settingsNavigation(ctx, repo)}<section class="stack"><h1>Deployment environments</h1><div id="enterprise-message"></div>${environments.map((environment) => `<article class="card"><h2>${ctx.escapeHtml(environment.name)}</h2><p>Required reviewers: ${ctx.escapeHtml(environment.requiredReviewers.join(", ") || "none")}</p><p>Secrets: ${ctx.escapeHtml(environment.secretNames.join(", ") || "none")}</p></article>`).join("") || '<div class="panel">No environments.</div>'}${ctx.canAdminRepository(repo) ? `<form class="panel stack" data-form="environment"><h2>New environment</h2><div class="form-row"><label for="environment-name">Name</label><input id="environment-name" name="name" required /></div><div class="form-row"><label for="environment-reviewers">Required reviewers</label><input id="environment-reviewers" name="reviewers" /></div><label class="checkbox-row"><input type="checkbox" name="preventSelfReview" checked /> Prevent self-review</label><label class="checkbox-row"><input type="checkbox" name="protectedBranchesOnly" checked /> Protected branches only</label><div class="form-row"><label for="environment-secrets">Secret names</label><input id="environment-secrets" name="secrets" /></div><button class="btn" type="submit">Configure environment</button></form>` : ""}</section></div>`);
  ctx.root.querySelector('[data-form="environment"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await ctx.command("environment.upsert", { repoId: repo.id, name: data.name, requiredReviewers: parseList(data.reviewers), preventSelfReview: Boolean(data.preventSelfReview), protectedBranchesOnly: Boolean(data.protectedBranchesOnly), secretNames: parseList(data.secrets) });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Environment configured.");
    if (result.ok) ctx.render();
  });
  return true;
}

function lifecycleView(ctx, repo) {
  if (ctx.authRequired()) return true;
  ctx.layout(`<div class="split">${settingsNavigation(ctx, repo)}<section class="stack"><h1>Danger zone</h1><div id="enterprise-message"></div><form class="panel stack" data-form="transfer-repository"><h2>Transfer repository</h2><div class="form-row"><label for="target-owner">New owner</label><input id="target-owner" name="targetOwner" required /></div><div class="form-row"><label for="transfer-confirm">Type ${ctx.escapeHtml(repo.name)} to confirm</label><input id="transfer-confirm" name="confirmName" required /></div><button class="btn danger" type="submit">Transfer repository</button></form><form class="panel danger-panel stack" data-form="delete-repository"><h2>Delete repository</h2><p>This removes the local repository and its related workflow, issue, pull request, and policy records.</p><div class="form-row"><label for="delete-confirm">Type ${ctx.escapeHtml(repo.name)} to confirm</label><input id="delete-confirm" name="confirmName" required /></div><button class="btn danger" type="submit">Delete this repository</button></form></section></div>`);
  ctx.root.querySelector('[data-form="transfer-repository"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await ctx.command("repository.transfer", { repoId: repo.id, ...data });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Repository transferred.");
    if (result.ok) ctx.navigate(`/${result.item.owner}/${result.item.name}`);
  });
  ctx.root.querySelector('[data-form="delete-repository"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await ctx.command("repository.delete", { repoId: repo.id, ...data });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Repository deleted.");
    if (result.ok) ctx.navigate("/");
  });
  return true;
}

function issueFormsView(ctx, repo) {
  if (ctx.authRequired()) return true;
  const forms = (ctx.state.issueForms || []).filter((entry) => entry.repoId === repo.id);
  repositoryShell(ctx, repo, "Issue forms", `<div id="enterprise-message"></div>${forms.map((form) => `<article class="card"><h2>${ctx.escapeHtml(form.name)}</h2><p>${ctx.escapeHtml(form.description)}</p>${ctx.link(`/${repo.owner}/${repo.name}/issues/new?template=${encodeURIComponent(form.id)}`, "Use template", 'class="btn secondary"')}</article>`).join("") || '<div class="panel">No issue forms.</div>'}${ctx.canAdminRepository(repo) ? `<form class="panel stack" data-form="issue-form"><h2>New issue form</h2><div class="form-row"><label for="form-name">Name</label><input id="form-name" name="name" required /></div><div class="form-row"><label for="form-description">Description</label><input id="form-description" name="description" /></div><div class="form-row"><label for="form-prefix">Title prefix</label><input id="form-prefix" name="titlePrefix" placeholder="[Bug] " /></div><div class="form-row"><label for="form-labels">Labels</label><input id="form-labels" name="labels" /></div><div class="form-row"><label for="form-fields">Fields, one per line: type | id | label | required | options</label><textarea id="form-fields" name="fields" required>textarea|reproduction|Reproduction steps|required|
textarea|expected|Expected behavior|required|
dropdown|severity|Severity|required|Low,Medium,High</textarea></div><button class="btn" type="submit">Create issue form</button></form>` : ""}`);
  ctx.root.querySelector('[data-form="issue-form"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const body = String(data.fields || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
      const [type, id, label, required, options] = line.split("|").map((entry) => entry.trim());
      return { type, id, label, required: required.toLowerCase() === "required", options: parseList(options) };
    });
    const result = await ctx.command("issueForm.upsert", { repoId: repo.id, name: data.name, description: data.description, titlePrefix: data.titlePrefix, labels: parseList(data.labels), body });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Issue form created.");
    if (result.ok) ctx.render();
  });
  return true;
}

function issueFormSubmissionView(ctx, repo, formId) {
  if (ctx.authRequired()) return true;
  const form = (ctx.state.issueForms || []).find((entry) => entry.repoId === repo.id && entry.id === formId);
  if (!form) return false;
  const component = (field) => {
    if (field.type === "markdown") return `<div class="callout">${ctx.escapeHtml(field.value)}</div>`;
    if (field.type === "textarea") return `<div class="form-row"><label for="field-${ctx.escapeHtml(field.id)}">${ctx.escapeHtml(field.label)}</label><textarea id="field-${ctx.escapeHtml(field.id)}" name="${ctx.escapeHtml(field.id)}" ${field.required ? "required" : ""} placeholder="${ctx.escapeHtml(field.placeholder || "")}"></textarea></div>`;
    if (field.type === "dropdown") return `<div class="form-row"><label for="field-${ctx.escapeHtml(field.id)}">${ctx.escapeHtml(field.label)}</label><select id="field-${ctx.escapeHtml(field.id)}" name="${ctx.escapeHtml(field.id)}" ${field.required ? "required" : ""}><option value="">Choose an option</option>${field.options.map((option) => `<option value="${ctx.escapeHtml(option)}">${ctx.escapeHtml(option)}</option>`).join("")}</select></div>`;
    if (field.type === "checkboxes") return `<fieldset><legend>${ctx.escapeHtml(field.label)}</legend>${field.options.map((option) => `<label class="checkbox-row"><input type="checkbox" name="${ctx.escapeHtml(field.id)}" value="${ctx.escapeHtml(option)}" /> ${ctx.escapeHtml(option)}</label>`).join("")}</fieldset>`;
    return `<div class="form-row"><label for="field-${ctx.escapeHtml(field.id)}">${ctx.escapeHtml(field.label)}</label><input id="field-${ctx.escapeHtml(field.id)}" name="${ctx.escapeHtml(field.id)}" ${field.required ? "required" : ""} /></div>`;
  };
  repositoryShell(ctx, repo, form.name, `<div id="enterprise-message"></div><form class="panel stack" data-form="issue-form-submit"><p>${ctx.escapeHtml(form.description)}</p><div class="form-row"><label for="issue-form-title">Title</label><input id="issue-form-title" name="title" required /></div>${form.body.map(component).join("")}<button class="btn" type="submit">Submit new issue</button></form>`);
  ctx.root.querySelector('[data-form="issue-form-submit"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const values = {};
    for (const field of form.body) {
      if (field.type === "markdown") continue;
      values[field.id] = field.type === "checkboxes" ? data.getAll(field.id) : data.get(field.id);
    }
    const result = await ctx.command("issueForm.submit", { formId: form.id, title: data.get("title"), values });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Issue created.");
    if (result.ok) ctx.navigate(`/${repo.owner}/${repo.name}/issues/${result.item.number}`);
  });
  return true;
}

function isOrgOwner(ctx, org) {
  const user = ctx.currentUser();
  return Boolean(user && (org.owner === user || org.members.some((member) => member.username === user && member.role === "Owner")));
}

function organizationSettingsNavigation(ctx, org) {
  return `<nav class="side-nav">${ctx.link(`/orgs/${org.name}/settings/security`, "Authentication security")} ${ctx.link(`/orgs/${org.name}/settings/scim`, "SCIM provisioning")} ${ctx.link(`/orgs/${org.name}/settings/data-policies`, "Data policies")} ${ctx.link(`/orgs/${org.name}/audit-log`, "Audit log")}</nav>`;
}

function auditView(ctx, org) {
  if (ctx.authRequired()) return true;
  if (!isOrgOwner(ctx, org)) {
    ctx.layout('<div class="error">Organization owner role is required to view the audit log.</div>', true);
    return true;
  }
  const events = (ctx.state.auditEvents || []).filter((event) => !event.organization || event.organization === org.name).slice().reverse();
  ctx.layout(`<section class="stack"><h1>Audit log</h1>${ctx.organizationTabs(org)}<p class="muted">Append-only SHA-256 hash chain. Sensitive credential fields are redacted before persistence.</p><div id="enterprise-message"></div><div class="toolbar"><input id="audit-filter" type="search" aria-label="Filter audit log" placeholder="Actor, action, or resource" /><button class="btn secondary" type="button" data-action="verify-audit">Verify chain</button><button class="btn secondary" type="button" data-action="export-audit">Export CSV</button></div><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Resource</th><th>Outcome</th></tr></thead><tbody id="audit-events"></tbody></table></section>`);
  const renderRows = () => {
    const query = ctx.root.querySelector("#audit-filter").value.toLowerCase();
    ctx.root.querySelector("#audit-events").innerHTML = events.filter((event) => `${event.actor} ${event.action} ${event.resource}`.toLowerCase().includes(query)).map((event) => `<tr><td>${ctx.escapeHtml(event.timestamp)}</td><td>${ctx.escapeHtml(event.actor)}</td><td>${ctx.escapeHtml(event.action)}</td><td>${ctx.escapeHtml(event.resource)}</td><td>${ctx.escapeHtml(event.outcome)}</td></tr>`).join("") || '<tr><td colspan="5">No matching audit events.</td></tr>';
  };
  ctx.root.querySelector("#audit-filter").addEventListener("input", renderRows);
  ctx.root.querySelector('[data-action="verify-audit"]').addEventListener("click", async () => {
    const result = await ctx.command("audit.verify", {});
    ctx.root.querySelector("#enterprise-message").innerHTML = result.item.valid ? `<div class="success">Chain verified: ${result.item.count} event(s), head ${ctx.escapeHtml(result.item.headHash.slice(0, 12))}…</div>` : `<div class="error">Audit chain failed at event ${result.item.brokenAt}.</div>`;
  });
  ctx.root.querySelector('[data-action="export-audit"]').addEventListener("click", async () => {
    const response = await fetch(`/api/audit/export.csv?organization=${encodeURIComponent(org.name)}`, { headers: { "x-langqi-world": ctx.worldId(), "x-langqi-user": ctx.currentUser() } });
    if (!response.ok) {
      ctx.root.querySelector("#enterprise-message").innerHTML = '<div class="error">Audit export was denied.</div>';
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${org.name}-audit-log.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  });
  renderRows();
  return true;
}

function securityView(ctx, org) {
  if (ctx.authRequired()) return true;
  const provider = (ctx.state.identityProviders || []).find((entry) => entry.organization === org.name) || {};
  ctx.layout(`<div class="split">${organizationSettingsNavigation(ctx, org)}<section class="stack"><h1>Authentication security</h1><div id="enterprise-message"></div><form class="panel stack" data-form="identity-provider"><h2>SAML single sign-on</h2><label class="checkbox-row"><input type="checkbox" name="enabled" ${provider.enabled ? "checked" : ""} /> Enable SAML SSO</label><label class="checkbox-row"><input type="checkbox" name="enforceSso" ${provider.enforceSso ? "checked" : ""} /> Require SSO for organization access</label><label class="checkbox-row"><input type="checkbox" name="scimEnabled" ${provider.scimEnabled ? "checked" : ""} /> Enable SCIM provisioning</label><div class="form-row"><label for="saml-url">Identity provider sign-on URL</label><input id="saml-url" name="signOnUrl" type="url" value="${ctx.escapeHtml(provider.signOnUrl || "")}" /></div><div class="form-row"><label for="saml-issuer">Issuer</label><input id="saml-issuer" name="issuer" value="${ctx.escapeHtml(provider.issuer || "")}" /></div><div class="form-row"><label for="saml-certificate">Public certificate</label><textarea id="saml-certificate" name="certificate" autocomplete="off"></textarea></div><button class="btn" type="submit">Save authentication settings</button></form></section></div>`);
  ctx.root.querySelector('[data-form="identity-provider"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await ctx.command("identityProvider.upsert", { organization: org.name, signOnUrl: data.signOnUrl, issuer: data.issuer, certificate: data.certificate, enabled: Boolean(data.enabled), enforceSso: Boolean(data.enforceSso), scimEnabled: Boolean(data.scimEnabled) });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Authentication settings saved.");
  });
  return true;
}

function scimView(ctx, org) {
  if (ctx.authRequired()) return true;
  const users = (ctx.state.scimUsers || []).filter((entry) => entry.organization === org.name);
  ctx.layout(`<div class="split">${organizationSettingsNavigation(ctx, org)}<section class="stack"><h1>SCIM provisioning</h1><div id="enterprise-message"></div>${users.map((user) => `<article class="card"><div class="toolbar"><strong>${ctx.escapeHtml(user.userName)}</strong><span class="badge">${user.active ? "Active" : "Deactivated"}</span>${user.active ? `<button class="btn danger" type="button" data-deactivate-scim="${ctx.escapeHtml(user.id)}">Deactivate</button>` : ""}</div><p>${ctx.escapeHtml(user.displayName)}</p></article>`).join("") || '<div class="panel">No SCIM users.</div>'}<form class="panel stack" data-form="scim-user"><h2>Provision user</h2><div class="form-row"><label for="scim-username">Username</label><input id="scim-username" name="userName" required /></div><div class="form-row"><label for="scim-display">Display name</label><input id="scim-display" name="displayName" /></div><div class="form-row"><label for="scim-email">Email</label><input id="scim-email" name="email" type="email" /></div><div class="form-row"><label for="scim-groups">Groups</label><input id="scim-groups" name="groups" /></div><button class="btn" type="submit">Provision with SCIM</button></form></section></div>`);
  ctx.root.querySelector('[data-form="scim-user"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await ctx.command("scim.provision", { organization: org.name, ...data, groups: parseList(data.groups) });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "SCIM user provisioned.");
    if (result.ok) ctx.render();
  });
  ctx.root.querySelectorAll("[data-deactivate-scim]").forEach((button) => button.addEventListener("click", async () => {
    const result = await ctx.command("scim.deactivate", { id: button.dataset.deactivateScim });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "SCIM user deactivated.");
    if (result.ok) ctx.render();
  }));
  return true;
}

function dataPoliciesView(ctx, org) {
  if (ctx.authRequired()) return true;
  const policies = (ctx.state.dataPolicies || []).filter((entry) => entry.organization === org.name);
  ctx.layout(`<div class="split">${organizationSettingsNavigation(ctx, org)}<section class="stack"><h1>Fine-grained data policies</h1><p class="muted">Apply subject-bound row filters and field visibility without copying source data.</p><div id="enterprise-message"></div>${policies.map((policy) => `<article class="card"><h2>${ctx.escapeHtml(policy.name)}</h2><p>Dataset: ${ctx.escapeHtml(policy.dataset)}</p><p>Rows: ${ctx.escapeHtml(policy.rowField)} ∈ ${ctx.escapeHtml(policy.allowedRowValues.join(", "))}</p><p>Hidden fields: ${ctx.escapeHtml(policy.hiddenFields.join(", ") || "none")}</p></article>`).join("") || '<div class="panel">No data policies.</div>'}<form class="panel stack" data-form="data-policy"><h2>New data policy</h2><div class="form-row"><label for="policy-name">Name</label><input id="policy-name" name="name" required /></div><div class="form-row"><label for="policy-dataset">Dataset</label><input id="policy-dataset" name="dataset" required /></div><div class="form-row"><label for="policy-subjects">Users or teams</label><input id="policy-subjects" name="subjects" /></div><div class="form-row"><label for="policy-row-field">Row scope field</label><input id="policy-row-field" name="rowField" placeholder="department" /></div><div class="form-row"><label for="policy-row-values">Allowed row values</label><input id="policy-row-values" name="allowedRowValues" /></div><div class="form-row"><label for="policy-hidden">Hidden fields</label><input id="policy-hidden" name="hiddenFields" /></div><div class="form-row"><label for="policy-readonly">Read-only fields</label><input id="policy-readonly" name="readOnlyFields" /></div><button class="btn" type="submit">Create data policy</button></form></section></div>`);
  ctx.root.querySelector('[data-form="data-policy"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await ctx.command("dataPolicy.upsert", { organization: org.name, name: data.name, dataset: data.dataset, subjects: parseList(data.subjects), rowField: data.rowField, allowedRowValues: parseList(data.allowedRowValues), hiddenFields: parseList(data.hiddenFields), readOnlyFields: parseList(data.readOnlyFields) });
    ctx.root.querySelector("#enterprise-message").innerHTML = resultMessage(ctx, result, "Data policy created.");
    if (result.ok) ctx.render();
  });
  return true;
}

export function handleEnterpriseRoute(ctx) {
  let match = ctx.path.match(/^\/orgs\/([^/]+)\/audit-log$/);
  if (match) {
    const org = organization(ctx, match[1]);
    return org ? auditView(ctx, org) : false;
  }
  match = ctx.path.match(/^\/orgs\/([^/]+)\/settings\/(security|scim|data-policies)$/);
  if (match) {
    const org = organization(ctx, match[1]);
    if (!org) return false;
    if (match[2] === "security") return securityView(ctx, org);
    if (match[2] === "scim") return scimView(ctx, org);
    return dataPoliciesView(ctx, org);
  }

  match = ctx.path.match(/^\/([^/]+)\/([^/]+)\/actions\/workflows\/([^/]+)$/);
  if (match) {
    const repo = repository(ctx, match[1], match[2]);
    return repo ? workflowView(ctx, repo, decode(match[3])) : false;
  }
  match = ctx.path.match(/^\/([^/]+)\/([^/]+)\/actions\/runs\/([^/]+)$/);
  if (match) {
    const repo = repository(ctx, match[1], match[2]);
    return repo ? workflowRunView(ctx, repo, decode(match[3])) : false;
  }
  match = ctx.path.match(/^\/([^/]+)\/([^/]+)\/actions\/new$/);
  if (match) {
    const repo = repository(ctx, match[1], match[2]);
    return repo ? workflowEditorView(ctx, repo) : false;
  }
  match = ctx.path.match(/^\/([^/]+)\/([^/]+)\/actions$/);
  if (match) {
    const repo = repository(ctx, match[1], match[2]);
    return repo ? actionsView(ctx, repo) : false;
  }
  match = ctx.path.match(/^\/([^/]+)\/([^/]+)\/settings\/(rules|environments|repository-lifecycle)$/);
  if (match) {
    const repo = repository(ctx, match[1], match[2]);
    if (!repo) return false;
    if (match[3] === "rules") return rulesetsView(ctx, repo);
    if (match[3] === "environments") return environmentsView(ctx, repo);
    return lifecycleView(ctx, repo);
  }
  match = ctx.path.match(/^\/([^/]+)\/([^/]+)\/issues\/templates$/);
  if (match) {
    const repo = repository(ctx, match[1], match[2]);
    return repo ? issueFormsView(ctx, repo) : false;
  }
  match = ctx.path.match(/^\/([^/]+)\/([^/]+)\/issues\/new$/);
  if (match && new URLSearchParams(location.search).has("template")) {
    const repo = repository(ctx, match[1], match[2]);
    const formId = new URLSearchParams(location.search).get("template");
    return repo ? issueFormSubmissionView(ctx, repo, formId) : false;
  }
  return false;
}
