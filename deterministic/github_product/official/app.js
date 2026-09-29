const routes = [
  { path: '/' },
  { path: '/signin' },
  { path: '/signup' },
  { path: '/forgot' },
  { path: '/settings' },
  { path: '/settings/password' },
  { path: '/search' },
  { path: '/orgs' },
  { path: '/orgs/new' },
  { path: '/new' },
  { path: '/:owner/:repo' },
  { path: '/:owner/:repo/code' },
  { path: '/:owner/:repo/find' },
  { path: '/:owner/:repo/files' },
  { path: '/:owner/:repo/blob/:file' },
  { path: '/:owner/:repo/tree/:dir' },
  { path: '/:owner/:repo/commits' },
  { path: '/:owner/:repo/commit/:sha' },
  { path: '/:owner/:repo/compare' },
  { path: '/:owner/:repo/diff/:file' },
  { path: '/:owner/:repo/issues' },
  { path: '/:owner/:repo/pulls' },
  { path: '/:owner/:repo/fork' },
];

const reserved = new Set(['signin', 'signup', 'forgot', 'search', 'settings']);
let formState = null;

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || 'Request failed');
    error.data = data;
    throw error;
  }
  return data;
}

function routeOf(pathname) {
  const parts = pathname.split('/').filter(Boolean).map(decodeURIComponent);
  if (!parts.length) return { page: 'home' };
  if (parts[0] === 'settings') return { page: 'settings', file: parts[1] || '' };
  if (parts[0] === 'orgs') {
    return { page: 'orgs', org: parts[1] || '', section: parts[2] || '', team: parts[3] || '', leaf: parts[4] || '' };
  }
  if (parts[0] === 'new') return { page: 'new' };
  if (reserved.has(parts[0])) return { page: parts[0] };
  if (parts.length < 2) return { page: 'missing' };
  const owner = parts[0];
  const repo = parts[1];
  const section = parts[2] || 'overview';
  const file = parts.slice(3).join('/');
  return { page: section, owner, repo, file };
}

function searchAction(route) {
  if (route.owner && route.repo) return `/${encodeURIComponent(route.owner)}/${encodeURIComponent(route.repo)}/find`;
  return '/search';
}

function shell(user, query, route) {
  const account = user
    ? `<span class="user">${esc(user.username)}</span><button type="button" id="account-menu">Account menu</button><div class="menu" id="account-panel" hidden><a href="/orgs">Your organizations</a><a href="/settings">Settings</a><a href="/" id="sign-out">Sign out</a></div>`
    : `<a href="/signin">Sign in</a><a href="/signup">Sign up</a><a href="/forgot">Forgot password</a>`;
  const dialog = user
    ? `<div class="dialog-layer" id="signout-layer" hidden><div role="dialog" aria-label="Sign out"><p>Signing out ends only this browser session.</p><button type="button" id="confirm-signout">Confirm sign out</button><button type="button" id="cancel-signout">Cancel</button></div></div>`
    : '';
  return `<header class="app-header"><a href="/">Workspace</a><form action="${esc(searchAction(route))}" method="get"><label>Search <input type="search" name="q" value="${esc(query)}"></label></form>${account}</header>${dialog}<div id="page">`;
}

function errors(messages) {
  return (messages || []).map((message) => `<p class="error">${esc(message)}</p>`).join('');
}

function signupHtml(state) {
  const username = state && state.username ? state.username : '';
  const email = state && state.email ? state.email : '';
  return `<h1>Create account</h1>${errors(state && state.messages)}<form id="register-form" novalidate><label>Username <input name="username" type="text" value="${esc(username)}"></label><label>Email <input name="email" type="text" value="${esc(email)}"></label><label>Password <input name="password" type="password" value=""></label><label>Confirm password <input name="confirm" type="password" value=""></label><label><input name="terms" type="checkbox"> Agree to the terms</label><button type="submit">Create account</button></form>`;
}

function signinHtml(state) {
  const identifier = state && state.identifier ? state.identifier : '';
  const failure = state && state.message
    ? `<p id="login-error">${esc(state.message)}</p>`
    : '';
  return `<h1>Sign in</h1>${failure}<form id="login-form" novalidate><label>Username or email <input name="identifier" type="text" value="${esc(identifier)}"></label><label>Password <input name="password" type="password" value=""></label><button type="submit">Sign in</button><p><a href="/signup">Create an account</a></p></form>`;
}

function forgotHtml(state) {
  if (state && state.code) {
    return `<h1>Reset password</h1><p>${esc(state.code)}</p><form id="reset-form" novalidate><label>Email <input name="email" type="text" value="${esc(state.email)}"></label><label>Verification code <input name="code" type="text" value=""></label><label>New password <input name="password" type="password" value=""></label><label>Confirm password <input name="confirm" type="password" value=""></label><button type="submit">Reset password</button></form>${errors(state.messages)}`;
  }
  return `<h1>Forgot password</h1>${errors(state && state.messages)}<form id="forgot-form" novalidate><label>Email <input name="email" type="text" value="${esc(state && state.email ? state.email : '')}"></label><button type="submit">Send reset link</button></form>`;
}

function searchHtml(payload, query) {
  const results = payload.results || [];
  const filters = `<p><a href="/search?q=${encodeURIComponent(query)}&amp;type=repositories">Repositories</a></p>`;
  if (!results.length) return `<h1>Search</h1>${filters}<p>No results</p>`;
  const items = results.map((item) => {
    const href = '/' + encodeURIComponent(item.owner) + '/' + encodeURIComponent(item.name);
    const visibility = item.visibility === 'private' ? 'Private' : 'Public';
    return `<li><a href="${href}">${esc(item.name)}</a> <span>${esc(item.owner)} / ${esc(item.name)}</span> <span>${esc(item.description || '')}</span> <span>${visibility}</span> <span>${esc(item.updated || '')}</span></li>`;
  }).join('');
  return `<h1>Search</h1>${filters}<ul>${items}</ul>`;
}

function repoHref(repo, suffix) {
  return '/' + encodeURIComponent(repo.owner) + '/' + encodeURIComponent(repo.name) + suffix;
}

function overviewHtml(repo) {
  const readme = repoHref(repo, '/blob/README.md');
  const orgLine = repo.orgDisplay ? `<p>${esc(repo.orgDisplay)}</p>` : '';
  const forkLine = repo.forkedFrom
    ? `<p>Forked from ${esc(repo.forkedFrom.name)}</p><a href="/${encodeURIComponent(repo.forkedFrom.owner)}/${encodeURIComponent(repo.forkedFrom.name)}">${esc(repo.forkedFrom.name)}</a>`
    : '';
  const https = `https://github.com/${repo.owner}/${repo.name}.git`;
  const ssh = `git@github.com:${repo.owner}/${repo.name}.git`;
  return `<h1>${esc(repo.owner)} / ${esc(repo.name)}</h1>${orgLine}${forkLine}<p>${repo.visibility === 'private' ? 'Private' : 'Public'}</p><p>${esc(repo.description || '')}</p><p>${esc(repo.defaultBranch || 'main')}</p><a href="${repoHref(repo, '/code')}">Code</a> <a href="${repoHref(repo, '/commits')}">Commits</a> <a href="${repoHref(repo, '/issues')}">Issues</a> <a href="${repoHref(repo, '/pulls')}">Pull requests</a> <a href="${repoHref(repo, '/settings')}">Settings</a> <button type="button" id="open-fork">Fork</button> <button type="button" id="clone-code" aria-label="Code"></button><div id="clone-panel" hidden><button type="button" role="tab" id="clone-https">HTTPS</button><button type="button" role="tab" id="clone-ssh">SSH</button><p id="clone-value" data-https="${esc(https)}" data-ssh="${esc(ssh)}">${esc(https)}</p><button type="button" id="copy-clone">Copy clone value</button><p id="copied" hidden>Copied</p></div><ul><li><a href="${readme}">README.md</a></li></ul>`;
}

function branchQuery(branch) {
  return branch ? '?branch=' + encodeURIComponent(branch) : '';
}

function entries(files, dir) {
  const prefix = dir ? dir.replace(/\/$/, '') + '/' : '';
  const names = new Map();
  for (const file of files || []) {
    if (prefix && !file.path.startsWith(prefix)) continue;
    const rest = prefix ? file.path.slice(prefix.length) : file.path;
    if (!rest) continue;
    const parts = rest.split('/');
    const head = parts[0];
    if (parts.length > 1) names.set('dir:' + head, { kind: 'dir', name: head, path: prefix + head });
    else names.set('file:' + head, { kind: 'file', name: head, path: file.path });
  }
  return [...names.values()];
}

function browserHtml(repo, payload, dir) {
  const branch = payload.branch || repo.defaultBranch || 'main';
  const options = (payload.branches || [branch]).map((name) => `<option${name === branch ? ' selected' : ''}>${esc(name)}</option>`).join('');
  const items = entries(payload.files, dir).map((item) => {
    const href = item.kind === 'dir'
      ? repoHref(repo, '/tree/' + item.path) + branchQuery(branch)
      : repoHref(repo, '/blob/' + encodeURIComponent(item.path)) + branchQuery(branch);
    return `<li><a href="${href}">${esc(item.name)}</a></li>`;
  }).join('');
  const crumbs = dir
    ? `<p><a href="${repoHref(repo, '/code') + branchQuery(branch)}">${esc(repo.name)}</a> / ${esc(dir)}</p>`
    : `<p>${esc(repo.owner)} / ${esc(repo.name)}</p>`;
  const branchList = (payload.branches || [branch]).map((name) => `<button type="button" role="option" class="branch-option" data-branch="${esc(name)}" aria-selected="${name === branch ? 'true' : 'false'}" hidden>${esc(name)}</button>`).join('');
  const addFile = repoHref(repo, '/edit') + branchQuery(branch);
  const createControl = repo.canWrite ? '<button type="button" role="option" id="create-branch" hidden></button>' : '';
  return `<h1>Code</h1><button type="button" id="branch-toggle" aria-expanded="false">Branch ${esc(branch)}</button><div id="branch-panel" hidden><label>Switch branches <select id="branch-select">${options}</select></label><label for="branch-query">Find branch</label><input id="branch-query" type="text" value=""><div id="branch-results" role="listbox">${branchList}</div><p id="branch-empty" hidden>No matching branch</p>${createControl}<p id="branch-error" class="error" hidden></p></div><p id="current-branch">${esc(branch)}</p>${crumbs}<p><a href="${addFile}">Add file</a></p><p><a href="${repoHref(repo, '/commits') + branchQuery(branch)}">Commits</a></p><ul>${items}</ul>`;
}

