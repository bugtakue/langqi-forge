const ROLE_LEVEL = Object.freeze({ read: 1, triage: 2, write: 3, maintain: 4, admin: 5 });

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizedRole(value) {
  const role = String(value || "").toLowerCase();
  return ROLE_LEVEL[role] ? role : "";
}

function memberName(value) {
  return typeof value === "string" ? value : value?.username;
}

export function isOrganizationOwner(state, organization, actor) {
  const org = state.organizations.find((entry) => entry.id === organization || entry.name === organization);
  return Boolean(org && actor && (org.owner === actor || asArray(org.members).some((entry) => entry.username === actor && entry.role === "Owner")));
}

export function isTeamMaintainer(state, team, actor) {
  return Boolean(team && actor && (isOrganizationOwner(state, team.organization, actor) || asArray(team.maintainers).some((entry) => memberName(entry) === actor)));
}

export function repositoryRole(state, repo, actor) {
  if (!repo || !actor || actor === "anonymous") return "";
  if (repo.owner === actor || isOrganizationOwner(state, repo.owner, actor) || asArray(repo.administrators).includes(actor)) return "admin";
  let strongest = "";
  for (const access of asArray(repo.accesses)) {
    const team = state.teams.find(
      (entry) => entry.organization === repo.owner && (entry.id === access.subject || entry.name === access.subject),
    );
    const teamSubject = access.subjectType === "team" || (access.subjectType !== "user" && Boolean(team));
    const applies = teamSubject
      ? Boolean(team && [...asArray(team.members), ...asArray(team.maintainers)].some((entry) => memberName(entry) === actor))
      : access.subject === actor;
    const role = applies ? normalizedRole(access.role) : "";
    if (role && (!strongest || ROLE_LEVEL[role] > ROLE_LEVEL[strongest])) strongest = role;
  }
  return strongest;
}

export function hasRepositoryRole(state, repo, actor, minimum) {
  const actual = repositoryRole(state, repo, actor);
  return Boolean(actual && ROLE_LEVEL[actual] >= ROLE_LEVEL[minimum]);
}

export function canViewRepository(state, repo, actor) {
  return Boolean(repo && (repo.visibility === "public" || hasRepositoryRole(state, repo, actor, "read")));
}

function denied(code, message) {
  return { ok: false, code, message };
}

function repositoryForItem(state, collection, item) {
  if (collection === "repositories") return item;
  return state.repositories.find((repo) => repo.id === item?.repoId);
}

export function authorizeGenericCommand(state, type, payload, actor) {
  if (!actor || actor === "anonymous") return denied("authentication_required", "a valid server session is required");
  if (type === "session.destroy") return { ok: true };

  if (type === "create") {
    const { collection, item } = payload || {};
    if (collection === "organizations") return item?.owner === actor ? { ok: true } : denied("forbidden", "organization owner must be the current account");
    if (collection === "teams") return isOrganizationOwner(state, item?.organization, actor) ? { ok: true } : denied("forbidden", "organization owner role is required");
    if (collection === "repositories") {
      return item?.owner === actor || isOrganizationOwner(state, item?.owner, actor)
        ? { ok: true }
        : denied("forbidden", "repository owner must be the current account or an owned organization");
    }
    if (collection === "issues") {
      const repo = repositoryForItem(state, collection, item);
      return hasRepositoryRole(state, repo, actor, "write") ? { ok: true } : denied("forbidden", "repository Write permission is required");
    }
    return denied("unsupported_collection", "the requested collection cannot be created through the generic API");
  }

  if (type === "pullRequest.create") {
    const repo = state.repositories.find((entry) => entry.id === payload?.item?.repoId);
    return hasRepositoryRole(state, repo, actor, "write") ? { ok: true } : denied("forbidden", "repository Write permission is required");
  }

  const collection = payload?.collection;
  const item = asArray(state[collection]).find((entry) => entry.id === payload?.id);
  if (!item) return denied("not_found", "target object was not found");

  if (collection === "organizations") {
    return isOrganizationOwner(state, item.name || item.id, actor) ? { ok: true } : denied("forbidden", "organization owner role is required");
  }
  if (collection === "teams") {
    return isTeamMaintainer(state, item, actor) ? { ok: true } : denied("forbidden", "team maintainer role is required");
  }
  const repo = repositoryForItem(state, collection, item);
  if (!repo) return denied("unsupported_collection", "the requested collection cannot be changed through the generic API");

  if (collection === "repositories") {
    const adminFields = new Set(["accesses", "defaultBranch", "protections", "visibility", "owner", "name"]);
    const fields = type === "patch" ? Object.keys(payload.patch || {}) : [payload.field];
    const minimum = fields.some((field) => adminFields.has(field)) ? "admin" : "write";
    return hasRepositoryRole(state, repo, actor, minimum) ? { ok: true } : denied("forbidden", `repository ${minimum} permission is required`);
  }

  if (collection === "issues") {
    const fields = type === "patch" ? Object.keys(payload.patch || {}) : [payload.field];
    const minimum = fields.some((field) => ["assignees", "labels", "milestone", "state"].includes(field)) ? "triage" : "write";
    return hasRepositoryRole(state, repo, actor, minimum) ? { ok: true } : denied("forbidden", `repository ${minimum} permission is required`);
  }

  if (collection === "pullRequests") {
    const fields = type === "patch" ? Object.keys(payload.patch || {}) : [payload.field];
    if (fields.includes("checks")) return hasRepositoryRole(state, repo, actor, "admin") ? { ok: true } : denied("forbidden", "repository Admin permission is required");
    if (fields.includes("draft")) return item.author === actor ? { ok: true } : denied("forbidden", "only the pull-request author can mark it ready");
    if (fields.includes("state")) return item.author === actor || hasRepositoryRole(state, repo, actor, "maintain") ? { ok: true } : denied("forbidden", "pull-request author or Maintain permission is required");
    if (fields.includes("reviewers")) return item.author === actor || hasRepositoryRole(state, repo, actor, "maintain") ? { ok: true } : denied("forbidden", "pull-request author or Maintain permission is required");
    return hasRepositoryRole(state, repo, actor, "write") ? { ok: true } : denied("forbidden", "repository Write permission is required");
  }
  return denied("unsupported_collection", "the requested collection cannot be changed through the generic API");
}