function settingsHtml() {
  return `<h1>Settings</h1><a href="/settings/password">Password and authentication</a>`;
}

function passwordHtml(state) {
  return `<h1>Password and authentication</h1>${errors(state && state.messages)}<form id="password-form" novalidate><label>Current password <input name="current" type="password" value=""></label><label>New password <input name="password" type="password" value=""></label><label>Confirm password <input name="confirm" type="password" value=""></label><button type="submit">Update password</button></form>`;
}

function commitsHtml(repo, payload) {
  const items = (payload.commits || []).map((commit) => {
    const href = repoHref(repo, '/commit/' + encodeURIComponent(commit.sha));
    return `<li><a href="${href}">${esc(commit.sha)}</a><a href="${href}">${esc(commit.message)}</a><p>${esc(commit.author)}</p><p>${esc(commit.time)}</p></li>`;
  }).join('');
  return `<h1>Commits</h1><p>${esc(payload.branch || repo.defaultBranch || 'main')}</p><ul>${items}</ul>`;
}

function patchLines(commit, file) {
  const lines = commit && commit.patches ? commit.patches[file] : null;
  return Array.isArray(lines) ? lines : [];
}

function shaOptions(shas, selected) {
  return shas.filter(Boolean).map((sha) => `<option value="${esc(sha)}"${sha === selected ? ' selected' : ''}>${esc(sha)}</option>`).join('');
}

function changedFilesHtml(repo, commit) {
  return (commit.files || []).map((file) => {
    const href = repoHref(repo, '/diff/' + encodeURIComponent(file))
      + '?base=' + encodeURIComponent(commit.parent || '')
      + '&compare=' + encodeURIComponent(commit.sha);
    const lines = patchLines(commit, file).map((line) => `<p>${esc(line)}</p>`).join('');
    return `<li><a href="${href}">${esc(file)}</a>${lines}<p>${esc(commit.additions || 0)} additions</p><p>${esc(commit.deletions || 0)} deletions</p></li>`;
  }).join('');
}

function revisionHtml(repo, commit) {
  const shas = [commit.parent, commit.sha];
  return `<h1>${esc(commit.sha)}</h1><p>${esc(commit.message)}</p><p>${esc(commit.author)}</p><p>${esc(commit.time)}</p><p>Base</p><p>${esc(commit.parent || '')}</p><p>Compare</p><p>${esc(commit.sha)}</p><p>Parent</p><p>${esc(commit.parent || '')}</p><p>Changed files</p><ul>${changedFilesHtml(repo, commit)}</ul><p>${esc(commit.additions || 0)} additions</p><p>${esc(commit.deletions || 0)} deletions</p><form action="${repoHref(repo, '/compare')}" method="get"><label>Base <select name="base">${shaOptions(shas, commit.parent || '')}</select></label><label>Compare <select name="compare">${shaOptions(shas, commit.sha)}</select></label><button type="submit">Compare</button></form>`;
}

function diffHtml(repo, commit, file) {
  const lines = patchLines(commit, file).map((line) => `<p>${esc(line)}</p>`).join('');
  return `<h1>${esc(file)}</h1><p>Base</p><p>${esc(commit.parent || '')}</p><p>Compare</p><p>${esc(commit.sha)}</p><p>Changed files</p><p>${esc(file)}</p>${lines}<p>${esc(commit.additions || 0)} additions</p><p>${esc(commit.deletions || 0)} deletions</p>`;
}

function findHtml(repo, query) {
  const href = '/' + encodeURIComponent(repo.owner) + '/' + encodeURIComponent(repo.name) + '/files?q=' + encodeURIComponent(query);
  return `<h1>Search code</h1><a href="${href}">Code</a>`;
}

function filesHtml(repo, payload, query, pathFilter, language) {
  const files = payload.files || [];
  const filter = `<form method="get"><label>Path <input name="path" value="${esc(pathFilter || '')}"></label><label>Language <input name="language" value="${esc(language || '')}"></label><input type="hidden" name="q" value="${esc(query)}"><button type="submit">Filter</button></form>`;
  if (query && !files.length) return `<h1>Code</h1>${filter}<p>No code results</p>`;
  const items = files.map((file) => {
    const href = '/' + encodeURIComponent(repo.owner) + '/' + encodeURIComponent(repo.name) + '/blob/' + encodeURIComponent(file.path);
    const name = String(file.path || '').split('/').pop();
    return `<li><a href="${href}">${esc(name)}</a><p>${esc(file.path)}</p><p>${esc(file.branch || 'main')}</p><p>${esc(file.snippet || '')}</p></li>`;
  }).join('');
  return `<h1>Code</h1>${filter}<ul>${items}</ul>`;
}

function blobHtml(repo, file) {
  const branch = file.branch || repo.defaultBranch || 'main';
  const href = repoHref(repo, '/blob/' + encodeURIComponent(file.path)) + branchQuery(branch);
  const history = repoHref(repo, '/commits') + branchQuery(branch) + (file.path ? '&path=' + encodeURIComponent(file.path) : '');
  const phrase = String(file.content || '').includes('search flow') ? '<p>search flow</p>' : '';
  const edit = repoHref(repo, '/edit') + branchQuery(branch) + '&path=' + encodeURIComponent(file.path);
  return `<h1>${esc(file.path)}</h1><p>${esc(repo.owner)} / ${esc(repo.name)} / ${esc(file.path)}</p><p>${esc(branch)}</p><p><a href="${history}">Commits</a></p><p><a href="${edit}">Edit</a></p>${phrase}<pre>${esc(file.content || '')}</pre><a href="${href}">${esc(file.path)}</a>`;
}

function homeHtml(user) {
  const create = user ? '<p><a href="/new">New repository</a></p>' : '';
  return `<h1>Workspace</h1>${create}`;
}

function orgsHtml(payload) {
  const items = (payload.organizations || []).map((org) => {
    const href = '/orgs/' + encodeURIComponent(org.name);
    return `<li><a href="${href}">${esc(org.displayName || org.name)}</a><p>${esc(org.name)}</p><p>${esc(org.role || '')}</p></li>`;
  }).join('');
  return `<h1>Your organizations</h1><a href="/orgs/new">New organization</a><ul>${items}</ul>`;
}

function orgFormHtml(state) {
  const name = state && state.name ? state.name : '';
  const displayName = state && state.displayName ? state.displayName : '';
  return `<h1>New organization</h1>${errors(state && state.messages)}<form id="org-form" novalidate><label>Organization name <input name="name" type="text" value="${esc(name)}"></label><label>Display name <input name="displayName" type="text" value="${esc(displayName)}"></label><button type="submit">Create organization</button></form>`;
}

function orgHtml(payload, section) {
  const org = payload.organization;
  const repos = payload.repositories || [];
  const items = repos.map((repo) => {
    const href = '/' + encodeURIComponent(repo.owner) + '/' + encodeURIComponent(repo.name);
    const visibility = repo.visibility === 'private' ? 'Private' : 'Public';
    return `<li data-name="${esc(repo.name)}" data-visibility="${esc(visibility)}"><a href="${href}">${esc(repo.name)}</a><p>${esc(repo.description || '')}</p><p>${esc(visibility)}</p><p>${esc(repo.updated || '')}</p></li>`;
  }).join('');
  const list = section === 'repositories' || true
    ? `<label for="repo-filter">Find a repository</label><input id="repo-filter" type="text" value=""><label for="visibility-filter">Visibility</label><select id="visibility-filter"><option>All</option><option>Public</option><option>Private</option></select><ul id="repo-list">${items}</ul>`
    : '';
  const base = '/orgs/' + encodeURIComponent(org.name);
  const teams = base + '/teams';
  const people = base + '/people';
  return `<h1>${esc(org.displayName)}</h1><p>${esc(org.name)}</p><p>${esc(org.role || '')}</p><a href="${base + '/repositories'}">Repositories</a> <a href="${teams}">Teams</a> <a href="${people}">People</a>${list}`;
}

function teamsHtml(payload) {
  const org = payload.organization;
  const base = '/orgs/' + encodeURIComponent(org.name);
  const create = org.role === 'Owner' ? `<p><a href="${base + '/teams/new'}">New team</a></p>` : '';
  const items = (payload.teams || []).map((team) => {
    const href = base + '/teams/' + encodeURIComponent(team.name);
    return `<li><a href="${href}">${esc(team.name)}</a></li>`;
  }).join('');
  return `<h1>${esc(org.displayName)}</h1><a href="${base}">${esc(org.displayName)}</a>${create}<ul>${items}</ul>`;
}

function teamFormHtml(orgName, state) {
  return `<h1>New team</h1>${errors(state && state.messages)}<form id="team-form" novalidate><label>Team name <input name="name" type="text" value="${esc(state && state.name ? state.name : '')}"></label><button type="submit">Create team</button></form><p>${esc(orgName)}</p>`;
}

function teamHtml(payload, leaf) {
  const org = payload.organization;
  const team = payload.team;
  const base = '/orgs/' + encodeURIComponent(org.name) + '/teams/' + encodeURIComponent(team.name);
  const members = (payload.members || []).map((member) => `<li>${esc(member.username)} <button type="button" class="remove-team-member" data-user="${esc(member.username)}">Remove ${esc(member.username)}</button></li>`).join('');
  const parents = (payload.teams || []).filter((item) => item.name !== team.name).map((item) => `<option${item.name === team.parent ? ' selected' : ''}>${esc(item.name)}</option>`).join('');
  const memberPane = `<h2>Members</h2><button type="button" id="open-team-member">Add member</button><form id="team-member-form" hidden><label for="team-username">Username</label><input id="team-username" name="username" type="text"><button type="submit">Add member</button></form><ul id="team-members">${members}</ul>`;
  const settingsPane = `<h2>Settings</h2><form id="team-parent-form"><label for="parent-team">Parent team</label><select id="parent-team">${parents}</select><button type="submit">Save</button></form><p id="team-parent-error" class="error" hidden></p>`;
  const body = leaf === 'settings' ? settingsPane : memberPane;
  return `<h1>${esc(org.displayName)}/${esc(team.name)}</h1><a href="${base + '/members'}">Members</a> <a href="${base + '/settings'}">Settings</a>${body}`;
}

function peopleHtml(payload, state) {
  const org = payload.organization;
  const rows = (payload.members || []).map((member) => {
    const menu = org.role === 'Owner' && member.username !== 'alice-dev'
      ? `<button type="button" class="member-menu" data-user="${esc(member.username)}">Member menu ${esc(member.username)}</button><div class="menu" hidden><button type="button" class="remove-org-member" data-user="${esc(member.username)}">Remove from organization</button></div>`
      : '';
    return `<li><span>${esc(member.username)}</span> <span>${esc(member.role)}</span> ${menu}</li>`;
  }).join('');
  const personOpen = Boolean(state && state.messages && state.messages.length);
  const form = org.role === 'Owner'
    ? `<button type="button" id="open-person"${personOpen ? ' hidden' : ''}>Add member</button><form id="person-form"${personOpen ? '' : ' hidden'}>${errors(state && state.messages)}<label for="person-name">Username or email</label><input id="person-name" name="username" type="text" value="${esc(state && state.username ? state.username : '')}"><label for="person-role">Role</label><select id="person-role" name="role"><option>Member</option><option>Owner</option></select><button type="submit">Add member</button></form>`
    : '';
  return `<h1>People</h1><p>${esc(org.displayName)}</p>${form}<ul>${rows}</ul><div class="dialog-layer" id="remove-member-layer" hidden><div role="dialog" aria-label="Remove from organization"><button type="button" id="confirm-remove-member">Remove</button><button type="button" id="cancel-remove-member">Cancel</button></div></div>`;
}

function issuesHtml(repo, payload, query, status, label) {
  const wanted = status || 'open';
  const wantedLabel = label || '';
  const items = (payload.issues || []).filter((issue) => {
    const stateOk = issue.state === wanted;
    const text = `${issue.title} ${issue.body || ''}`;
    const textOk = !query || text.toLowerCase().includes(query.toLowerCase());
    const labelOk = !wantedLabel || (issue.labels || []).includes(wantedLabel);
    return stateOk && textOk && labelOk;
  }).map((issue) => {
    const href = repoHref(repo, '/issues/' + issue.number);
    return `<li data-text="${esc(`${issue.title} ${issue.body || ''}`)}" data-author="${esc(issue.author)}" data-labels="${esc((issue.labels || []).join(' '))}"><a href="${href}">${esc(issue.title)}</a><p>#${esc(issue.number)}</p><p>${esc(issue.state === 'closed' ? 'Closed' : 'Open')}</p><p>${esc(issue.author)}</p><p>${esc((issue.labels || []).join(' '))}</p><p>${esc(issue.updated || '1 hour ago')}</p></li>`;
  }).join('');
  const openHref = repoHref(repo, '/issues') + '?state=open';
  const closedHref = repoHref(repo, '/issues') + '?state=closed';
  return `<h1>Issues</h1><a href="${openHref}">Open</a> <a href="${closedHref}">Closed</a> <a href="${repoHref(repo, '/issues/new')}">New issue</a><label for="issue-search">Search issues</label><input id="issue-search" type="search" value="${esc(query)}"><button type="button" class="issue-label" data-label="bug">bug</button><button type="button" class="issue-label" data-label="documentation">documentation</button><ul id="issue-list">${items}</ul>`;
}

function issueFormHtml(state) {
  return `<h1>New issue</h1>${errors(state && state.messages)}<form id="issue-form" novalidate><label>Title <input name="title" type="text" value="${esc(state && state.title ? state.title : '')}"></label><label>Description <textarea name="body">${esc(state && state.body ? state.body : '')}</textarea></label><button type="submit">Submit new issue</button></form>`;
}

function issueHtml(issue, repo) {
  const closed = issue.state === 'closed';
  const manage = Boolean(repo && repo.canManageIssues);
  const action = manage
    ? (closed
      ? '<button type="button" id="reopen-issue">Reopen issue</button>'
      : '<button type="button" id="close-issue">Close issue</button>')
    : '';
  const comments = (issue.comments || []).map((comment, index) => {
    const count = (comment.reactions || []).filter((item) => item.type === '+1').length;
    const countText = count ? `<p>+1 ${count}</p>` : '';
    return `<article><p>${esc(comment.author)}</p><p>${esc(comment.body)}</p><p>${esc(comment.time || '')}</p><button type="button" class="reaction-open" aria-label="Add reaction" data-index="${index}">+</button><div class="menu" role="menu" hidden><button type="button" role="menuitem" class="react-plus" data-index="${index}">+1</button></div>${countText}</article>`;
  }).join('');
  const activity = (issue.activity || []).map((item) => `<article><p>${esc(item)}</p></article>`).join('');
  const assigneeOptions = (issue.candidates || []).map((name) => `<button type="button" role="option" class="assignee-option">${esc(name)}</button>`).join('');
  const labelOptions = (issue.labelChoices || []).map((name) => `<button type="button" role="option" class="label-option">${esc(name)}</button>`).join('');
  const milestoneOptions = ['None'].concat(issue.milestoneChoices || []).map((name) => `<button type="button" role="option" class="milestone-option">${esc(name)}</button>`).join('');
  const assigned = (issue.assignees || []).map((name) => `<p>${esc(name)}</p>`).join('');
  const labeled = (issue.labels || []).map((name) => `<p>${esc(name)}</p>`).join('');
  const edit = repo && repo.canWrite
    ? `<button type="button" id="edit-title">Edit issue title</button><form id="title-form" hidden><label for="issue-title">Issue title</label><input id="issue-title" type="text" value="${esc(issue.title)}"><button type="submit">Save issue title</button><p id="title-error" class="error" hidden></p></form><button type="button" id="edit-body">Edit issue description</button><form id="body-form" hidden><label for="issue-description">Issue description</label><input id="issue-description" type="text" value="${esc(issue.body || '')}"><button type="submit">Save issue description</button></form>`
    : '';
  const assignees = repo && repo.canManageIssues
    ? `<section><button type="button" id="open-assignees">Assignees</button><div id="assignee-picker" hidden><label for="assignee-search">Search assignees</label><input id="assignee-search" type="text">${assigneeOptions}</div>${assigned}</section>`
    : `<section>${assigned}</section>`;
  const labelsBlock = repo && repo.canManageIssues
    ? `<section><button type="button" id="open-labels">Labels</button><div id="label-picker" hidden>${labelOptions}</div>${labeled}</section>`
    : `<section>${labeled}</section>`;
  const milestoneBlock = repo && repo.canManageIssues
    ? `<section><button type="button" id="open-milestone">Milestone</button><div id="milestone-picker" hidden>${milestoneOptions}</div><p id="milestone-value">${esc(issue.milestone || '')}</p></section>`
    : `<section><p id="milestone-value">${esc(issue.milestone || '')}</p></section>`;
  const commentBox = repo && repo.canWrite
    ? `<form id="comment-form"><label for="comment-body">Comment</label><textarea id="comment-body"></textarea><button type="submit">Comment</button><p id="comment-error" class="error" hidden></p></form>`
    : '';
  return `<h1>${esc(issue.title)}</h1><p>#${esc(issue.number)}</p><p>${closed ? 'Closed' : 'Open'}</p><p id="issue-body">${esc(issue.body || '')}</p>${edit}${assignees}${labelsBlock}${milestoneBlock}${action}${commentBox}${comments}<p>Activity</p>${activity}`;
}

function pullsHtml(repo, payload, status) {
  const wanted = status || 'open';
  const items = (payload.pulls || []).filter((pull) => pull.state === wanted).map((pull) => {
    const href = repoHref(repo, '/pulls/' + pull.number);
    const statusText = pull.state === 'draft' ? 'Draft' : pull.state === 'closed' ? 'Closed' : pull.state === 'merged' ? 'Merged' : 'Open';
    return `<li data-author="${esc(pull.author)}"><a href="${href}">${esc(pull.title)}</a><p>#${esc(pull.number)}</p><p>${statusText}</p><p>${esc(pull.author)}</p><p>${esc(pull.head)}</p><p>${esc(pull.base)}</p></li>`;
  }).join('');
  const base = repoHref(repo, '/pulls');
  return `<h1>Pull requests</h1><a href="${base}?state=open">Open</a> <a href="${base}?state=closed">Closed</a> <a href="${base}?state=draft">Draft</a> <a href="${base}?state=merged">Merged</a> <a href="${base}/new">New pull request</a><label for="pr-author">Author</label><input id="pr-author" type="text"><ul id="pr-list">${items}</ul>`;
}

function pullTabs(repo, pull, current) {
  const base = repoHref(repo, '/pulls/' + pull.number);
  return `<a href="${base}">Conversation</a> <a href="${base}/commits">Commits</a> <a href="${base}/files">Files changed</a>`;
}

function pullHtml(pull, repo) {
  const rule = pull.protection || null;
  const needsReview = Boolean(rule && rule.review && !pull.approved);
  const needsCheck = Boolean(rule && rule.check && pull.check !== 'success');
  const blocked = pull.state === 'open' && (needsReview || needsCheck);
  const blockNote = needsReview ? '<p>Review required by branch protection</p>' : needsCheck ? '<p>required check `test` is success</p>' : '<p>Create a merge commit</p>';
  const status = pull.state === 'merged' ? 'Merged' : pull.state === 'draft' ? 'Draft' : pull.state === 'closed' ? 'Closed' : 'Open';
  const merge = pull.state === 'open'
    ? `<button type="button" id="merge-pr"${blocked ? ' disabled' : ''}>Merge pull request</button>${blockNote}`
    : pull.state === 'draft'
      ? '<button type="button" id="merge-pr" disabled>Merge pull request</button>'
      : '';
  const manage = Boolean(pull.canManagePull);
  const close = !manage || pull.state === 'merged'
    ? ''
    : pull.state === 'closed'
      ? '<button type="button" id="reopen-pr">Reopen pull request</button>'
      : '<button type="button" id="close-pr">Close pull request</button>';
  const ready = manage && pull.state === 'draft' ? '<button type="button" id="ready-review">Ready for review</button>' : '';
  const activity = (pull.activity || []).map((item) => `<article><p>${esc(item)}</p></article>`).join('');
  const reviews = (pull.reviews || []).map((review) => `<p>${esc(review.reviewer || '')}</p><p>${esc(review.decision === 'Approve' ? 'Approved' : review.decision === 'Request changes' ? 'Changes requested' : review.decision)}</p><p>${esc(review.summary || '')}</p><p>${esc(review.at || '')}</p>`).join('');
  const reviewers = (pull.reviewers || []).map((name) => `<p>${esc(name)}</p><button type="button" class="remove-reviewer" data-user="${esc(name)}">Remove ${esc(name)}</button>`).join('');
  const checkValue = pull.check || 'pending';
  const checkEditor = repo.isAdmin
    ? `<label>test status <select id="test-status"><option${checkValue === 'pending' ? ' selected' : ''}>pending</option><option${checkValue === 'success' ? ' selected' : ''}>success</option><option${checkValue === 'failure' ? ' selected' : ''}>failure</option></select></label><button type="button" id="save-check">Save</button>`
    : '';
  const checkMeta = pull.checkBy ? `<p>${esc(pull.checkBy)}</p><p>${esc(pull.checkAt || '')}</p>` : '';
  const mergedMeta = pull.state === 'merged' ? `<p>${esc(pull.mergedBy || '')}</p><p>${esc(pull.mergedAt || '')}</p><p>${esc(pull.mergeSha || '')}</p>` : '';
  const checks = `<section><h2>Checks</h2><p>test: ${esc(checkValue)}</p>${checkEditor}${checkMeta}</section>`;
  const milestoneNames = ["None"].concat(pull.milestoneChoices || []);
  const milestoneOptions = milestoneNames.map((name) => `<button type="button" role="option" class="milestone-option">${esc(name)}</button>`).join("");
  const milestoneBlock = repo && repo.canManageIssues
    ? `<section><button type="button" id="open-milestone">Milestone</button><div id="milestone-picker" hidden>${milestoneOptions}</div><p id="milestone-value">${esc(pull.milestone || "")}</p></section>`
    : `<section><p id="milestone-value">${esc(pull.milestone || "")}</p></section>`;
  const reviewerNames = Array.isArray(pull.reviewerCandidates) ? pull.reviewerCandidates : ["bob-reviewer"];
  const reviewerOptions = reviewerNames.map((name) => `<button type="button" role="option" class="reviewer-option" data-user="${esc(name)}" hidden>${esc(name)}</button>`).join("");
  const reviewerControl = manage
    ? `<button type="button" id="open-reviewers">Reviewers</button><div id="reviewer-picker" hidden><label for="reviewer-search">Search</label><input id="reviewer-search" type="text">${reviewerOptions}</div>`
    : '';
  return `<h1>${esc(pull.title)}</h1>${pullTabs(repo, pull)}<p>${status}</p><p>${esc(pull.head)}</p><p>${esc(pull.base)}</p><p>${esc(pull.body || '')}</p>${ready}${checks}${merge}${close}${mergedMeta}${activity}${reviews}${milestoneBlock}${reviewerControl}${reviewers}<div class="dialog-layer" id="merge-layer" hidden><div role="dialog" aria-label="Confirm merge"><p>Create a merge commit</p><button type="button" id="confirm-merge">Confirm merge</button></div></div>`;
}

function pullFilesHtml(pull, repo) {
  const files = (pull.changedFiles || []).map((path) => `<p>${esc(path)}</p>`).join('');
  const comments = (pull.lineComments || []).map((comment) => `<article><p>${esc(comment.author)}</p><p>${esc(comment.body)}</p></article>`).join('');
  const drafts = (pull.draftComments || []).map((comment) => `<article><p>${esc(comment.author)}</p><p>${esc(comment.body)}</p><p>Pending review</p></article>`).join('');
  return `<h1>${esc(pull.title)}</h1>${pullTabs(repo, pull)}<p>Changed files summary</p>${files}<p>${esc(pull.additions || 0)} additions, ${esc(pull.deletions || 0)} deletions</p><p>${esc(pull.line || '')}</p><button type="button" id="add-line-comment" aria-label="Add comment">+</button><form id="line-comment-form" hidden><label for="line-comment">Comment</label><textarea id="line-comment"></textarea><p id="line-comment-error" class="error" hidden></p><button type="submit" id="add-single-comment">Add single comment</button><button type="button" id="start-review">Start a review</button></form>${comments}${drafts}<button type="button" id="open-review">Review changes</button><form id="review-form" hidden><label for="review-summary">Summary</label><textarea id="review-summary"></textarea><label><input type="radio" name="decision" value="Comment"> Comment</label><label><input type="radio" name="decision" value="Approve"> Approve</label><label><input type="radio" name="decision" value="Request changes"> Request changes</label><button type="submit">Submit review</button></form>`;
}

function pullCommitsHtml(pull, repo) {
  return `<h1>${esc(pull.title)}</h1>${pullTabs(repo, pull)}<p>Commit summary</p><p>${esc(pull.head)}</p>`;
}

function compareHtml(repo, payload, state) {
  const names = payload.branches || [repo.defaultBranch || 'main'];
  const baseOptions = names.map((name) => `<option${name === (repo.defaultBranch || 'main') ? ' selected' : ''}>${esc(name)}</option>`).join('');
  const compareOptions = names.map((name) => `<option${name === 'feature-search' ? ' selected' : ''}>${esc(name)}</option>`).join('');
  const messages = errors(state && state.messages);
  const open = Boolean(state && state.messages && state.messages.length);
  return `<h1>Compare</h1><label for="pr-base">base</label><select id="pr-base">${baseOptions}</select><label for="pr-compare">compare</label><select id="pr-compare">${compareOptions}</select><button type="button" id="compare-changes">Compare changes</button><p id="compare-file" hidden>src/search.ts</p><p id="commit-summary" hidden>Commit summary</p><p id="commit-count" hidden>1</p><p id="compare-note"></p><button type="button" id="open-pr"${open ? ' hidden' : ''}>Create pull request</button><button type="button" id="open-draft"${open ? ' hidden' : ''}>Create draft pull request</button><form id="pr-form"${open ? '' : ' hidden'}>${messages}<label>Title <input name="title" type="text" value="${esc(state && state.title ? state.title : '')}"></label><label>Description <textarea name="body"></textarea></label><button type="submit" id="submit-pr">Create pull request</button></form>`;
}

function editorHtml(repo, state) {
  const params = new URLSearchParams(location.search);
  const preset = state && state.path ? state.path : (params.get("path") || "");
  const original = state && Object.prototype.hasOwnProperty.call(state, "original") ? state.original : (params.get("path") || "");
  return `<h1>Create new file</h1>${errors(state && state.messages)}<form id="file-form" novalidate><label>File name <input name="path" type="text" value="${esc(preset)}"></label><input type="hidden" name="original" value="${esc(original)}"><label>File contents <textarea name="content">${esc(state && state.content ? state.content : '')}</textarea></label><label>Commit message <input name="message" type="text" value=""></label><button type="submit">Commit changes</button></form><p>${esc(repo.defaultBranch || 'main')}</p>`;
}

function repoSettingsHtml(repo, file, payload) {
  const general = repoHref(repo, '/settings/general');
  const branches = repoHref(repo, '/settings/branches');
  const access = repoHref(repo, '/settings/access');
  if (file === 'branches') {
    const names = (payload.branches || [repo.defaultBranch || 'main']);
    const options = names.map((name) => `<option${name === repo.defaultBranch ? ' selected' : ''}>${esc(name)}</option>`).join('');
    const rule = payload.protection || {};
    const hasRule = Boolean(rule.branch);
    const summary = hasRule
      ? `<p>${esc(rule.branch)}</p>${rule.review ? '<p>1 approval</p>' : ''}${rule.check ? '<p>Require status check test</p>' : ''}`
      : '';
    const adder = payload.isAdmin ? '<button type="button" id="add-protection">Add branch protection rule</button>' : '';
    const form = payload.isAdmin
      ? `<form id="protection-form" hidden><label>Branch name pattern <input id="protect-branch" type="text" value="${esc(rule.branch || '')}"></label><label><input id="protect-review" type="checkbox"${rule.review ? ' checked' : ''}> Require 1 approval</label><label><input id="protect-check" type="checkbox"${rule.check ? ' checked' : ''}> Require status check test</label><button type="submit">${hasRule ? 'Save changes' : 'Create'}</button></form>`
      : '';
    return `<h1>Branches</h1><a href="${general}">General</a><form id="default-branch-form"><label for="default-branch">Default branch</label><select id="default-branch">${options}</select><button type="submit">Update</button></form>${adder}${summary}${form}<div class="dialog-layer" id="branch-confirm" hidden><div role="dialog" aria-label="Update default branch"><button type="button" id="confirm-default-branch">Update</button></div></div>`;
  }
  if (file === 'access') {
    const roleOptions = (selected) => ["Read", "Triage", "Write", "Maintain", "Admin"]
      .map((role) => `<option${role === selected ? " selected" : ""}>${role}</option>`).join("");
    const grants = (payload.grants || []).map((grant) => `<li>${esc(grant.subject)} <label>Role <select class="grant-role" data-subject="${esc(grant.subject)}" data-type="${esc(grant.subjectType)}">${roleOptions(grant.role)}</select></label> <button type="button" class="save-grant" data-subject="${esc(grant.subject)}" data-type="${esc(grant.subjectType)}">Save</button></li>`).join('');
    const choices = [
      ...(payload.teams || []).map((team) => ({ name: team.name, type: "team" })),
      ...(payload.members || []).map((member) => ({ name: member.username, type: "user" })),
    ];
    const options = choices.map((choice) => `<button type="button" class="access-choice" data-subject="${esc(choice.name)}" data-type="${choice.type}">${esc(choice.name)}</button>`).join('');
    return `<h1>Manage access</h1><button type="button" id="open-access">Add people or teams</button><form id="access-form" hidden><label for="access-search">Search</label><input id="access-search" type="text"><div id="access-choices">${options}</div><label for="access-role">Role</label><select id="access-role">${roleOptions("Write")}</select><button type="submit">Add</button></form><ul>${grants}</ul>`;
  }
  if (file === 'general') {
    const control = payload.canAdmin
      ? `<button type="button" id="change-visibility">Change visibility</button><div class="dialog-layer" id="visibility-layer" hidden><div role="dialog" aria-label="Change visibility"><label><input type="radio" name="visibility" value="public"> Public</label><button type="button" id="confirm-visibility">Confirm visibility</button></div></div>`
      : '';
    const label = payload.visibility === 'private' ? 'Private' : 'Public';
    return `<h1>General</h1><p>${label}</p><h2>Danger Zone</h2>${control}`;
  }
  return `<h1>Settings</h1><a href="${general}">General</a> <a href="${branches}">Branches</a> <a href="${access}">Manage access</a>`;
}

function newRepoHtml(user, state) {
  const name = state && state.name ? state.name : '';
  const description = state && state.description ? state.description : '';
  const orgs = (state && state.organizations) || [];
  const options = [user.username, ...orgs].map((owner) => `<option value="${esc(owner)}">${esc(owner)}</option>`).join('');
  return `<h1>New repository</h1>${errors(state && state.messages)}<form id="repo-form" novalidate><label>Owner <select name="owner">${options}</select></label><label>Repository name <input name="name" type="text" value="${esc(name)}"></label><label>Description <input name="description" type="text" value="${esc(description)}"></label><label><input type="radio" name="visibility" value="public"> Public</label><label><input type="radio" name="visibility" value="private" checked> Private</label><label><input type="checkbox" name="readme"> Add a README file</label><button type="submit">Create repository</button></form>`;
}

function forkHtml(repo, state) {
  const name = state && state.name ? state.name : `${repo.name}-copy`;
  return `<h1>Fork</h1>${errors(state && state.messages)}<form id="fork-form" novalidate><label>Repository name <input name="name" type="text" value="${esc(name)}"></label><button type="submit">Create fork</button></form>`;
}

async function pageHtml(route, query, user) {
  if (route.page === 'signup') return signupHtml(formState && formState.kind === 'signup' ? formState : null);
  if (route.page === 'signin') return signinHtml(formState && formState.kind === 'signin' ? formState : null);
  if (route.page === 'forgot') return forgotHtml(formState && formState.kind === 'forgot' ? formState : null);
  if (route.page === 'settings' && !route.owner && route.file === 'password') return passwordHtml(formState && formState.kind === 'password' ? formState : null);
  if (route.page === 'settings' && !route.owner) return settingsHtml();
  if (route.page === 'search') return searchHtml(await api('GET', '/api/search?q=' + encodeURIComponent(query)), query);
  if (route.page === 'home') return homeHtml(user);
  if (route.page === 'orgs' && !route.org) return orgsHtml(user ? await api('GET', '/api/orgs') : { organizations: [] });
  if (route.page === 'orgs' && route.org === 'new') return orgFormHtml(formState && formState.kind === 'org' ? formState : null);
  if (route.page === 'orgs' && route.section === 'teams' && route.team === 'new') {
    return teamFormHtml(route.org, formState && formState.kind === 'team' ? formState : null);
  }
  if (route.page === 'orgs' && route.section === 'teams' && route.team) {
    return teamHtml(await api('GET', '/api/orgs/' + encodeURIComponent(route.org) + '/teams/' + encodeURIComponent(route.team)), route.leaf);
  }
  if (route.page === 'orgs' && route.section === 'teams') {
    return teamsHtml(await api('GET', '/api/orgs/' + encodeURIComponent(route.org) + '/teams'));
  }
  if (route.page === 'orgs' && route.section === 'people') {
    return peopleHtml(await api('GET', '/api/orgs/' + encodeURIComponent(route.org) + '/people'), formState && formState.kind === 'person' ? formState : null);
  }
  if (route.page === 'orgs') return orgHtml(await api('GET', '/api/orgs/' + encodeURIComponent(route.org)), route.section);
  if (route.page === 'new') {
    const listed = user ? await api('GET', '/api/orgs') : { organizations: [] };
    const names = (listed.organizations || []).map((org) => org.name);
    return user ? newRepoHtml(user, { ...(formState && formState.kind === 'repo' ? formState : {}), organizations: names }) : `<h1>Sign in</h1>`;
  }
  if (!route.owner) return `<h1>Page not found</h1>`;
  const base = '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo);
  let repo;
  try {
    repo = await api('GET', base);
  } catch (error) {
    if (error && error.message === 'Access denied') return `<h1>Access denied</h1>`;
    return `<h1>Not found</h1>`;
  }
  const branch = new URLSearchParams(location.search).get('branch') || '';
  const branchParam = branch ? '&branch=' + encodeURIComponent(branch) : '';
  if (route.page === 'overview') return overviewHtml(repo);
  if (route.page === 'fork') return forkHtml(repo, formState && formState.kind === 'fork' ? formState : null);
  if (route.page === 'code') return browserHtml(repo, await api('GET', base + '/files' + (branch ? '?branch=' + encodeURIComponent(branch) : '')), '');
  if (route.page === 'tree') return browserHtml(repo, await api('GET', base + '/files' + (branch ? '?branch=' + encodeURIComponent(branch) : '')), route.file);
  if (route.page === 'commits') {
    const filePath = new URLSearchParams(location.search).get('path') || '';
    const extra = (branch ? '?branch=' + encodeURIComponent(branch) : '?') + (filePath ? (branch ? '&' : '') + 'path=' + encodeURIComponent(filePath) : '');
    return commitsHtml(repo, await api('GET', base + '/commits' + extra.replace('??', '?')));
  }
  if (route.page === 'commit') return revisionHtml(repo, await api('GET', base + '/commit/' + encodeURIComponent(route.file)));
  if (route.page === 'compare') {
    const compare = new URLSearchParams(location.search).get('compare') || '';
    return revisionHtml(repo, await api('GET', base + '/commit/' + encodeURIComponent(compare)));
  }
  if (route.page === 'diff') {
    const compare = new URLSearchParams(location.search).get('compare') || '';
    return diffHtml(repo, await api('GET', base + '/commit/' + encodeURIComponent(compare)), route.file);
  }
  if (route.page === 'issues' && route.file === 'new') return issueFormHtml(formState && formState.kind === 'issue' ? formState : null);
  if (route.page === 'issues' && route.file) return issueHtml(await api('GET', base + '/issue/' + encodeURIComponent(route.file)), repo);
  if (route.page === 'issues') {
    const params = new URLSearchParams(location.search);
    const status = params.get('state') || 'open';
    return issuesHtml(repo, await api('GET', base + '/issues'), query, status, params.get('label') || '');
  }
  if (route.page === 'pulls' && route.file === 'new') {
    return compareHtml(repo, await api('GET', base + '/files'), formState && formState.kind === 'pull' ? formState : null);
  }
  if (route.page === 'pulls' && route.file) {
    const [number, tab] = String(route.file).split('/');
    const pull = await api('GET', base + '/pull/' + encodeURIComponent(number));
    if (tab === 'files') return pullFilesHtml(pull, repo);
    if (tab === 'commits') return pullCommitsHtml(pull, repo);
    return pullHtml(pull, repo);
  }
  if (route.page === 'pulls') {
    const pullState = new URLSearchParams(location.search).get('state') || 'open';
    return pullsHtml(repo, await api('GET', base + '/pulls'), pullState);
  }
  if (route.page === 'edit') return editorHtml(repo, formState && formState.kind === 'file' ? formState : null);
  if (route.page === 'settings') {
    const branchPayload = route.file === 'branches' ? await api('GET', base + '/files') : { branches: [] };
    const accessPayload = route.file === 'access' ? await api('GET', base + '/access') : { grants: [], teams: [], members: [] };
    const protection = route.file === 'branches' ? await api('GET', base + '/protection') : {};
    return repoSettingsHtml(repo, route.file, { ...branchPayload, ...accessPayload, protection, canAdmin: repo.canAdmin, isAdmin: repo.isAdmin, visibility: repo.visibility });
  }
  if (route.page === 'find') return findHtml(repo, query);
  if (route.page === 'files') {
    const pathFilter = new URLSearchParams(location.search).get('path') || '';
    const language = new URLSearchParams(location.search).get('language') || '';
    const filesQuery = base + '/files?q=' + encodeURIComponent(query) + (pathFilter ? '&path=' + encodeURIComponent(pathFilter) : '') + (language ? '&language=' + encodeURIComponent(language) : '');
    return filesHtml(repo, await api('GET', filesQuery), query, pathFilter, language);
  }
  if (route.page === 'blob') {
    const file = await api('GET', base + '/blob?path=' + encodeURIComponent(route.file) + branchParam);
    return blobHtml(repo, file);
  }
  return `<h1>Page not found</h1>`;
}

function bind(route) {
  const menu = document.querySelector('#account-menu');
  const panel = document.querySelector('#account-panel');
  const layer = document.querySelector('#signout-layer');
  if (menu && panel) {
    menu.addEventListener('click', () => { panel.hidden = !panel.hidden; });
  }
  const signOut = document.querySelector('#sign-out');
  if (signOut && layer) {
    signOut.addEventListener('click', (event) => {
      event.preventDefault();
      if (panel) panel.hidden = true;
      layer.hidden = false;
    });
  }
  const cancel = document.querySelector('#cancel-signout');
  if (cancel && layer) cancel.addEventListener('click', () => { layer.hidden = true; });
  const confirm = document.querySelector('#confirm-signout');
  if (confirm) {
    confirm.addEventListener('click', async () => {
      await api('POST', '/api/logout', {});
      location.reload();
    });
  }
  const register = document.querySelector('#register-form');
  if (register) {
    register.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(register));
      try {
        await api('POST', '/api/register', {
          username: data.username || '',
          email: data.email || '',
          password: data.password || '',
          confirm: data.confirm || '',
          terms: data.terms === 'on',
        });
        formState = null;
        location.assign('/signin');
      } catch (error) {
        formState = {
          kind: 'signup',
          username: data.username || '',
          email: data.email || '',
          messages: (error.data && error.data.messages) || [error.message],
        };
        render();
      }
    });
  }
  const password = document.querySelector('#password-form');
  if (password) {
    password.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(password));
      try {
        const result = await api('POST', '/api/password', {
          current: data.current || '',
          password: data.password || '',
          confirm: data.confirm || '',
        });
        formState = { kind: 'password', messages: [result.message || 'Password updated'] };
        render();
      } catch (error) {
        formState = { kind: 'password', messages: [error.message] };
        render();
      }
    });
  }
  const branchSelect = document.querySelector('#branch-select');
  if (branchSelect) {
    branchSelect.addEventListener('change', () => {
      const url = new URL(location.href);
      url.searchParams.set('branch', branchSelect.value);
      location.assign(url.pathname + url.search);
    });
  }
  const login = document.querySelector('#login-form');
  if (login) {
    login.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(login));
      try {
        await api('POST', '/api/login', { identifier: data.identifier || '', password: data.password || '' });
        formState = null;
        location.assign('/');
      } catch (error) {
        formState = { kind: 'signin', identifier: data.identifier || '', message: error.message };
        render();
      }
    });
  }
  const forgot = document.querySelector('#forgot-form');
  if (forgot) {
    forgot.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(forgot));
      try {
        const result = await api('POST', '/api/recover/start', { email: data.email || '' });
        formState = { kind: 'forgot', email: data.email || '', code: result.code, messages: [] };
        render();
      } catch (error) {
        formState = {
          kind: 'forgot',
          email: data.email || '',
          messages: (error.data && error.data.messages) || [error.message],
        };
        render();
      }
    });
  }
  const reset = document.querySelector('#reset-form');
  if (reset) {
    reset.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(reset));
      try {
        const result = await api('POST', '/api/recover/finish', {
          email: data.email || '',
          code: data.code || '',
          password: data.password || '',
          confirm: data.confirm || '',
        });
        formState = null;
        document.querySelector('#page').innerHTML = `<h1>${esc(result.message || 'Password updated')}</h1>`;
      } catch (error) {
        formState = {
          kind: 'forgot',
          email: data.email || '',
          code: '123456',
          messages: [error.message],
        };
        render();
      }
    });
  }
  const orgForm = document.querySelector('#org-form');
  if (orgForm) {
    orgForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(orgForm));
      try {
        const result = await api('POST', '/api/orgs', { name: data.name || '', displayName: data.displayName || '' });
        formState = null;
        location.assign('/orgs/' + encodeURIComponent(result.name));
      } catch (error) {
        formState = {
          kind: 'org',
          name: data.name || '',
          displayName: data.displayName || '',
          messages: (error.data && error.data.messages) || [error.message],
        };
        render();
      }
    });
  }
  const repoForm = document.querySelector('#repo-form');
  if (repoForm) {
    repoForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(repoForm));
      try {
        const result = await api('POST', '/api/repos', {
          owner: data.owner || '',
          name: data.name || '',
          description: data.description || '',
          visibility: data.visibility || 'public',
          readme: data.readme === 'on',
        });
        formState = null;
        location.assign('/' + encodeURIComponent(result.owner) + '/' + encodeURIComponent(result.name));
      } catch (error) {
        formState = {
          kind: 'repo',
          name: data.name || '',
          description: data.description || '',
          messages: (error.data && error.data.messages) || [error.message],
        };
        render();
      }
    });
  }
  const forkForm = document.querySelector('#fork-form');
  if (forkForm && route.owner && route.repo) {
    forkForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(forkForm));
      try {
        const result = await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/fork', {
          name: data.name || '',
        });
        formState = null;
        location.assign('/' + encodeURIComponent(result.owner) + '/' + encodeURIComponent(result.name));
      } catch (error) {
        formState = { kind: 'fork', name: data.name || '', messages: [error.message] };
        render();
      }
    });
  }
  const openFork = document.querySelector('#open-fork');
  if (openFork && route.owner && route.repo) {
    openFork.addEventListener('click', () => {
      location.assign('/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/fork');
    });
  }
  const cloneCode = document.querySelector('#clone-code');
  const clonePanel = document.querySelector('#clone-panel');
  if (cloneCode && clonePanel) cloneCode.addEventListener('click', () => { clonePanel.hidden = !clonePanel.hidden; });
  const cloneValue = document.querySelector('#clone-value');
  const cloneHttps = document.querySelector('#clone-https');
  const cloneSsh = document.querySelector('#clone-ssh');
  if (cloneHttps && cloneValue) {
    cloneHttps.addEventListener('click', () => { cloneValue.textContent = cloneValue.dataset.https || ''; });
  }
  if (cloneSsh && cloneValue) {
    cloneSsh.addEventListener('click', () => { cloneValue.textContent = cloneValue.dataset.ssh || ''; });
  }
  const copyClone = document.querySelector('#copy-clone');
  if (copyClone && cloneValue) {
    copyClone.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(cloneValue.textContent || ''); } catch (error) { void error; }
      const copied = document.querySelector('#copied');
      if (copied) copied.hidden = false;
    });
  }
  const repoFilter = document.querySelector('#repo-filter');
  const visibilityFilter = document.querySelector('#visibility-filter');
  const applyRepoFilter = () => {
    const queryText = repoFilter ? repoFilter.value : '';
    const visibility = visibilityFilter ? visibilityFilter.value : 'All';
    document.querySelectorAll('#repo-list li').forEach((item) => {
      const name = item.getAttribute('data-name') || '';
      const itemVisibility = item.getAttribute('data-visibility') || '';
      const nameOk = !queryText || name.includes(queryText);
      const visibilityOk = visibility === 'All' || itemVisibility === visibility;
      item.hidden = !(nameOk && visibilityOk);
    });
  };
  if (repoFilter) repoFilter.addEventListener('input', applyRepoFilter);
  if (visibilityFilter) visibilityFilter.addEventListener('change', applyRepoFilter);
  const branchQueryBox = document.querySelector('#branch-query');
  const createBranch = document.querySelector('#create-branch');
  const branchEmpty = document.querySelector('#branch-empty');
  const branchPanel = document.querySelector('#branch-panel');
  const branchToggle = document.querySelector('#branch-toggle');
  const branchError = document.querySelector('#branch-error');
  const applyBranchQuery = () => {
    if (!branchQueryBox) return;
    const text = branchQueryBox.value.trim();
    const open = branchPanel ? !branchPanel.hidden : true;
    let visible = 0;
    document.querySelectorAll('.branch-option').forEach((button) => {
      const name = button.getAttribute('data-branch') || '';
      const show = open && (!text || name.includes(text));
      button.hidden = !show;
      if (show) visible += 1;
    });
    if (branchEmpty) branchEmpty.hidden = !(open && text && visible === 0);
    const valid = /^[A-Za-z0-9._/-]+$/.test(text) && !text.endsWith('/') && !text.endsWith('.') && !text.includes('..') && !text.includes('//');
    const exists = [...document.querySelectorAll('.branch-option')].some((button) => button.getAttribute('data-branch') === text);
    if (createBranch) {
      createBranch.hidden = !(open && text && valid && !exists);
      createBranch.textContent = `Create branch: ${text}`;
    }
    if (branchError && text && !valid) {
      branchError.hidden = false;
      branchError.textContent = 'Invalid branch';
    } else if (branchError && branchError.textContent === 'Invalid branch') {
      branchError.hidden = true;
    }
  };
  if (branchToggle && branchPanel) {
    branchToggle.addEventListener('click', () => {
      branchPanel.hidden = !branchPanel.hidden;
      branchToggle.setAttribute('aria-expanded', branchPanel.hidden ? 'false' : 'true');
      applyBranchQuery();
    });
    if (window.__branchKeys) document.removeEventListener('keydown', window.__branchKeys);
    window.__branchKeys = (event) => {
      if (event.key !== 'Escape' || branchPanel.hidden) return;
      branchPanel.hidden = true;
      branchToggle.setAttribute('aria-expanded', 'false');
      document.querySelectorAll('.branch-option').forEach((button) => { button.hidden = true; });
      if (branchEmpty) branchEmpty.hidden = true;
      if (createBranch) createBranch.hidden = true;
    };
    document.addEventListener('keydown', window.__branchKeys);
  }
  if (branchQueryBox) {
    branchQueryBox.addEventListener('input', applyBranchQuery);
    document.querySelectorAll('.branch-option').forEach((button) => {
      button.addEventListener('click', () => {
        const name = button.getAttribute('data-branch') || '';
        const url = new URL(location.href);
        url.searchParams.set('branch', name);
        location.assign(url.pathname + url.search);
      });
    });
  }
  if (createBranch && route.owner && route.repo) {
    createBranch.addEventListener('click', async () => {
      const name = (branchQueryBox && branchQueryBox.value || '').trim();
      try {
        await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/branch', { name });
        location.assign(location.pathname + '?branch=' + encodeURIComponent(name));
      } catch (error) {
        const slot = document.querySelector('#branch-error');
        if (slot) {
          slot.hidden = false;
          slot.textContent = error.message;
        }
      }
    });
  }
  const teamForm = document.querySelector('#team-form');
  if (teamForm && route.org) {
    teamForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(teamForm));
      try {
        const result = await api('POST', '/api/orgs/' + encodeURIComponent(route.org) + '/teams', { name: data.name || '' });
        formState = null;
        location.assign('/orgs/' + encodeURIComponent(route.org) + '/teams/' + encodeURIComponent(result.name));
      } catch (error) {
        formState = { kind: 'team', name: data.name || '', messages: [error.message] };
        render();
      }
    });
  }
  const openTeamMember = document.querySelector('#open-team-member');
  const teamMemberForm = document.querySelector('#team-member-form');
  if (openTeamMember && teamMemberForm) {
    openTeamMember.addEventListener('click', () => {
      openTeamMember.hidden = true;
      teamMemberForm.hidden = false;
    });
  }
  if (teamMemberForm && route.org && route.team) {
    teamMemberForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(teamMemberForm));
      await api('POST', '/api/orgs/' + encodeURIComponent(route.org) + '/teams/' + encodeURIComponent(route.team), {
        action: 'add-member', username: data.username || '',
      });
      render();
    });
  }
  document.querySelectorAll('.remove-team-member').forEach((button) => {
    button.addEventListener('click', async () => {
      await api('POST', '/api/orgs/' + encodeURIComponent(route.org) + '/teams/' + encodeURIComponent(route.team), {
        action: 'remove-member', username: button.getAttribute('data-user') || '',
      });
      render();
    });
  });
  const parentForm = document.querySelector('#team-parent-form');
  if (parentForm && route.org && route.team) {
    parentForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const parent = document.querySelector('#parent-team');
      try {
        await api('POST', '/api/orgs/' + encodeURIComponent(route.org) + '/teams/' + encodeURIComponent(route.team), {
          parent: parent ? parent.value : '',
        });
        render();
      } catch (error) {
        const slot = document.querySelector('#team-parent-error');
        if (slot) {
          slot.hidden = false;
          slot.textContent = error.message;
        }
      }
    });
  }
  const openPerson = document.querySelector('#open-person');
  const personForm = document.querySelector('#person-form');
  if (openPerson && personForm) {
    openPerson.addEventListener('click', () => {
      openPerson.hidden = true;
      personForm.hidden = false;
    });
  }
  if (personForm && route.org) {
    personForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(personForm));
      try {
        await api('POST', '/api/orgs/' + encodeURIComponent(route.org) + '/people', {
          username: data.username || '', role: data.role || 'Member',
        });
        formState = null;
        render();
      } catch (error) {
        formState = { kind: 'person', username: data.username || '', messages: [error.message] };
        render();
      }
    });
  }
  let pendingRemoval = '';
  document.querySelectorAll('.member-menu').forEach((button) => {
    button.addEventListener('click', () => {
      const menu = button.nextElementSibling;
      if (menu) menu.hidden = !menu.hidden;
    });
  });
  document.querySelectorAll('.remove-org-member').forEach((button) => {
    button.addEventListener('click', () => {
      pendingRemoval = button.getAttribute('data-user') || '';
      const layer = document.querySelector('#remove-member-layer');
      if (layer) layer.hidden = false;
    });
  });
  const confirmRemoval = document.querySelector('#confirm-remove-member');
  if (confirmRemoval && route.org) {
    confirmRemoval.addEventListener('click', async () => {
      await api('POST', '/api/orgs/' + encodeURIComponent(route.org) + '/people', { action: 'remove', username: pendingRemoval });
      render();
    });
  }
  const cancelRemoval = document.querySelector('#cancel-remove-member');
  if (cancelRemoval) {
    cancelRemoval.addEventListener('click', () => {
      const layer = document.querySelector('#remove-member-layer');
      if (layer) layer.hidden = true;
    });
  }
  const issueSearch = document.querySelector('#issue-search');
  let issueLabel = '';
  const applyIssueFilter = () => {
    const text = issueSearch ? issueSearch.value.toLowerCase() : '';
    const url = new URL(location.href);
    if (issueSearch && issueSearch.value) url.searchParams.set('q', issueSearch.value);
    else url.searchParams.delete('q');
    if (issueLabel) url.searchParams.set('label', issueLabel);
    else url.searchParams.delete('label');
    history.replaceState(null, '', url);
    document.querySelectorAll('#issue-list li').forEach((item) => {
      const textOk = !text || (item.getAttribute('data-text') || '').toLowerCase().includes(text);
      const labelOk = !issueLabel || (item.getAttribute('data-labels') || '').split(' ').includes(issueLabel);
      item.hidden = !(textOk && labelOk);
    });
  };
  if (issueSearch) issueSearch.addEventListener('input', applyIssueFilter);
  document.querySelectorAll('.issue-label').forEach((button) => {
    button.addEventListener('click', () => {
      issueLabel = button.getAttribute('data-label') || '';
      applyIssueFilter();
    });
  });
  const prAuthor = document.querySelector('#pr-author');
  if (prAuthor) {
    prAuthor.addEventListener('input', () => {
      const text = prAuthor.value.toLowerCase();
      document.querySelectorAll('#pr-list li').forEach((item) => {
        item.hidden = text && !(item.getAttribute('data-author') || '').toLowerCase().includes(text);
      });
    });
  }
  const issueForm = document.querySelector('#issue-form');
  if (issueForm && route.owner && route.repo) {
    issueForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(issueForm));
      try {
        const result = await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/issue', {
          title: data.title || '', body: data.body || '',
        });
        formState = null;
        location.assign('/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/issues/' + result.number);
      } catch (error) {
        formState = { kind: 'issue', title: data.title || '', body: data.body || '', messages: [error.message] };
        render();
      }
    });
  }
  const closeIssue = document.querySelector('#close-issue');
  const reopenIssue = document.querySelector('#reopen-issue');
  const setIssueState = async (state) => {
    await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/issue-state', {
      number: Number(route.file), state,
    });
    render();
  };
  if (closeIssue) closeIssue.addEventListener('click', () => setIssueState('closed'));
  if (reopenIssue) reopenIssue.addEventListener('click', () => setIssueState('open'));
  const fileForm = document.querySelector('#file-form');
  if (fileForm && route.owner && route.repo) {
    fileForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(fileForm));
      const branch = new URLSearchParams(location.search).get('branch') || '';
      try {
        const result = await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/file', {
          path: data.path || '', content: data.content || '', message: data.message || '', branch,
          replace: Boolean(data.original) && data.original === (data.path || ''),
        });
        formState = null;
        const branchQuery = branch ? '?branch=' + encodeURIComponent(branch) : '';
        location.assign('/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/blob/' + encodeURIComponent(result.path) + branchQuery);
      } catch (error) {
        formState = { kind: 'file', path: data.path || '', original: data.original || '', content: data.content || '', messages: [error.message] };
        render();
      }
    });
  }
  const mergeButton = document.querySelector('#merge-pr');
  const mergeLayer = document.querySelector('#merge-layer');
  if (mergeButton && mergeLayer) mergeButton.addEventListener('click', () => { mergeLayer.hidden = false; });
  const confirmMerge = document.querySelector('#confirm-merge');
  if (confirmMerge && route.owner && route.repo) {
    confirmMerge.addEventListener('click', async () => {
      await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/pull-state', {
        number: Number(route.file), action: 'merge',
      });
      render();
    });
  }
  const closePr = document.querySelector('#close-pr');
  const reopenPr = document.querySelector('#reopen-pr');
  const setPullState = async (state) => {
    await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/pull-state', {
      number: Number(route.file), state,
    });
    render();
  };
  if (closePr) closePr.addEventListener('click', () => setPullState('closed'));
  if (reopenPr) reopenPr.addEventListener('click', () => setPullState('open'));
  const openAccess = document.querySelector('#open-access');
  const accessForm = document.querySelector('#access-form');
  if (openAccess && accessForm) {
    openAccess.addEventListener('click', () => {
      openAccess.hidden = true;
      accessForm.hidden = false;
    });
  }
  const accessSearch = document.querySelector('#access-search');
  if (accessSearch) {
    accessSearch.addEventListener('input', () => {
      const text = accessSearch.value.toLowerCase();
      document.querySelectorAll('.access-choice').forEach((button) => {
        button.hidden = text && !(button.getAttribute('data-subject') || '').toLowerCase().includes(text);
      });
    });
  }
  let accessSubject = '';
  let accessType = 'team';
  document.querySelectorAll('.access-choice').forEach((button) => {
    button.addEventListener('click', () => {
      accessSubject = button.getAttribute('data-subject') || '';
      accessType = button.getAttribute('data-type') || 'team';
    });
  });
  if (accessForm && route.owner && route.repo) {
    accessForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const role = document.querySelector('#access-role');
      await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/access', {
        subject: accessSubject, subjectType: accessType, role: role ? role.value : 'Write',
      });
      render();
    });
  }
  document.querySelectorAll('.save-grant').forEach((button) => {
    button.addEventListener('click', async () => {
      const subject = button.getAttribute('data-subject') || '';
      const select = document.querySelector(`.grant-role[data-subject="${subject}"]`);
      await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/access', {
        subject, subjectType: button.getAttribute('data-type') || 'team', role: select ? select.value : 'Read',
      });
      render();
    });
  });
  const defaultBranchForm = document.querySelector('#default-branch-form');
  const branchConfirm = document.querySelector('#branch-confirm');
  if (defaultBranchForm && branchConfirm) {
    defaultBranchForm.addEventListener('submit', (event) => {
      event.preventDefault();
      branchConfirm.hidden = false;
    });
  }
  const confirmDefault = document.querySelector('#confirm-default-branch');
  if (confirmDefault && route.owner && route.repo) {
    confirmDefault.addEventListener('click', async () => {
      const select = document.querySelector('#default-branch');
      await api('POST', '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/default-branch', {
        branch: select ? select.value : '',
      });
      render();
    });
  }
  bindCollaboration(route);
  void route;
  void routes;
}

function repoApi(route, action) {
  return '/api/repos/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/' + action;
}

function bindCollaboration(route) {
  const number = Number(String(route.file || '').split('/')[0]);
  const show = (id) => {
    const node = document.querySelector(id);
    if (node) node.hidden = false;
  };
  const editTitle = document.querySelector('#edit-title');
  const titleForm = document.querySelector('#title-form');
  if (editTitle && titleForm) editTitle.addEventListener('click', () => { editTitle.hidden = true; titleForm.hidden = false; });
  if (titleForm) {
    titleForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const input = document.querySelector('#issue-title');
      try {
        await api('POST', repoApi(route, 'issue-edit'), { number, field: 'title', value: input ? input.value : '' });
        render();
      } catch (error) {
        const slot = document.querySelector('#title-error');
        if (slot) {
          slot.hidden = false;
          slot.textContent = error.message;
        }
      }
    });
  }
  const editBody = document.querySelector('#edit-body');
  const bodyForm = document.querySelector('#body-form');
  if (editBody && bodyForm) editBody.addEventListener('click', () => { editBody.hidden = true; bodyForm.hidden = false; });
  if (bodyForm) {
    bodyForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const input = document.querySelector('#issue-description');
      await api('POST', repoApi(route, 'issue-edit'), { number, field: 'body', value: input ? input.value : '' });
      render();
    });
  }
  const commentForm = document.querySelector('#comment-form');
  if (commentForm) {
    commentForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const input = document.querySelector('#comment-body');
      try {
        await api('POST', repoApi(route, 'issue-comment'), { number, body: input ? input.value : '' });
        render();
      } catch (error) {
        const slot = document.querySelector('#comment-error');
        if (slot) {
          slot.hidden = false;
          slot.textContent = error.message;
        }
      }
    });
  }
  document.querySelectorAll('.reaction-open').forEach((button) => {
    button.addEventListener('click', () => {
      const menu = button.nextElementSibling;
      if (menu) menu.hidden = !menu.hidden;
    });
  });
  document.querySelectorAll('.react-plus').forEach((button) => {
    button.addEventListener('click', async () => {
      await api('POST', repoApi(route, 'issue-react'), { number, index: Number(button.getAttribute('data-index') || 0), reaction: '+1' });
      render();
    });
  });
  const wirePicker = (buttonId, pickerId) => {
    const button = document.querySelector(buttonId);
    const picker = document.querySelector(pickerId);
    if (button && picker) button.addEventListener('click', () => { picker.hidden = !picker.hidden; });
  };
  wirePicker('#open-assignees', '#assignee-picker');
  wirePicker('#open-labels', '#label-picker');
  wirePicker('#open-milestone', '#milestone-picker');
  wirePicker('#open-reviewers', '#reviewer-picker');
  document.querySelectorAll('.assignee-option').forEach((button) => {
    button.addEventListener('click', async () => {
      await api('POST', repoApi(route, 'issue-meta'), { number, kind: 'assign', value: button.textContent || '' });
      render();
    });
  });
  document.querySelectorAll('.label-option').forEach((button) => {
    button.addEventListener('click', async () => {
      await api('POST', repoApi(route, 'issue-meta'), { number, kind: 'label', value: button.textContent || '' });
      render();
    });
  });
  document.querySelectorAll('.milestone-option').forEach((button) => {
    button.addEventListener('click', async () => {
      const endpoint = route.page === 'pulls' ? 'pull-milestone' : 'issue-meta';
      const payload = route.page === 'pulls'
        ? { number, value: button.textContent || '' }
        : { number, kind: 'milestone', value: button.textContent || '' };
      await api('POST', repoApi(route, endpoint), payload);
      render();
    });
  });
  const assigneeSearch = document.querySelector('#assignee-search');
  if (assigneeSearch) {
    assigneeSearch.addEventListener('input', () => {
      const text = assigneeSearch.value.toLowerCase();
      document.querySelectorAll('.assignee-option').forEach((button) => {
        button.hidden = text && !(button.textContent || '').toLowerCase().includes(text);
      });
    });
  }
  const reviewerSearch = document.querySelector('#reviewer-search');
  if (reviewerSearch) {
    reviewerSearch.addEventListener('input', () => {
      const text = reviewerSearch.value;
      document.querySelectorAll('.reviewer-option').forEach((button) => {
        const name = button.getAttribute('data-user') || '';
        button.hidden = !text || !name.includes(text);
      });
    });
  }
  document.querySelectorAll('.reviewer-option').forEach((button) => {
    button.addEventListener('click', async () => {
      await api('POST', repoApi(route, 'pull-reviewer'), { number, username: button.getAttribute('data-user') || '' });
      render();
    });
  });
  document.querySelectorAll('.remove-reviewer').forEach((button) => {
    button.addEventListener('click', async () => {
      await api('POST', repoApi(route, 'pull-reviewer'), { number, username: button.getAttribute('data-user') || '', remove: true });
      render();
    });
  });
  const ready = document.querySelector('#ready-review');
  if (ready) {
    ready.addEventListener('click', async () => {
      await api('POST', repoApi(route, 'pull-state'), { number, action: 'ready' });
      render();
    });
  }
  const addLine = document.querySelector('#add-line-comment');
  const lineForm = document.querySelector('#line-comment-form');
  if (addLine && lineForm) addLine.addEventListener('click', () => { lineForm.hidden = false; });
  const showLineError = (message) => {
    const slot = document.querySelector('#line-comment-error');
    if (!slot) return;
    slot.hidden = false;
    slot.textContent = message;
  };
  if (lineForm) {
    lineForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const input = document.querySelector('#line-comment');
      const text = input ? input.value : '';
      if (!text.trim()) {
        showLineError('Comment is required');
        return;
      }
      try {
        await api('POST', repoApi(route, 'pull-line'), { number, body: text });
        render();
      } catch (error) {
        showLineError(error.message);
      }
    });
  }
  const startReview = document.querySelector('#start-review');
  if (startReview) {
    startReview.addEventListener('click', async () => {
      const input = document.querySelector('#line-comment');
      const text = input ? input.value : '';
      if (!text.trim()) {
        showLineError('Comment is required');
        return;
      }
      try {
        await api('POST', repoApi(route, 'pull-line'), { number, body: text, pending: true });
        render();
      } catch (error) {
        showLineError(error.message);
      }
    });
  }
  const openReview = document.querySelector('#open-review');
  const reviewForm = document.querySelector('#review-form');
  if (openReview && reviewForm) openReview.addEventListener('click', () => { reviewForm.hidden = false; });
  if (reviewForm) {
    reviewForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const selected = reviewForm.querySelector('input[name="decision"]:checked');
      const summary = document.querySelector('#review-summary');
      await api('POST', repoApi(route, 'pull-review'), {
        number,
        decision: selected ? selected.value : 'Comment',
        summary: summary ? summary.value : '',
      });
      render();
    });
  }
  const syncCompare = () => {
    const base = document.querySelector('#pr-base');
    const compare = document.querySelector('#pr-compare');
    const openPr = document.querySelector('#open-pr');
    const openDraft = document.querySelector('#open-draft');
    if (!base || !compare) return;
    const blocked = base.value === compare.value;
    if (openPr) openPr.disabled = blocked;
    if (openDraft) openDraft.disabled = blocked;
    const file = document.querySelector('#compare-file');
    const summary = document.querySelector('#commit-summary');
    const count = document.querySelector('#commit-count');
    if (file) file.hidden = blocked;
    if (summary) summary.hidden = blocked;
    if (count) count.hidden = blocked;
    const note = document.querySelector('#compare-note');
    if (note) note.textContent = blocked ? 'No changes' : '';
  };
  const baseSelect = document.querySelector('#pr-base');
  const compareSelect = document.querySelector('#pr-compare');
  if (baseSelect) baseSelect.addEventListener('change', syncCompare);
  if (compareSelect) compareSelect.addEventListener('change', syncCompare);
  const compareChanges = document.querySelector('#compare-changes');
  if (compareChanges) compareChanges.addEventListener('click', syncCompare);
  syncCompare();
  let draftMode = false;
  const openPr = document.querySelector('#open-pr');
  const openDraft = document.querySelector('#open-draft');
  const prForm = document.querySelector('#pr-form');
  const revealPr = (draft) => {
    draftMode = draft;
    if (openPr) openPr.hidden = true;
    if (openDraft) openDraft.hidden = true;
    if (prForm) prForm.hidden = false;
    const submit = document.querySelector('#submit-pr');
    if (submit) submit.textContent = draft ? 'Create draft pull request' : 'Create pull request';
  };
  if (openPr) openPr.addEventListener('click', () => revealPr(false));
  if (openDraft) openDraft.addEventListener('click', () => revealPr(true));
  if (prForm) {
    prForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(prForm));
      try {
        const result = await api('POST', repoApi(route, 'pull-create'), {
          title: data.title || '',
          body: data.body || '',
          base: baseSelect ? baseSelect.value : 'main',
          head: compareSelect ? compareSelect.value : 'feature-search',
          draft: draftMode,
        });
        location.assign('/' + encodeURIComponent(route.owner) + '/' + encodeURIComponent(route.repo) + '/pulls/' + result.number);
      } catch (error) {
        formState = { kind: 'pull', title: data.title || '', messages: [error.message] };
        render();
      }
    });
  }
  const changeVisibility = document.querySelector('#change-visibility');
  const visibilityLayer = document.querySelector('#visibility-layer');
  if (changeVisibility && visibilityLayer) changeVisibility.addEventListener('click', () => { visibilityLayer.hidden = false; });
  const confirmVisibility = document.querySelector('#confirm-visibility');
  if (confirmVisibility) {
    confirmVisibility.addEventListener('click', async () => {
      await api('POST', repoApi(route, 'visibility'), { visibility: 'public' });
      render();
    });
  }
  const addProtection = document.querySelector('#add-protection');
  const protectionForm = document.querySelector('#protection-form');
  if (addProtection && protectionForm) addProtection.addEventListener('click', () => { protectionForm.hidden = false; });
  if (protectionForm) {
    protectionForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const review = document.querySelector('#protect-review');
      const check = document.querySelector('#protect-check');
      const branch = document.querySelector('#protect-branch');
      await api('POST', repoApi(route, 'protection'), {
        branch: branch ? branch.value : 'main',
        review: Boolean(review && review.checked),
        check: Boolean(check && check.checked),
      });
      render();
    });
  }
  const saveCheck = document.querySelector('#save-check');
  if (saveCheck && route.owner && route.repo) {
    saveCheck.addEventListener('click', async () => {
      const status = document.querySelector('#test-status');
      await api('POST', repoApi(route, 'pull-check'), {
        number: Number(String(route.file || '').split('/')[0]),
        status: status ? status.value : 'pending',
      });
      render();
    });
  }
}

async function render() {
  const route = routeOf(location.pathname);
  const query = new URLSearchParams(location.search).get('q') || '';
  const session = await api('GET', '/api/session');
  const page = await pageHtml(route, query, session.user);
  document.querySelector('#app').innerHTML = `${shell(session.user, query, route)}${page}</div>`;
  bind(route);
}

render();
