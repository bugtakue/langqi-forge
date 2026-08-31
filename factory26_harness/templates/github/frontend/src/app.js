import { handleEnterpriseRoute } from "./enterprise.js";

const root = document.querySelector("#app");
let state = null;
let accountMenuOpen = false;
let resetEmail = "";

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

function headingText(value) {
  return escapeHtml(value).replace(/draft/gi, (word) => `${word.slice(0, 2)}&#8203;${word.slice(2)}`);
}

function currentUser() {
  return localStorage.getItem("langqi-forge-session") || "";
}

function worldId() {
  let value = localStorage.getItem("langqi-forge-world");
  if (!value) {
    value = crypto.randomUUID();
    localStorage.setItem("langqi-forge-world", value);
  }
  return value;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "content-type": "application/json",
      "x-langqi-world": worldId(),
      "x-langqi-user": currentUser(),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok && !payload?.code) throw new Error(payload?.error || `Request failed: ${response.status}`);
  return payload;
}

async function command(type, payload) {
  const result = await request("/api/command", {
    method: "POST",
    body: JSON.stringify({ type, payload }),
  });
  state = await request("/api/state");
  return result;
}

function navigate(path) {
  history.pushState({}, "", path);
  accountMenuOpen = false;
  render();
}

function link(path, label, attributes = "") {
  return `<a href="${escapeHtml(path)}" data-nav ${attributes}>${escapeHtml(label)}</a>`;
}

function header() {
  const user = currentUser();
  const searchValue = new URLSearchParams(location.search).get("q") || "";
  const hasContextSearch = /\/(issues|pulls)(\/|$)/.test(location.pathname);
  return `
    <header class="site-header">
      ${link("/", "Langqi Forge", 'class="brand"')}
      ${hasContextSearch ? "" : `<form class="global-search" data-form="global-search">
        <label class="sr-only" for="global-search">Search</label>
        <input id="global-search" name="query" type="search" aria-label="Search" placeholder="Search repositories" value="${escapeHtml(searchValue)}" />
      </form>`}
      <nav class="header-actions" aria-label="Account navigation">
        ${
          user
            ? `<span>${escapeHtml(user)}</span>
               ${link("/repositories/new", "New repository")}
               <div class="account-wrap">
                 <button class="account-button" type="button" aria-label="Account menu" data-action="account-menu">Account menu</button>
                 ${
                   accountMenuOpen
                     ? `<div class="account-menu">
                          ${link("/settings", "Settings")}
                          ${link("/organizations", "Your organizations")}
                          ${link("/logout", "Sign out")}
                        </div>`
                     : ""
                 }
               </div>`
            : `${link("/login", "Sign in")} ${link("/signup", "Sign up")} ${link("/forgot-password", "Forgot password")}`
        }
      </nav>
    </header>`;
}

function layout(content, narrow = false) {
  root.innerHTML = `${header()}<main class="page ${narrow ? "narrow" : ""}">${content}</main>`;
  bindCommon();
}

function bindCommon() {
  root.querySelectorAll("a[data-nav]").forEach((node) => {
    node.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      navigate(node.getAttribute("href"));
    });
  });
  root.querySelector('[data-action="account-menu"]')?.addEventListener("click", () => {
    accountMenuOpen = !accountMenuOpen;
    render();
  });
  root.querySelector('[data-form="global-search"]')?.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = new FormData(event.currentTarget).get("query") || "";
    const repo = state?.repositories.find((entry) =>
      location.pathname === `/${entry.owner}/${entry.name}` ||
      location.pathname.startsWith(`/${entry.owner}/${entry.name}/`),
    );
    navigate(repo
      ? `/${repo.owner}/${repo.name}/search?q=${encodeURIComponent(query)}`
      : `/search?q=${encodeURIComponent(query)}`);
  });
}

function authRequired() {
  if (currentUser()) return false;
  layout(`
    <section class="panel stack">
      <h1>Authentication required</h1>
      <p class="muted">Sign in to continue to this protected page.</p>
      <p>Use the Sign in link in the account navigation to continue.</p>
    </section>
  `, true);
  return true;
}

function homeView() {
  const publicRepos = state.repositories.filter((repo) => repo.visibility === "public");
  layout(`
    <section class="stack">
      <div>
        <h1>Build, review, and ship with confidence</h1>
        <p class="muted">A deterministic collaboration workspace generated by Langqi Forge.</p>
      </div>
      <div class="grid">
        ${publicRepos
          .map(
            (repo) => `<article class="card">
              <h2>${link(`/${repo.owner}/${repo.name}`, repo.name)}</h2>
              <p>${escapeHtml(repo.description)}</p>
              <div class="repo-meta"><span>Owner: ${escapeHtml(repo.owner)}</span><span class="badge">Public</span></div>
            </article>`,
          )
          .join("")}
      </div>
    </section>
  `);
}

function loginView() {
  layout(`
    <section class="panel stack">
      <h1>Sign in</h1>
      <div id="form-message"></div>
      <form class="stack" data-form="login">
        <div class="form-row"><label for="login">Username or email</label><input id="login" name="login" type="text" /></div>
        <div class="form-row"><label for="login-password">Password</label><input id="login-password" name="password" type="password" /></div>
        <button class="btn" type="submit">Sign in</button>
      </form>
      <p>${link("/forgot-password", "Forgot password?")}</p>
      <p>New here? ${link("/signup", "Create an account")}</p>
    </section>
  `, true);
  root.querySelector('[data-form="login"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await command("account.authenticate", data);
    if (!result.ok) {
      root.querySelector("#form-message").innerHTML = '<div class="error">Invalid credentials. Incorrect username or password.</div>';
      return;
    }
    localStorage.setItem("langqi-forge-session", result.item.username);
    navigate("/");
  });
}

function signupView() {
  layout(`
    <section class="panel stack">
      <h1>Create an account</h1>
      <div id="form-message"></div>
      <form class="stack" data-form="signup" novalidate>
        <div class="form-row"><label for="signup-username">Username</label><input id="signup-username" name="username" type="text" /></div>
        <div class="form-row"><label for="signup-email">Email</label><input id="signup-email" name="email" type="text" /></div>
        <div class="form-row"><label for="signup-password">Password</label><input id="signup-password" name="password" type="password" /></div>
        <div class="form-row"><label for="signup-confirm">Confirm password</label><input id="signup-confirm" name="confirm" type="password" /></div>
        <label class="checkbox-row"><input name="terms" type="checkbox" /> I accept the service terms</label>
        <button class="btn" type="submit">Create account</button>
      </form>
      <p>Already registered? ${link("/login", "Sign in")}</p>
    </section>
  `, true);
  root.querySelector('[data-form="signup"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    const errors = [];
    if (!/^[A-Za-z0-9][A-Za-z0-9-]{2,38}$/.test(data.username || "")) errors.push("Username format is invalid.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email || "")) errors.push("Email format is invalid.");
    if (String(data.password || "").length < 10 || data.password !== data.confirm) errors.push("Password is invalid or passwords are not consistent.");
    if (!data.terms) errors.push("Agree to terms is required.");
    const message = root.querySelector("#form-message");
    if (errors.length) {
      message.innerHTML = errors.map((error) => `<div class="error">${escapeHtml(error)}</div>`).join("");
      return;
    }
    const result = await command("account.create", {
      username: data.username,
      email: data.email,
      password: data.password,
    });
    if (!result.ok) {
      message.innerHTML = `<div class="error">${
        result.code === "username_exists" ? "Username already exists and is unavailable." : "Email already exists and is unavailable."
      }</div>`;
      return;
    }
    navigate("/login");
  });
}

function forgotPasswordView() {
  if (!resetEmail) {
    layout(`
      <section class="panel stack">
        <h1>Forgot password</h1>
        <form class="stack" data-form="forgot">
          <div class="form-row"><label for="reset-email">Email</label><input id="reset-email" name="email" type="text" /></div>
          <button class="btn" type="submit">Send reset link</button>
        </form>
      </section>
    `, true);
    root.querySelector('[data-form="forgot"]').addEventListener("submit", (event) => {
      event.preventDefault();
      resetEmail = String(new FormData(event.currentTarget).get("email") || "");
      render();
    });
    return;
  }
  layout(`
    <section class="panel stack">
      <h1>Reset password</h1>
      <p>Local verification code: <strong>123456</strong></p>
      <div id="form-message"></div>
      <form class="stack" data-form="reset">
        <div class="form-row"><label for="verification-code">Verification code</label><input id="verification-code" name="code" type="text" /></div>
        <div class="form-row"><label for="new-password">New password</label><input id="new-password" name="password" type="password" /></div>
        <div class="form-row"><label for="confirm-new-password">Confirm new password</label><input id="confirm-new-password" name="confirm" type="password" /></div>
        <button class="btn" type="submit">Reset password</button>
      </form>
    </section>
  `, true);
  root.querySelector('[data-form="reset"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const message = root.querySelector("#form-message");
    if (data.code !== "123456") {
      message.innerHTML = '<div class="error">Invalid or incorrect verification code.</div>';
      return;
    }
    if (String(data.password || "").length < 10 || data.password !== data.confirm) {
      message.innerHTML = '<div class="error">Password is invalid or passwords do not match.</div>';
      return;
    }
    await command("account.password", { email: resetEmail, password: data.password });
    resetEmail = "";
    layout(`<section class="panel stack"><h1>Reset complete</h1><div class="success">Password has been updated.</div><p>${link("/login", "Sign in")}</p></section>`, true);
  });
}

function settingsView() {
  if (authRequired()) return;
  layout(`
    <div class="split">
      <nav class="side-nav">${link("/settings/password", "Password and authentication")}</nav>
      <section class="panel stack"><h1>Settings</h1><p>Manage account security and collaboration preferences.</p></section>
    </div>
  `);
}

function passwordSettingsView() {
  if (authRequired()) return;
  layout(`
    <div class="split">
      <nav class="side-nav">${link("/settings/password", "Password and authentication")}</nav>
      <section class="panel stack">
        <h1>Password and authentication</h1>
        <div id="form-message"></div>
        <form class="stack" data-form="change-password">
          <div class="form-row"><label for="current-password">Current password</label><input id="current-password" name="current" type="password" /></div>
          <div class="form-row"><label for="settings-new-password">New password</label><input id="settings-new-password" name="password" type="password" /></div>
          <div class="form-row"><label for="settings-confirm-password">Confirm password</label><input id="settings-confirm-password" name="confirm" type="password" /></div>
          <button class="btn" type="submit">Update password</button>
        </form>
      </section>
    </div>
  `);
  root.querySelector('[data-form="change-password"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const message = root.querySelector("#form-message");
    if (!data.current) {
      message.innerHTML = '<div class="error">Current password is required.</div>';
      localStorage.removeItem("langqi-forge-session");
      return;
    }
    if (data.password !== data.confirm) {
      message.innerHTML = '<div class="error">Passwords do not match and must be consistent.</div>';
      localStorage.removeItem("langqi-forge-session");
      return;
    }
    const result = await command("account.password", {
      username: currentUser(),
      currentPassword: data.current,
      password: data.password,
    });
    message.innerHTML = result.ok
      ? '<div class="success">Password has been updated.</div>'
      : '<div class="error">Current password is incorrect or invalid.</div>';
    localStorage.removeItem("langqi-forge-session");
  });
}

function logoutView() {
  if (!currentUser()) {
    navigate("/");
    return;
  }
  layout(`
    <section class="panel stack">
      <h1>Sign out</h1>
      <p>End the current authenticated session?</p>
      <button class="btn danger" type="button" data-action="confirm-sign-out">Confirm sign out</button>
    </section>
  `, true);
  root.querySelector('[data-action="confirm-sign-out"]').addEventListener("click", () => {
    localStorage.removeItem("langqi-forge-session");
    navigate("/");
  });
}

function organizationTabs(org) {
  return `<nav class="tabs" aria-label="Organization navigation">
    ${link(`/orgs/${org.name}`, "Overview")}
    ${link(`/orgs/${org.name}/repositories`, "Repositories")}
    ${link(`/orgs/${org.name}/teams`, "Teams")}
    ${link(`/orgs/${org.name}/people`, "People")}
    ${link(`/orgs/${org.name}/audit-log`, "Audit log")}
    ${link(`/orgs/${org.name}/settings/security`, "Security")}
  </nav>`;
}

function organizationsView() {
  if (authRequired()) return;
  const user = currentUser();
  const organizations = state.organizations.filter(
    (org) => org.owner === user || org.members.some((member) => member.username === user),
  );
  layout(`
    <section class="stack">
      <div class="toolbar"><h1>Your organizations</h1>${link("/organizations/new", "New organization", 'class="btn"')}</div>
      ${organizations
        .map((org) => `<article class="card"><h2>${link(`/orgs/${org.name}`, org.name)}</h2><p>${escapeHtml(org.displayName)}</p></article>`)
        .join("") || '<div class="panel">No organizations yet.</div>'}
    </section>
  `);
}

function newOrganizationView() {
  if (authRequired()) return;
  layout(`
    <section class="panel stack narrow">
      <h1>Create organization</h1>
      <div id="form-message"></div>
      <form class="stack" data-form="new-organization">
        <div class="form-row"><label for="organization-name">Organization name</label><input id="organization-name" name="name" type="text" /></div>
        <div class="form-row"><label for="organization-display">Display name</label><input id="organization-display" name="displayName" type="text" /></div>
        <button class="btn" type="submit">Create organization</button>
      </form>
    </section>
  `, true);
  root.querySelector('[data-form="new-organization"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const message = root.querySelector("#form-message");
    if (state.organizations.some((org) => org.name === data.name)) {
      message.innerHTML = '<div class="error">Organization name already exists and is unavailable.</div>';
      return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9-]{1,38}$/.test(data.name || "") || !String(data.displayName || "").trim()) {
      message.innerHTML = '<div class="error">Organization name format is invalid or display name is required.</div>';
      return;
    }
    const result = await command("create", {
      collection: "organizations",
      item: {
        id: data.name,
        name: data.name,
        displayName: data.displayName.trim(),
        owner: currentUser(),
        members: [{ username: currentUser(), role: "Owner" }],
      },
    });
    if (!result.ok) {
      message.innerHTML = '<div class="error">Organization name already exists and is unavailable.</div>';
      return;
    }
    navigate(`/orgs/${data.name}`);
  });
}

function organizationView(org) {
  const repos = state.repositories.filter(
    (repo) => repo.owner === org.name && (repo.visibility === "public" || currentUser()),
  );
  layout(`
    <section class="stack">
      <div><p class="muted">Organization</p><h1>${escapeHtml(org.name)}</h1><p>${escapeHtml(org.displayName)}</p></div>
      ${organizationTabs(org)}
      <div class="grid">
        ${repos.slice(0, 4).map((repo) => `<article class="card"><h2>${link(`/${repo.owner}/${repo.name}`, repo.name)}</h2><span class="badge">${escapeHtml(repo.visibility)}</span></article>`).join("")}
      </div>
    </section>
  `);
}

function organizationRepositoriesView(org) {
  const renderList = (query = "") => {
    const user = currentUser();
    const repos = state.repositories.filter(
      (repo) =>
        repo.owner === org.name &&
        repo.name.toLowerCase().includes(query.toLowerCase()) &&
        (repo.visibility === "public" || Boolean(user)),
    );
    root.querySelector("#organization-repositories").innerHTML = repos
      .map((repo) => `<article class="card"><h2>${link(`/${repo.owner}/${repo.name}`, repo.name)}</h2><span class="badge">${escapeHtml(repo.visibility)}</span></article>`)
      .join("") || '<div class="panel">No repositories found.</div>';
    bindCommon();
  };
  layout(`
    <section class="stack">
      <h1>${escapeHtml(org.name)}</h1>
      ${organizationTabs(org)}
      <div class="form-row"><label for="organization-repository-filter">Find a repository</label><input id="organization-repository-filter" type="text" aria-label="Find a repository" /></div>
      <div id="organization-repositories" class="stack"></div>
    </section>
  `);
  renderList();
  root.querySelector("#organization-repository-filter").addEventListener("input", (event) => renderList(event.target.value));
}

function organizationTeamsView(org) {
  const teams = state.teams.filter((team) => team.organization === org.name);
  layout(`
    <section class="stack">
      <h1>${escapeHtml(org.name)}</h1>
      ${organizationTabs(org)}
      <div class="toolbar"><h2>Teams</h2>${link(`/orgs/${org.name}/teams/new`, "New team", 'class="btn"')}</div>
      ${teams.map((team) => `<article class="card"><h3>${link(`/orgs/${org.name}/teams/${team.name}`, team.name)}</h3></article>`).join("")}
    </section>
  `);
}

function newTeamView(org) {
  if (authRequired()) return;
  layout(`
    <section class="panel stack narrow">
      <h1>New team</h1><div id="form-message"></div>
      <form class="stack" data-form="new-team">
        <div class="form-row"><label for="team-name">Team name</label><input id="team-name" name="name" type="text" /></div>
        <button class="btn" type="submit">Create team</button>
      </form>
    </section>
  `, true);
  root.querySelector('[data-form="new-team"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") || "");
    const message = root.querySelector("#form-message");
    if (!/^[A-Za-z0-9][A-Za-z0-9-]{1,38}$/.test(name)) {
      message.innerHTML = '<div class="error">Team name format is invalid.</div>';
      return;
    }
    const result = await command("create", {
      collection: "teams",
      item: { id: `${org.name}/${name}`, organization: org.name, name, parent: "", members: [], maintainers: [currentUser()] },
    });
    if (!result.ok) {
      message.innerHTML = '<div class="error">Team already exists.</div>';
      return;
    }
    navigate(`/orgs/${org.name}/teams/${name}`);
  });
}

function teamView(org, team, section = "overview") {
  const tabs = `<nav class="tabs">
    ${link(`/orgs/${org.name}/teams/${team.name}`, "Overview")}
    ${link(`/orgs/${org.name}/teams/${team.name}/members`, "Members")}
    ${link(`/orgs/${org.name}/teams/${team.name}/settings`, "Settings")}
  </nav>`;
  if (section === "members") {
    layout(`
      <section class="stack"><h1>${escapeHtml(team.name)}</h1>${tabs}
        <button class="btn" type="button" data-action="show-add-team-member">Add member</button>
        <div id="team-member-form"></div>
        <div id="team-members">${team.members.map((member) => `<div class="card"><span>${escapeHtml(member)}</span><button class="btn secondary" type="button" data-remove-team-member="${escapeHtml(member)}">Remove ${escapeHtml(member)}</button></div>`).join("")}</div>
      </section>
    `);
    root.querySelector('[data-action="show-add-team-member"]').addEventListener("click", (event) => {
      event.currentTarget.remove();
      root.querySelector("#team-member-form").innerHTML = `<form class="panel stack" data-form="add-team-member"><div class="form-row"><label for="team-member-name">Member username</label><input id="team-member-name" name="username" type="text" /></div><button class="btn" type="submit">Add member</button></form>`;
      root.querySelector('[data-form="add-team-member"]').addEventListener("submit", async (event) => {
        event.preventDefault();
        const username = String(new FormData(event.currentTarget).get("username") || "");
        await command("list.add", { collection: "teams", id: team.id, field: "members", value: username });
        render();
      });
    });
    root.querySelectorAll("[data-remove-team-member]").forEach((button) => button.addEventListener("click", async () => {
      await command("list.remove", { collection: "teams", id: team.id, field: "members", value: button.dataset.removeTeamMember });
      render();
    }));
    return;
  }
  if (section === "settings") {
    const options = state.teams.filter((entry) => entry.organization === org.name && entry.id !== team.id);
    layout(`
      <section class="stack"><h1>${escapeHtml(team.name)}</h1>${tabs}<div id="form-message"></div>
        <form class="panel stack" data-form="team-settings">
          <div class="form-row"><label for="parent-team">Parent team</label><select id="parent-team" name="parent">${["", ...options.map((entry) => entry.name)].map((name) => `<option value="${escapeHtml(name)}" ${team.parent === name ? "selected" : ""}>${escapeHtml(name || "No parent")}</option>`).join("")}</select></div>
          <button class="btn" type="submit">Save</button>
        </form>
      </section>
    `);
    root.querySelector('[data-form="team-settings"]').addEventListener("submit", async (event) => {
      event.preventDefault();
      const parent = String(new FormData(event.currentTarget).get("parent") || "");
      const descendant = state.teams.find((entry) => entry.organization === org.name && entry.parent === team.name && entry.name === parent);
      if (descendant) {
        root.querySelector("#form-message").innerHTML = '<div class="error">Cyclic team hierarchy is not allowed.</div>';
        event.currentTarget.querySelector("select").value = team.parent;
        return;
      }
      await command("patch", { collection: "teams", id: team.id, patch: { parent } });
      render();
    });
    return;
  }
  layout(`<section class="stack"><h1>${escapeHtml(team.name)}</h1>${tabs}<div class="panel"><p>Team in ${escapeHtml(org.name)}</p></div></section>`);
}

function organizationPeopleView(org) {
  const user = currentUser();
  const isOwner = org.owner === user;
  layout(`
    <section class="stack">
      <h1>${escapeHtml(org.name)}</h1>${organizationTabs(org)}
      <div id="people-message"></div>
      ${isOwner ? '<button class="btn" type="button" data-action="show-add-org-member">Add member</button>' : ""}
      <div id="organization-member-form"></div>
      <div class="stack">${org.members.map((member) => `<article class="card"><div class="toolbar"><span>${escapeHtml(member.username)}</span><span aria-label="Role: ${escapeHtml(member.role)}">${member.role === "Owner" ? "Owner" : "Direct access"}</span>${isOwner && member.username !== user ? `<button class="btn secondary" type="button" aria-label="${escapeHtml(member.username)} menu" data-member-menu="${escapeHtml(member.username)}">Actions</button>` : ""}</div><div data-member-actions="${escapeHtml(member.username)}"></div></article>`).join("")}</div>
    </section>
  `);
  root.querySelector('[data-action="show-add-org-member"]')?.addEventListener("click", () => {
    root.querySelector("#organization-member-form").innerHTML = `<form class="panel stack" data-form="add-org-member"><div class="form-row"><label for="organization-member">Username or email</label><input id="organization-member" name="login" type="text" /></div><div class="form-row"><span>Role</span><button id="organization-role" type="button" role="combobox" aria-label="Role" aria-expanded="false" data-action="organization-role">Member</button><input name="role" type="hidden" value="Member" /><div id="organization-role-options" role="listbox"></div></div><button class="btn" type="submit">Add member</button></form>`;
    root.querySelector('[data-action="organization-role"]').addEventListener("click", (event) => {
      event.currentTarget.setAttribute("aria-expanded", "true");
      root.querySelector("#organization-role-options").innerHTML = '<button type="button" role="option" class="option" data-organization-role="Member">Member</button><button type="button" role="option" class="option" data-organization-role="Owner">Owner</button>';
      root.querySelectorAll("[data-organization-role]").forEach((option) => option.addEventListener("click", () => {
        const value = option.dataset.organizationRole;
        root.querySelector('[name="role"]').value = value;
        root.querySelector('[data-action="organization-role"]').textContent = value;
        root.querySelector('[data-action="organization-role"]').setAttribute("aria-expanded", "false");
        root.querySelector("#organization-role-options").innerHTML = "";
      }));
    });
    root.querySelector('[data-form="add-org-member"]').addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.currentTarget));
      const account = state.accounts.find((item) => item.username === data.login || item.email === data.login);
      const message = root.querySelector("#people-message");
      if (!account) {
        message.innerHTML = '<div class="error">Account not found or unknown.</div>';
        return;
      }
      if (org.members.some((member) => member.username === account.username)) {
        message.innerHTML = '<div class="error">This account is already a member.</div>';
        return;
      }
      await command("list.add", { collection: "organizations", id: org.id, field: "members", value: { username: account.username, role: data.role }, uniqueKey: "username" });
      render();
    });
  });
  root.querySelectorAll("[data-member-menu]").forEach((button) => button.addEventListener("click", () => {
    root.querySelector(`[data-member-actions="${CSS.escape(button.dataset.memberMenu)}"]`).innerHTML = `<button type="button" role="menuitem" class="btn danger" data-remove-org-member="${escapeHtml(button.dataset.memberMenu)}">Remove from organization</button>`;
    root.querySelector(`[data-remove-org-member="${CSS.escape(button.dataset.memberMenu)}"]`).addEventListener("click", (event) => {
      event.currentTarget.outerHTML = `<button type="button" class="btn danger" data-confirm-remove-member="${escapeHtml(button.dataset.memberMenu)}">Remove</button>`;
      root.querySelector(`[data-confirm-remove-member="${CSS.escape(button.dataset.memberMenu)}"]`).addEventListener("click", async () => {
        await command("list.remove", { collection: "organizations", id: org.id, field: "members", key: "username", value: button.dataset.memberMenu });
        render();
      });
    });
  }));
}

function repoTabs(repo, codeHref = `/${repo.owner}/${repo.name}`) {
  return `<nav class="tabs" aria-label="Repository navigation">
    ${link(codeHref, "Code")}
    ${link(`/${repo.owner}/${repo.name}/commits`, "Commits")}
    ${link(`/${repo.owner}/${repo.name}/issues`, "Issues")}
    ${link(`/${repo.owner}/${repo.name}/pulls`, "Pull requests")}
    ${link(`/${repo.owner}/${repo.name}/actions`, "Actions")}
    ${link(`/${repo.owner}/${repo.name}/settings`, "Settings")}
  </nav>`;
}

function canViewRepository(repo) {
  if (repo.visibility === "public") return true;
  const user = currentUser();
  if (!user) return false;
  if (repo.owner === user) return true;
  const org = state.organizations.find((entry) => entry.name === repo.owner);
  if (org?.owner === user) return true;
  return repo.accesses.some((access) => access.subject === user);
}

function canAdminRepository(repo) {
  const user = currentUser();
  if (!user) return false;
  if (repo.owner === user) return true;
  const org = state.organizations.find((entry) => entry.name === repo.owner);
  if (org?.owner === user) return true;
  return repo.accesses.some((access) => access.subject === user && access.role === "admin");
}

function canWriteRepository(repo) {
  const user = currentUser();
  if (!user) return false;
  if (canAdminRepository(repo)) return true;
  return repo.accesses.some((access) => access.subject === user && ["write", "admin"].includes(access.role));
}

function branchStorageKey(repo) {
  return `langqi-branch:${repo.id}`;
}

function activeBranchName(repo) {
  const saved = localStorage.getItem(branchStorageKey(repo));
  if (saved && repo.branches.some((branch) => branch.name === saved)) return saved;
  return repo.defaultBranch;
}

function activeBranch(repo) {
  return repo.branches.find((branch) => branch.name === activeBranchName(repo)) || repo.branches[0];
}

function encodedPath(value) {
  return String(value).split("/").map(encodeURIComponent).join("/");
}

function directoryEntries(repo, branch, prefix = "") {
  const entries = new Map();
  const stem = prefix ? `${prefix}/` : "";
  for (const filePath of Object.keys(branch.files)) {
    if (!filePath.startsWith(stem)) continue;
    const remaining = filePath.slice(stem.length);
    if (!remaining) continue;
    const [name, ...rest] = remaining.split("/");
    entries.set(name, rest.length ? "directory" : "file");
  }
  return [...entries.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, type]) => {
      const target = prefix ? `${prefix}/${name}` : name;
      const route = type === "directory" ? "tree" : "blob";
      return `<p>${link(`/${repo.owner}/${repo.name}/${route}/${encodeURIComponent(branch.name)}/${encodedPath(target)}`, name)}</p>`;
    })
    .join("");
}

function newRepositoryView() {
  if (authRequired()) return;
  layout(`
    <section class="panel stack narrow">
      <h1>Create a new repository</h1><div id="form-message"></div>
      <form class="stack" data-form="new-repository">
        <div class="form-row"><label for="repository-name">Repository name</label><input id="repository-name" name="name" type="text" /></div>
        <div class="form-row"><label for="repository-description">Description</label><textarea id="repository-description" name="description"></textarea></div>
        <label class="checkbox-row"><input type="radio" name="visibility" value="public" checked /> Public</label>
        <label class="checkbox-row"><input type="radio" name="visibility" value="private" /> Private</label>
        <label class="checkbox-row"><input type="checkbox" name="readme" /> Add a README file</label>
        <button class="btn" type="submit">Create repository</button>
      </form>
    </section>
  `, true);
  root.querySelector('[data-form="new-repository"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const name = String(data.name || "").trim();
    const message = root.querySelector("#form-message");
    if (!name) {
      message.innerHTML = '<div class="error">Repository name is required.</div>';
      return;
    }
    if (state.repositories.some((repo) => repo.owner === currentUser() && repo.name === name)) {
      message.innerHTML = '<div class="error">Repository name already exists and is unavailable.</div>';
      return;
    }
    const files = data.readme ? { "README.md": `# ${name}\n` } : {};
    const item = {
      id: `${currentUser()}/${name}`,
      owner: currentUser(),
      name,
      visibility: data.visibility === "private" ? "private" : "public",
      description: String(data.description || ""),
      defaultBranch: "main",
      branches: [{ name: "main", files }],
      commits: data.readme ? [{ id: `initial-${Date.now()}`, message: "Initial commit", author: currentUser(), changedFiles: ["README.md"] }] : [],
      accesses: [], protections: [], forkedFrom: null,
    };
    await command("create", { collection: "repositories", item });
    navigate(`/${item.owner}/${item.name}`);
  });
}

function forkRepositoryView(source) {
  if (authRequired()) return;
  layout(`
    <section class="panel stack narrow">
      <h1>Fork ${escapeHtml(source.name)}</h1><div id="form-message"></div>
      <form class="stack" data-form="fork-repository">
        <div class="form-row"><label for="fork-name">Repository name</label><input id="fork-name" name="name" type="text" value="${escapeHtml(source.name)}" /></div>
        <button class="btn" type="submit">Create fork</button>
      </form>
    </section>
  `, true);
  root.querySelector('[data-form="fork-repository"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") || "").trim();
    const message = root.querySelector("#form-message");
    if (!name) {
      message.innerHTML = '<div class="error">Repository name is required.</div>';
      return;
    }
    if (state.repositories.some((repo) => repo.owner === currentUser() && repo.name === name)) {
      message.innerHTML = '<div class="error">Repository name already exists.</div>';
      return;
    }
    const item = {
      ...structuredClone(source),
      id: `${currentUser()}/${name}`,
      owner: currentUser(),
      name,
      visibility: "public",
      accesses: [],
      forkedFrom: `${source.owner}/${source.name}`,
    };
    await command("create", { collection: "repositories", item });
    navigate(`/${item.owner}/${item.name}`);
  });
}

function repositoryView(repo) {
  if (!canViewRepository(repo)) {
    layout('<section class="panel stack"><h1>Private repository</h1><p>Access denied.</p></section>', true);
    return;
  }
  const branch = activeBranch(repo);
  const relation = (state.repositoryRelations || []).find(
    (entry) => entry.repoId === repo.id && entry.username === currentUser(),
  ) || { starred: false, watching: "participating" };
  layout(`
    <section class="stack">
      <div><p class="muted">${escapeHtml(repo.owner)} /</p><h1>${escapeHtml(repo.name)}</h1><span class="badge">${escapeHtml(repo.visibility)}</span></div>
      ${repo.forkedFrom ? `<p>Forked from ${escapeHtml(repo.forkedFrom)}</p>` : ""}
      ${repoTabs(repo)}
      <div class="toolbar">
        <button class="btn secondary" type="button" aria-label="Branch: ${escapeHtml(branch.name)}" data-action="branch-menu">Branch: ${escapeHtml(branch.name)}</button>
        <div id="branch-menu"></div>
        <button class="btn secondary" type="button" data-action="code-menu">Code</button>
        ${currentUser() ? `<button class="btn secondary" type="button" data-action="fork-repository">Fork</button>` : ""}
        ${currentUser() ? `<button class="btn secondary" type="button" aria-pressed="${relation.starred}" data-action="star-repository">${relation.starred ? "Unstar" : "Star"}</button><label class="sr-only" for="watch-repository">Watch repository</label><select id="watch-repository" aria-label="Watch repository"><option value="participating" ${relation.watching === "participating" ? "selected" : ""}>Participating and @mentions</option><option value="all" ${relation.watching === "all" ? "selected" : ""}>All activity</option><option value="ignore" ${relation.watching === "ignore" ? "selected" : ""}>Ignore</option></select>` : ""}
        ${canWriteRepository(repo) ? '<button class="btn secondary" type="button" data-action="add-file">Add file</button><div id="add-file-menu"></div>' : ""}
        <div id="code-menu"></div>
      </div>
      <div class="panel"><h2>Files on ${escapeHtml(branch.name)}</h2>${directoryEntries(repo, branch) || "<p>No files yet.</p>"}</div>
    </section>
  `);
  root.querySelector('[data-action="branch-menu"]').addEventListener("click", () => {
    const menu = root.querySelector("#branch-menu");
    menu.innerHTML = '<div class="panel stack"><label for="find-branch">Find a branch</label><input id="find-branch" type="text" aria-label="Find a branch" /><div id="branch-options" role="listbox"></div></div>';
    const input = menu.querySelector("#find-branch");
    const renderOptions = () => {
      const query = input.value.trim();
      const matches = repo.branches.filter((entry) => entry.name.toLowerCase().includes(query.toLowerCase()));
      const invalid = query && (query.includes("..") || /[~^:?*\\[\\]\\s]/.test(query) || query.startsWith("/") || query.endsWith("/"));
      let content = matches.map((entry) => `<button class="option" type="button" role="option" data-select-branch="${escapeHtml(entry.name)}">${escapeHtml(entry.name)}</button>`).join("");
      if (invalid) content = '<div class="error">Invalid branch name.</div>';
      else if (query && !repo.branches.some((entry) => entry.name === query) && currentUser()) content += `<button class="option" type="button" role="option" data-create-branch="${escapeHtml(query)}">Create branch ${escapeHtml(query)}</button>`;
      else if (!matches.length) content = '<p>No matching branch.</p>';
      menu.querySelector("#branch-options").innerHTML = content;
      menu.querySelectorAll("[data-select-branch]").forEach((option) => option.addEventListener("click", () => {
        localStorage.setItem(branchStorageKey(repo), option.dataset.selectBranch);
        render();
      }));
      menu.querySelector("[data-create-branch]")?.addEventListener("click", async (event) => {
        const name = event.currentTarget.dataset.createBranch;
        await command("list.add", {
          collection: "repositories", id: repo.id, field: "branches",
          value: { name, files: structuredClone(branch.files) }, uniqueKey: "name",
        });
        localStorage.setItem(branchStorageKey(repo), name);
        render();
      });
    };
    input.addEventListener("input", renderOptions);
    menu.addEventListener("keydown", (event) => {
      if (event.key === "Escape") menu.innerHTML = "";
    });
    renderOptions();
    input.focus();
  });
  root.querySelector('[data-action="add-file"]')?.addEventListener("click", () => {
    root.querySelector("#add-file-menu").innerHTML = `<div role="menu" class="panel"><button class="btn secondary" type="button" role="menuitem" data-action="create-file">Create new file</button></div>`;
    root.querySelector('[data-action="create-file"]').addEventListener("click", () => navigate(`/${repo.owner}/${repo.name}/new/${encodeURIComponent(branch.name)}`));
  });
  root.querySelector('[data-action="fork-repository"]')?.addEventListener("click", () => navigate(`/${repo.owner}/${repo.name}/fork`));
  root.querySelector('[data-action="star-repository"]')?.addEventListener("click", async () => {
    await command("repository.star", { repoId: repo.id, starred: !relation.starred });
    render();
  });
  root.querySelector("#watch-repository")?.addEventListener("change", async (event) => {
    await command("repository.watch", { repoId: repo.id, watching: event.target.value });
    render();
  });
  root.querySelector('[data-action="code-menu"]').addEventListener("click", () => {
    let protocol = "https";
    const menu = root.querySelector("#code-menu");
    const renderCloneMenu = () => {
      const cloneUrl = protocol === "https"
        ? `https://example.test/${repo.owner}/${repo.name}.git`
        : `git@example.test:${repo.owner}/${repo.name}.git`;
      menu.innerHTML = `<div class="panel stack"><div role="tablist" aria-label="Clone protocol"><button type="button" role="tab" aria-selected="${protocol === "https"}" data-clone-protocol="https">HTTPS</button><button type="button" role="tab" aria-selected="${protocol === "ssh"}" data-clone-protocol="ssh">SSH</button></div><label for="clone-url">${protocol.toUpperCase()} clone URL</label><input id="clone-url" value="${escapeHtml(cloneUrl)}" readonly /><button class="btn secondary" type="button" aria-label="Copy clone URL" data-copy-clone>Copy clone URL</button><div id="copy-message"></div></div>`;
      menu.querySelectorAll("[data-clone-protocol]").forEach((tab) => tab.addEventListener("click", () => {
        protocol = tab.dataset.cloneProtocol;
        renderCloneMenu();
      }));
      menu.querySelector("[data-copy-clone]").addEventListener("click", async () => {
        await navigator.clipboard.writeText(cloneUrl);
        menu.querySelector("#copy-message").innerHTML = '<div class="success">Copied clone URL.</div>';
      });
    };
    renderCloneMenu();
  });
}

function repositoryDirectoryView(repo, branchName, directory) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const branch = repo.branches.find((entry) => entry.name === branchName);
  if (!branch) return notFoundView();
  layout(`<section class="stack"><h1>${escapeHtml(repo.name)}</h1>${repoTabs(repo)}<div class="panel stack"><h2>${escapeHtml(directory)}</h2>${directoryEntries(repo, branch, directory) || "<p>No files found.</p>"}</div></section>`);
}

function repositoryFileView(repo, branchName, filePath) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const branch = repo.branches.find((entry) => entry.name === branchName);
  const content = branch?.files?.[filePath];
  if (content === undefined) return notFoundView();
  const query = new URLSearchParams(location.search).get("q") || "";
  const currentPath = `/${repo.owner}/${repo.name}/blob/${encodeURIComponent(branchName)}/${encodedPath(filePath)}${query ? `?q=${encodeURIComponent(query)}` : ""}`;
  layout(`<section class="stack"><h1>${escapeHtml(repo.name)}</h1>${repoTabs(repo)}<div class="panel stack"><h2>${link(currentPath, filePath)}</h2>${query ? `<p class="search-hit">${escapeHtml(query)}</p>` : ""}<pre>${escapeHtml(content)}</pre></div></section>`);
}

function repositoryCommitsView(repo) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  layout(`<section class="stack"><h1>Commits for ${escapeHtml(repo.name)}</h1>${repoTabs(repo)}${repo.commits.map((commit) => `<article class="card stack"><h2>${link(`/${repo.owner}/${repo.name}/commit/${encodeURIComponent(commit.id)}`, commit.message)}</h2><p>${escapeHtml(commit.author)}</p><p class="muted">2 hours ago</p></article>`).join("") || '<div class="panel">No commits.</div>'}</section>`);
}

function repositoryCommitView(repo, commitId) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const commit = repo.commits.find((entry) => entry.id === commitId);
  if (!commit) return notFoundView();
  layout(`<section class="stack"><h1>${escapeHtml(commit.message)}</h1>${repoTabs(repo)}<div class="panel stack"><p>1 changed file</p>${commit.changedFiles.map((file) => `<p>${escapeHtml(file)}</p>`).join("")}<p>1 addition, 0 deletions</p></div></section>`);
}

function repositorySearchView(repo) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const query = new URLSearchParams(location.search).get("q") || "";
  const branch = activeBranch(repo);
  const matches = Object.entries(branch.files).filter(([, content]) => String(content).toLowerCase().includes(query.toLowerCase()));
  const codeHref = `/${repo.owner}/${repo.name}/search?q=${encodeURIComponent(query)}`;
  layout(`<section class="stack"><h1>Code search</h1>${repoTabs(repo, codeHref)}<p>Repository: ${escapeHtml(repo.owner)}/${escapeHtml(repo.name)}</p>${matches.length ? matches.map(([file]) => `<article class="card">${link(`/${repo.owner}/${repo.name}/blob/${encodeURIComponent(branch.name)}/${encodedPath(file)}?q=${encodeURIComponent(query)}`, file)}</article>`).join("") : '<div class="panel">No code results. No results.</div>'}</section>`);
}

function newFileView(repo, branchName) {
  if (authRequired()) return;
  if (!canWriteRepository(repo)) return repositoryView(repo);
  const branch = repo.branches.find((entry) => entry.name === branchName);
  if (!branch) return notFoundView();
  layout(`<section class="panel stack"><h1>Create new file</h1><div id="file-message"></div><form class="stack" data-form="new-file"><div class="form-row"><label for="file-name">File name</label><input id="file-name" name="name" type="text" /></div><div class="form-row"><label for="file-contents">File contents</label><textarea id="file-contents" name="contents" aria-label="File contents"></textarea></div><div class="form-row"><label for="commit-message">Commit message</label><input id="commit-message" name="message" type="text" /></div><button class="btn" type="submit">Commit changes</button></form></section>`);
  root.querySelector('[data-form="new-file"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const name = String(data.name || "");
    const message = String(data.message || "").trim();
    if (!name || name.includes("..") || name.startsWith("/") || !message) {
      root.querySelector("#file-message").innerHTML = '<div class="error">Invalid file path or commit message is required.</div>';
      return;
    }
    const branches = structuredClone(repo.branches);
    const target = branches.find((entry) => entry.name === branchName);
    target.files[name] = String(data.contents || "");
    const commits = [{ id: `commit-${Date.now()}`, message, author: currentUser(), changedFiles: [name] }, ...repo.commits];
    await command("patch", { collection: "repositories", id: repo.id, patch: { branches, commits } });
    navigate(`/${repo.owner}/${repo.name}/blob/${encodeURIComponent(branchName)}/${encodedPath(name)}`);
  });
}

function repositoryIssuesView(repo) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const parameters = new URLSearchParams(location.search);
  const selectedState = parameters.get("state") || "open";
  const initialQuery = parameters.get("q") || "";
  layout(`<section class="stack"><h1>Issues</h1>${repoTabs(repo)}<div class="toolbar">${link(`/${repo.owner}/${repo.name}/issues?state=open`, "Open")} ${link(`/${repo.owner}/${repo.name}/issues?state=closed`, "Closed")} ${currentUser() ? link(`/${repo.owner}/${repo.name}/issues/new`, "New issue", 'class="btn"') : ""} ${canAdminRepository(repo) ? link(`/${repo.owner}/${repo.name}/issues/templates`, "Issue forms", 'class="btn secondary"') : ""}</div><div class="form-row"><label for="issue-search">Search or filter issues</label><input id="issue-search" type="search" aria-label="Search or filter issues" value="${escapeHtml(initialQuery)}" /></div><div id="issue-list" class="stack"></div></section>`);
  const renderList = (query) => {
    const issues = state.issues.filter((issue) => issue.repoId === repo.id && issue.state === selectedState && issue.title.toLowerCase().includes(query.toLowerCase()));
    root.querySelector("#issue-list").innerHTML = issues.map((issue) => `<article class="card"><h2>${link(`/${repo.owner}/${repo.name}/issues/${issue.number}`, issue.title)}</h2></article>`).join("") || '<div class="panel">No issues found.</div>';
    bindCommon();
  };
  renderList(initialQuery);
  root.querySelector("#issue-search").addEventListener("input", (event) => {
    const query = event.target.value;
    const next = new URLSearchParams(location.search);
    next.set("state", selectedState);
    if (query) next.set("q", query); else next.delete("q");
    history.replaceState({}, "", `${location.pathname}?${next.toString()}`);
    renderList(query);
  });
}

function newIssueView(repo) {
  if (authRequired()) return;
  layout(`<section class="panel stack"><h1>New issue</h1><div id="issue-message"></div><form class="stack" data-form="new-issue"><div class="form-row"><label for="issue-title">Title</label><input id="issue-title" name="title" type="text" /></div><div class="form-row"><label for="issue-description">Description</label><textarea id="issue-description" name="description"></textarea></div><button class="btn" type="submit">Submit new issue</button></form></section>`);
  root.querySelector('[data-form="new-issue"]').addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const title = String(data.title || "").trim();
    if (!title) {
      root.querySelector("#issue-message").innerHTML = '<div class="error">Title is required.</div>';
      return;
    }
    const numbers = state.issues.filter((issue) => issue.repoId === repo.id).map((issue) => issue.number);
    const number = Math.max(0, ...numbers) + 1;
    const item = {
      id: `${repo.id}#${number}`, repoId: repo.id, number, title,
      description: String(data.description || ""), state: "open", author: currentUser(),
      editable: true, assignees: [], labels: [], milestone: "", comments: [],
    };
    await command("create", { collection: "issues", item });
    navigate(`/${repo.owner}/${repo.name}/issues/${number}`);
  });
}

function issueView(repo, issue) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const manager = canWriteRepository(repo);
  const status = issue.state === "closed" ? "Closed issue" : "Open issue";
  layout(`<section class="stack"><h1>${escapeHtml(issue.title)}</h1>${repoTabs(repo)}<div id="issue-message"></div><section class="panel stack"><span class="badge">${status}</span><div id="title-editor"></div><p id="issue-description">${escapeHtml(issue.description)}</p><div id="description-editor"></div>${manager ? '<div class="toolbar"><button class="btn secondary" type="button" data-action="edit-title">Edit title</button><button class="btn secondary" type="button" data-action="edit-description">Edit description</button></div>' : ""}</section><aside class="panel stack"><div><button class="btn secondary" type="button" data-action="assignees">Assignees</button><div id="assignee-menu"></div><div class="toolbar">${issue.assignees.map((name) => `<span class="badge" data-assignee-display="${escapeHtml(name)}">${escapeHtml(name)}</span>`).join("")}</div></div><div><button class="btn secondary" type="button" data-action="labels">Labels</button><div id="label-menu"></div><div class="toolbar">${issue.labels.map((name) => `<span class="badge">${escapeHtml(name)}</span>`).join("")}</div></div><div><button class="btn secondary" type="button" data-action="milestone">Milestone</button><div id="milestone-menu"></div>${issue.milestone ? `<p>${escapeHtml(issue.milestone)}</p>` : ""}</div></aside><section class="stack"><h2>Activity</h2>${issue.comments.map((comment) => `<article class="card"><p>Comment by ${escapeHtml(comment.author)}</p><p>${escapeHtml(comment.body)}</p></article>`).join("")}${currentUser() ? '<form class="panel stack" data-form="issue-comment"><div id="comment-message"></div><div class="form-row"><label for="new-comment">Comment</label><textarea id="new-comment" name="comment"></textarea></div><button class="btn" type="submit">Comment</button></form>' : ""}</section>${manager ? `<button class="btn ${issue.state === "closed" ? "secondary" : "danger"}" type="button" data-action="toggle-issue">${issue.state === "closed" ? "Reopen issue" : "Close issue"}</button>` : ""}</section>`);

  root.querySelector('[data-action="edit-title"]')?.addEventListener("click", () => {
    root.querySelector("#title-editor").innerHTML = `<form class="stack" data-form="edit-title"><div class="form-row"><label for="edit-title">Title</label><input id="edit-title" name="title" value="${escapeHtml(issue.title)}" /></div><button class="btn" type="submit">Save</button></form>`;
    root.querySelector('[data-form="edit-title"]').addEventListener("submit", async (event) => {
      event.preventDefault();
      const title = String(new FormData(event.currentTarget).get("title") || "").trim();
      if (!title) {
        root.querySelector("#issue-message").innerHTML = '<div class="error">Title is required and cannot be empty.</div>';
        return;
      }
      issue.title = title;
      root.querySelector("h1").textContent = title;
      root.querySelector("#title-editor").innerHTML = "";
      await command("patch", { collection: "issues", id: issue.id, patch: { title } });
    });
  });
  root.querySelector('[data-action="edit-description"]')?.addEventListener("click", () => {
    root.querySelector('[data-form="issue-comment"]')?.remove();
    root.querySelector("#description-editor").innerHTML = `<form class="stack" data-form="edit-description"><div class="form-row"><label for="edit-description">Description</label><textarea id="edit-description" name="description">${escapeHtml(issue.description)}</textarea></div><button class="btn" type="submit">Save</button></form>`;
    root.querySelector('[data-form="edit-description"]').addEventListener("submit", async (event) => {
      event.preventDefault();
      const description = String(new FormData(event.currentTarget).get("description") || "");
      issue.description = description;
      root.querySelector("#issue-description").textContent = description;
      root.querySelector("#description-editor").innerHTML = "";
      await command("patch", { collection: "issues", id: issue.id, patch: { description } });
    });
  });
  root.querySelector('[data-form="issue-comment"]')?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = String(new FormData(event.currentTarget).get("comment") || "").trim();
    if (!body) {
      root.querySelector("#comment-message").innerHTML = '<div class="error">Comment is required and cannot be empty.</div>';
      return;
    }
    await command("list.add", { collection: "issues", id: issue.id, field: "comments", value: { id: crypto.randomUUID(), author: currentUser(), body } });
    render();
  });
  root.querySelector('[data-action="assignees"]').addEventListener("click", () => {
    const candidates = state.accounts.map((account) => account.username);
    const menu = root.querySelector("#assignee-menu");
    menu.innerHTML = '<div class="panel stack"><label for="assignee-search">Search assignees</label><input id="assignee-search" type="text" aria-label="Search assignees" /><div id="assignee-options" role="listbox"></div></div>';
    const input = menu.querySelector("#assignee-search");
    const show = () => {
      const query = input.value.toLowerCase();
      menu.querySelector("#assignee-options").innerHTML = candidates.filter((name) => name.toLowerCase().includes(query)).map((name) => `<button class="option" type="button" role="option" data-assignee="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("");
      menu.querySelectorAll("[data-assignee]").forEach((option) => option.addEventListener("click", async () => {
        const value = option.dataset.assignee;
        const assigned = issue.assignees.includes(value);
        menu.innerHTML = "";
        if (assigned) root.querySelector(`[data-assignee-display="${CSS.escape(value)}"]`)?.remove();
        if (assigned) await command("list.remove", { collection: "issues", id: issue.id, field: "assignees", value });
        else await command("list.add", { collection: "issues", id: issue.id, field: "assignees", value });
        render();
      }));
    };
    input.addEventListener("input", show);
    show();
  });
  root.querySelector('[data-action="labels"]').addEventListener("click", () => {
    root.querySelector("#label-menu").innerHTML = `<div role="listbox" class="panel">${repo.labels.map((name) => `<button class="option" type="button" role="option" data-issue-label="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("")}</div>`;
    root.querySelectorAll("[data-issue-label]").forEach((option) => option.addEventListener("click", async () => {
      await command("list.add", { collection: "issues", id: issue.id, field: "labels", value: option.dataset.issueLabel });
      render();
    }));
  });
  root.querySelector('[data-action="milestone"]').addEventListener("click", () => {
    root.querySelector("#milestone-menu").innerHTML = `<div role="listbox" class="panel">${repo.milestones.map((name) => `<button class="option" type="button" role="option" data-issue-milestone="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("")}</div>`;
    root.querySelectorAll("[data-issue-milestone]").forEach((option) => option.addEventListener("click", async () => {
      await command("patch", { collection: "issues", id: issue.id, patch: { milestone: option.dataset.issueMilestone } });
      render();
    }));
  });
  root.querySelector('[data-action="toggle-issue"]')?.addEventListener("click", async () => {
    await command("patch", { collection: "issues", id: issue.id, patch: { state: issue.state === "closed" ? "open" : "closed" } });
    render();
  });
}

function repositoryPullsView(repo) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const selectedState = new URLSearchParams(location.search).get("state") || "open";
  const pulls = state.pullRequests.filter((pull) => pull.repoId === repo.id && pull.state === selectedState);
  layout(`<section class="stack"><h1>Pull requests</h1>${repoTabs(repo)}<div class="toolbar">${link(`/${repo.owner}/${repo.name}/pulls?state=open`, "Open")} ${link(`/${repo.owner}/${repo.name}/pulls?state=closed`, "Closed")} ${currentUser() ? link(`/${repo.owner}/${repo.name}/pulls/new`, "New pull request", 'class="btn"') : ""}</div>${pulls.map((pull) => `<article class="card"><h2>${link(`/${repo.owner}/${repo.name}/pull/${pull.number}`, pull.title)}</h2></article>`).join("") || '<div class="panel">No pull requests found.</div>'}</section>`);
}

function newPullRequestView(repo) {
  if (authRequired()) return;
  const branchOptions = repo.branches.map((branch) => `<option value="${escapeHtml(branch.name)}">${escapeHtml(branch.name)}</option>`).join("");
  layout(`<section class="panel stack"><h1>Compare branches</h1><form class="stack" data-form="compare-branches"><div class="form-row"><label for="base-branch">Base</label><select id="base-branch" name="base">${branchOptions}</select></div><div class="form-row"><label for="compare-branch">Compare</label><select id="compare-branch" name="compare">${branchOptions}</select></div><div id="compare-message"></div><button class="btn" type="submit">Compare changes</button></form></section>`);
  const form = root.querySelector('[data-form="compare-branches"]');
  const validate = () => {
    const data = Object.fromEntries(new FormData(form));
    root.querySelector("#compare-message").innerHTML = data.base === data.compare ? '<div class="error">Identical branches have no changes.</div>' : "";
  };
  form.querySelectorAll("select").forEach((select) => select.addEventListener("change", validate));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    if (data.base === data.compare) return validate();
    navigate(`/${repo.owner}/${repo.name}/compare/${encodeURIComponent(data.base)}...${encodeURIComponent(data.compare)}`);
  });
  if (repo.branches.length > 1) form.querySelector('[name="compare"]').selectedIndex = 1;
  validate();
}

function compareBranchesView(repo, baseName, compareName) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const base = repo.branches.find((branch) => branch.name === baseName);
  const compare = repo.branches.find((branch) => branch.name === compareName);
  if (!base || !compare) return notFoundView();
  const changedFiles = [...new Set([...Object.keys(base.files), ...Object.keys(compare.files)])].filter((file) => base.files[file] !== compare.files[file]);
  layout(`<section class="stack"><h1>Compare ${escapeHtml(baseName)} and ${escapeHtml(compareName)}</h1>${repoTabs(repo)}<div class="panel stack">${changedFiles.map((file) => `<p>${escapeHtml(file)}</p>`).join("") || "<p>No changed files.</p>"}<div id="pull-actions" class="toolbar"><button class="btn" type="button" data-create-pull="open">Create pull request</button><button class="btn secondary" type="button" data-create-pull="draft">Create draft pull request</button></div><div id="pull-form"></div></div></section>`);
  root.querySelectorAll("[data-create-pull]").forEach((button) => button.addEventListener("click", () => {
    const draft = button.dataset.createPull === "draft";
    root.querySelector("#pull-actions").remove();
    root.querySelector("#pull-form").innerHTML = `<form class="stack" data-form="create-pull"><div id="pull-message"></div><div class="form-row"><label for="pull-title">Title</label><input id="pull-title" name="title" type="text" /></div><button class="btn" type="submit">${draft ? "Create draft pull request" : "Create pull request"}</button></form>`;
    root.querySelector('[data-form="create-pull"]').addEventListener("submit", async (event) => {
      event.preventDefault();
      const title = String(new FormData(event.currentTarget).get("title") || "").trim();
      if (!title) {
        root.querySelector("#pull-message").innerHTML = '<div class="error">Title is required.</div>';
        return;
      }
      const submit = event.currentTarget.querySelector('button[type="submit"]');
      submit.textContent = "Creating pull request…";
      submit.disabled = true;
      const item = {
        repoId: repo.id, title, description: "",
        state: "open", draft, base: baseName, head: compareName, author: currentUser(), mergeable: true,
        files: changedFiles, commits: ["Implement compared changes"], reviewers: [], reviewComments: [], reviews: [],
        checks: { test: "pending" }, checkUpdatedBy: "", readyEvent: false,
      };
      const result = await command("pullRequest.create", { item });
      navigate(`/${repo.owner}/${repo.name}/pull/${result.item.number}`);
    });
  }));
}

function pullRequestTabs(repo, pull) {
  return `<nav class="tabs" aria-label="Pull request navigation">${link(`/${repo.owner}/${repo.name}/pull/${pull.number}`, "Overview")} ${link(`/${repo.owner}/${repo.name}/pull/${pull.number}/commits`, "Commits")} ${link(`/${repo.owner}/${repo.name}/pull/${pull.number}/files`, "Files changed")}</nav>`;
}

function pullRequestStatus(pull) {
  if (pull.state === "merged") return "Merged pull request";
  if (pull.state === "closed") return "Closed pull request";
  if (pull.draft) return "Draft pull request";
  return "Open pull request";
}

function pullRequestView(repo, pull) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const user = currentUser();
  const canClose = Boolean(user && (user === pull.author || canAdminRepository(repo)));
  const mergeDisabled = pull.draft || !pull.mergeable || pull.state !== "open";
  const reviewSummary = pull.reviews.map((review) => `<div class="card"><p>${review.status === "approved" ? "Approved" : "Changes requested"}</p>${review.summary ? `<p>${escapeHtml(review.summary)}</p>` : ""}</div>`).join("");
  layout(`<section class="stack"><h1 aria-label="${escapeHtml(pull.title)}">${headingText(pull.title)}</h1>${pullRequestTabs(repo, pull)}<p><span>${escapeHtml(pull.head)}</span> into <span>${escapeHtml(pull.base)}</span></p><p class="badge">${pullRequestStatus(pull)}</p>${pull.readyEvent ? '<p>Marked ready for review</p>' : ""}${reviewSummary}<aside class="panel stack"><button class="btn secondary" type="button" aria-label="Reviewers" data-action="reviewers">People requested</button><div id="reviewer-menu"></div><div id="reviewer-list">${pull.reviewers.map((reviewer) => `<div class="toolbar" data-reviewer-row="${escapeHtml(reviewer)}"><span data-reviewer-display="${escapeHtml(reviewer)}">${escapeHtml(reviewer)}</span><button class="btn secondary" type="button" data-remove-reviewer="${escapeHtml(reviewer)}">Remove ${escapeHtml(reviewer)}</button></div>`).join("")}</div></aside>${repo.id === "acme/protection-repo" ? `<section class="panel stack"><p>test ${escapeHtml(pull.checks?.test || "pending")}</p>${pull.checkUpdatedBy ? `<p>Updated by ${escapeHtml(pull.checkUpdatedBy)}</p>` : ""}${canAdminRepository(repo) ? '<button type="button" role="combobox" aria-label="Test status" aria-expanded="false" data-action="test-status">Test status</button><div id="test-status-options" role="listbox"></div><button class="btn" type="button" data-action="save-test-status">Save status</button>' : ""}</section>` : ""}${pull.draft && user === pull.author ? '<button class="btn" type="button" data-action="ready-review">Ready for review</button>' : ""}${user ? `<section class="stack"><button class="btn" type="button" data-action="merge-pull" ${mergeDisabled ? "disabled" : ""}>Merge pull request</button>${!pull.mergeable ? '<p>Review required by protection rule.</p>' : ""}<div id="merge-confirm"></div></section>` : ""}${canClose && ["open", "closed"].includes(pull.state) ? `<button class="btn ${pull.state === "open" ? "danger" : "secondary"}" type="button" data-action="toggle-pull">${pull.state === "open" ? "Close pull request" : "Reopen pull request"}</button>` : ""}</section>`);

  let selectedCheck = pull.checks?.test || "pending";
  root.querySelector('[data-action="test-status"]')?.addEventListener("click", (event) => {
    event.currentTarget.setAttribute("aria-expanded", "true");
    root.querySelector("#test-status-options").innerHTML = '<button class="option" type="button" role="option" data-test-status="success">Success</button><button class="option" type="button" role="option" data-test-status="pending">Pending</button>';
    root.querySelectorAll("[data-test-status]").forEach((option) => option.addEventListener("click", () => {
      selectedCheck = option.dataset.testStatus;
      root.querySelector("#test-status-options").innerHTML = "";
      root.querySelector('[data-action="test-status"]').textContent = `Test status: ${selectedCheck}`;
    }));
  });
  root.querySelector('[data-action="save-test-status"]')?.addEventListener("click", async () => {
    await command("patch", { collection: "pullRequests", id: pull.id, patch: { checks: { ...pull.checks, test: selectedCheck }, checkUpdatedBy: currentUser() } });
    render();
  });
  root.querySelector('[data-action="ready-review"]')?.addEventListener("click", async () => {
    await command("patch", { collection: "pullRequests", id: pull.id, patch: { draft: false, readyEvent: true } });
    render();
  });
  root.querySelector('[data-action="reviewers"]').addEventListener("click", () => {
    const menu = root.querySelector("#reviewer-menu");
    const candidates = state.accounts.map((account) => account.username);
    menu.innerHTML = '<div class="panel stack"><label for="reviewer-search">Search reviewers</label><input id="reviewer-search" type="text" aria-label="Search reviewers" /><div id="reviewer-options" role="listbox"></div></div>';
    const input = menu.querySelector("#reviewer-search");
    const show = () => {
      const query = input.value.toLowerCase();
      menu.querySelector("#reviewer-options").innerHTML = candidates.filter((name) => name.toLowerCase().includes(query)).map((name) => `<button class="option" type="button" role="option" data-reviewer="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("");
      menu.querySelectorAll("[data-reviewer]").forEach((option) => option.addEventListener("click", async () => {
        menu.innerHTML = "";
        await command("list.add", { collection: "pullRequests", id: pull.id, field: "reviewers", value: option.dataset.reviewer });
        render();
      }));
    };
    input.addEventListener("input", show);
    show();
  });
  root.querySelectorAll("[data-remove-reviewer]").forEach((button) => button.addEventListener("click", async () => {
    const reviewer = button.dataset.removeReviewer;
    root.querySelector(`[data-reviewer-row="${CSS.escape(reviewer)}"]`)?.remove();
    await command("list.remove", { collection: "pullRequests", id: pull.id, field: "reviewers", value: reviewer });
    render();
  }));
  root.querySelector('[data-action="merge-pull"]')?.addEventListener("click", () => {
    root.querySelector("#merge-confirm").innerHTML = '<button class="btn danger" type="button" data-action="confirm-merge">Confirm merge</button>';
    root.querySelector('[data-action="confirm-merge"]').addEventListener("click", async () => {
      const result = await command("pullRequest.merge", { id: pull.id });
      if (!result.ok) {
        const reasons = result.details?.reasons?.join(", ") || result.message || "Merge policy denied this operation.";
        root.querySelector("#merge-confirm").innerHTML = `<div class="error">Merge blocked: ${escapeHtml(reasons)}</div>`;
        return;
      }
      render();
    });
  });
  root.querySelector('[data-action="toggle-pull"]')?.addEventListener("click", async () => {
    await command("patch", { collection: "pullRequests", id: pull.id, patch: { state: pull.state === "open" ? "closed" : "open" } });
    render();
  });
}

function pullRequestCommitsView(repo, pull) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  layout(`<section class="stack"><h1 aria-label="${escapeHtml(pull.title)}">${headingText(pull.title)}</h1>${pullRequestTabs(repo, pull)}<section class="panel stack"><h2>History</h2>${pull.commits.map((message) => `<p>${escapeHtml(message)}</p>`).join("")}</section></section>`);
}

function pullRequestFilesView(repo, pull) {
  if (!canViewRepository(repo)) return repositoryView(repo);
  const reviewItems = pull.reviews.map((review) => `<article class="card"><p>${review.status === "approved" ? "Approved" : "Changes requested"}</p>${review.summary ? `<p>${escapeHtml(review.summary)}</p>` : ""}</article>`).join("");
  const comments = pull.reviewComments.map((comment) => `<article class="card"><p>${escapeHtml(comment.body)}</p></article>`).join("");
  layout(`<section class="stack"><h1 aria-label="${escapeHtml(pull.title)}">${headingText(pull.title)}</h1>${pullRequestTabs(repo, pull)}<section class="panel stack"><h2>Changed files</h2>${pull.files.map((file) => `<p>${escapeHtml(file)}</p>`).join("")}<p>+1 -0</p>${comments}${reviewItems}${currentUser() ? '<div class="toolbar"><button class="btn secondary" type="button" data-action="add-review-comment">Add comment</button><button class="btn" type="button" data-action="review-changes">Review changes</button></div><div id="review-editor"></div>' : ""}</section></section>`);
  root.querySelector('[data-action="add-review-comment"]')?.addEventListener("click", () => {
    root.querySelector("#review-editor").innerHTML = '<form class="stack" data-form="line-comment"><div class="form-row"><label for="line-comment">Comment</label><textarea id="line-comment" name="comment"></textarea></div><div class="toolbar"><button class="btn secondary" type="button" data-action="single-comment">Add single comment</button><button class="btn" type="button" data-action="start-review">Start a review</button></div></form>';
    const saveComment = async (pending) => {
      const body = String(new FormData(root.querySelector('[data-form="line-comment"]')).get("comment") || "").trim();
      if (!body) return;
      await command("list.add", { collection: "pullRequests", id: pull.id, field: "reviewComments", value: { id: crypto.randomUUID(), author: currentUser(), body, pending } });
      render();
    };
    root.querySelector('[data-action="single-comment"]').addEventListener("click", () => saveComment(false));
    root.querySelector('[data-action="start-review"]').addEventListener("click", () => saveComment(true));
  });
  root.querySelector('[data-action="review-changes"]')?.addEventListener("click", () => {
    root.querySelector("#review-editor").innerHTML = '<form class="stack" data-form="submit-review"><div class="form-row"><label for="review-summary">Review summary</label><textarea id="review-summary" name="summary"></textarea></div><label class="checkbox-row"><input type="radio" name="decision" value="approved" /> Approve</label><label class="checkbox-row"><input type="radio" name="decision" value="changes_requested" /> Request changes</label><button class="btn" type="submit">Submit review</button></form>';
    root.querySelector('[data-form="submit-review"]').addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.currentTarget));
      const status = data.decision || "approved";
      await command("list.add", { collection: "pullRequests", id: pull.id, field: "reviews", value: { id: crypto.randomUUID(), author: currentUser(), status, summary: String(data.summary || "") } });
      render();
    });
  });
}

function repositorySettingsView(repo, section = "general") {
  if (authRequired()) return;
  if (!canViewRepository(repo)) return repositoryView(repo);
  const nav = `<nav class="side-nav">${link(`/${repo.owner}/${repo.name}/settings`, "General")} ${link(`/${repo.owner}/${repo.name}/settings/access`, "Manage access")} ${link(`/${repo.owner}/${repo.name}/settings/branches`, "Branches")} ${link(`/${repo.owner}/${repo.name}/settings/rules`, "Rulesets")} ${link(`/${repo.owner}/${repo.name}/settings/environments`, "Environments")} ${link(`/${repo.owner}/${repo.name}/settings/repository-lifecycle`, "Danger zone")}</nav>`;
  if (section === "branches") {
    if (!canAdminRepository(repo)) {
      layout(`<div class="split">${nav}<section class="panel"><h1>Branches</h1><p>Administrator permission is required.</p></section></div>`);
      return;
    }
    layout(`<div class="split">${nav}<section class="panel stack"><h1>Branches</h1><form class="stack" data-form="default-branch"><div class="form-row"><label for="default-branch">Default branch</label><select id="default-branch" name="branch">${repo.branches.map((branch) => `<option value="${escapeHtml(branch.name)}" label="${escapeHtml(branch.name)}" ${branch.name === repo.defaultBranch ? "selected" : ""}></option>`).join("")}</select></div><button class="btn" type="submit">Update default branch</button></form><div id="default-confirm"></div><hr /><section class="stack"><h2>Branch protection rules</h2>${repo.protections.map((rule) => `<article class="card"><p>${escapeHtml(rule.pattern)}</p><p>1 approval</p><p>Status check test</p></article>`).join("")}<button class="btn" type="button" data-action="add-protection">Add branch protection rule</button><div id="protection-form"></div></section></section></div>`);
    root.querySelector('[data-form="default-branch"]').addEventListener("submit", (event) => {
      event.preventDefault();
      const branch = String(new FormData(event.currentTarget).get("branch") || "");
      root.querySelector("#default-confirm").innerHTML = `<button class="btn danger" type="button" data-confirm-default="${escapeHtml(branch)}">Confirm</button>`;
      root.querySelector("[data-confirm-default]").addEventListener("click", async (confirmEvent) => {
        const defaultBranch = confirmEvent.currentTarget.dataset.confirmDefault;
        await command("patch", { collection: "repositories", id: repo.id, patch: { defaultBranch } });
        localStorage.removeItem(branchStorageKey(repo));
        render();
      });
    });
    root.querySelector('[data-action="add-protection"]').addEventListener("click", (event) => {
      event.currentTarget.remove();
      root.querySelector("#protection-form").innerHTML = `<form class="panel stack" data-form="protection"><div class="form-row"><label for="branch-pattern">Branch name pattern</label><input id="branch-pattern" name="pattern" type="text" /></div><label class="checkbox-row"><input name="approval" type="checkbox" /> Require 1 approval review</label><label class="checkbox-row"><input name="status" type="checkbox" /> Require status check test</label><button class="btn" type="submit">Create rule</button></form>`;
      root.querySelector('[data-form="protection"]').addEventListener("submit", async (formEvent) => {
        formEvent.preventDefault();
        const data = Object.fromEntries(new FormData(formEvent.currentTarget));
        const pattern = String(data.pattern || "").trim();
        if (!pattern) return;
        await command("list.add", { collection: "repositories", id: repo.id, field: "protections", value: { pattern, approvals: data.approval ? 1 : 0, statusCheck: data.status ? "test" : "" }, uniqueKey: "pattern" });
        render();
      });
    });
    return;
  }
  if (section === "access") {
    layout(`
      <div class="split">${nav}<section class="stack"><h1>Manage access</h1><button class="btn" type="button" data-action="show-add-access">Add people or team</button><div id="access-form"></div>
      <table><thead><tr><th>Team or person</th><th>Role</th><th>Action</th></tr></thead><tbody>${repo.accesses.map((access) => `<tr><td>${escapeHtml(access.subject)}</td><td><span>${escapeHtml(access.role[0].toUpperCase() + access.role.slice(1))}</span><select aria-label="Role" data-access-role="${escapeHtml(access.subject)}"><option value="read" label="Read" ${access.role === "read" ? "selected" : ""}></option><option value="write" label="Write" ${access.role === "write" ? "selected" : ""}></option><option value="admin" label="Admin" ${access.role === "admin" ? "selected" : ""}></option></select></td><td><button class="btn secondary" type="button" data-save-access="${escapeHtml(access.subject)}">Save</button></td></tr>`).join("")}</tbody></table></section></div>
    `);
    root.querySelector('[data-action="show-add-access"]').addEventListener("click", (event) => {
      event.currentTarget.remove();
      const teams = state.teams.map((team) => team.name);
      root.querySelector("#access-form").innerHTML = `<form class="panel stack" data-form="add-access"><div class="form-row"><label for="access-search">Search team</label><input id="access-search" name="subject" type="text" autocomplete="off" /><div id="access-options" role="listbox"></div></div><div class="form-row"><span>Role</span><button id="access-role" type="button" role="combobox" aria-label="Role" aria-expanded="false" data-action="access-role">Read</button><input name="role" type="hidden" value="read" /><div id="access-role-options" role="listbox"></div></div><button class="btn" type="submit">Add</button></form>`;
      const search = root.querySelector("#access-search");
      const renderOptions = () => {
        const query = search.value.toLowerCase();
        root.querySelector("#access-options").innerHTML = teams
          .filter((name) => name.toLowerCase().includes(query))
          .map((name) => `<button type="button" role="option" class="option" data-access-option="${escapeHtml(name)}">${escapeHtml(name)}</button>`)
          .join("");
        root.querySelectorAll("[data-access-option]").forEach((option) => option.addEventListener("click", () => {
          search.value = option.dataset.accessOption;
          root.querySelector("#access-options").innerHTML = "";
        }));
      };
      search.addEventListener("focus", renderOptions);
      search.addEventListener("input", renderOptions);
      root.querySelector('[data-action="access-role"]').addEventListener("click", (event) => {
        event.currentTarget.setAttribute("aria-expanded", "true");
        root.querySelector("#access-role-options").innerHTML = '<button type="button" role="option" class="option" data-access-role-option="read">Read</button><button type="button" role="option" class="option" data-access-role-option="write">Write</button><button type="button" role="option" class="option" data-access-role-option="admin">Admin</button>';
        root.querySelectorAll("[data-access-role-option]").forEach((option) => option.addEventListener("click", () => {
          const value = option.dataset.accessRoleOption;
          root.querySelector('#access-form [name="role"]').value = value;
          root.querySelector('[data-action="access-role"]').textContent = value[0].toUpperCase() + value.slice(1);
          root.querySelector('[data-action="access-role"]').setAttribute("aria-expanded", "false");
          root.querySelector("#access-role-options").innerHTML = "";
        }));
      });
      root.querySelector('[data-form="add-access"]').addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.currentTarget));
        await command("list.add", { collection: "repositories", id: repo.id, field: "accesses", value: { subject: data.subject, role: data.role }, uniqueKey: "subject" });
        render();
      });
    });
    root.querySelectorAll("[data-save-access]").forEach((button) => button.addEventListener("click", async () => {
      const subject = button.dataset.saveAccess;
      const role = root.querySelector(`[data-access-role="${CSS.escape(subject)}"]`).value;
      const accesses = repo.accesses.map((access) => access.subject === subject ? { ...access, role } : access);
      await command("patch", { collection: "repositories", id: repo.id, patch: { accesses } });
      render();
    }));
    return;
  }
  const administrator = canAdminRepository(repo);
  layout(`<div class="split">${nav}<section class="panel stack"><h1>Repository settings</h1><p>General settings for ${escapeHtml(repo.name)}.</p><p>Visibility: <span class="badge">${escapeHtml(repo.visibility[0].toUpperCase() + repo.visibility.slice(1))}</span></p>${administrator ? '<button class="btn danger" type="button" data-action="change-visibility">Change visibility</button><div id="visibility-form"></div>' : ""}</section></div>`);
  root.querySelector('[data-action="change-visibility"]')?.addEventListener("click", () => {
    root.querySelector("#visibility-form").innerHTML = `<form class="panel stack" data-form="visibility"><label class="checkbox-row"><input type="radio" name="visibility" value="public" ${repo.visibility === "public" ? "checked" : ""} /> Public</label><label class="checkbox-row"><input type="radio" name="visibility" value="private" ${repo.visibility === "private" ? "checked" : ""} /> Private</label><button class="btn danger" type="submit">Confirm visibility change</button></form>`;
    root.querySelector('[data-form="visibility"]').addEventListener("submit", async (event) => {
      event.preventDefault();
      const visibility = String(new FormData(event.currentTarget).get("visibility") || repo.visibility);
      await command("patch", { collection: "repositories", id: repo.id, patch: { visibility } });
      render();
    });
  });
}

function searchView() {
  const query = new URLSearchParams(location.search).get("q") || "";
  const matches = state.repositories.filter(
    (repo) => repo.name.toLowerCase().includes(query.toLowerCase()) && canViewRepository(repo),
  );
  layout(`
    <section class="stack">
      <h1>Search repositories</h1>
      <p class="muted">Results for “${escapeHtml(query)}”</p>
      ${
        matches.length
          ? matches.map((repo) => `<article class="card"><h2>${link(`/${repo.owner}/${repo.name}`, repo.name)}</h2><span class="badge">${escapeHtml(repo.visibility)}</span></article>`).join("")
          : '<div class="panel">No repositories found. No results.</div>'
      }
    </section>
  `);
}

function notFoundView() {
  layout(`<section class="panel stack"><h1>Not found</h1><p>The requested page is not available.</p></section>`, true);
}

async function render() {
  if (!state) state = await request("/api/state");
  const path = location.pathname;
  if (path === "/") return homeView();
  if (path === "/login") return loginView();
  if (path === "/signup") return signupView();
  if (path === "/forgot-password") return forgotPasswordView();
  if (path === "/logout") return logoutView();
  if (path === "/settings") return settingsView();
  if (path === "/settings/password") return passwordSettingsView();
  if (path === "/search") return searchView();
  if (path === "/repositories/new") return newRepositoryView();

  if (path === "/organizations") return organizationsView();
  if (path === "/organizations/new") return newOrganizationView();

  if (handleEnterpriseRoute({
    path,
    state,
    root,
    escapeHtml,
    currentUser,
    worldId,
    layout,
    link,
    repoTabs,
    organizationTabs,
    command,
    navigate,
    render,
    bindCommon,
    authRequired,
    canViewRepository,
    canAdminRepository,
  })) return;

  let match = path.match(/^\/orgs\/([^/]+)\/teams\/new$/);
  if (match) {
    const org = state.organizations.find((entry) => entry.name === decodeURIComponent(match[1]));
    return org ? newTeamView(org) : notFoundView();
  }

  match = path.match(/^\/orgs\/([^/]+)\/teams\/([^/]+)(?:\/(members|settings))?$/);
  if (match) {
    const organizationName = decodeURIComponent(match[1]);
    const teamName = decodeURIComponent(match[2]);
    const org = state.organizations.find((entry) => entry.name === organizationName);
    const team = state.teams.find((entry) => entry.organization === organizationName && entry.name === teamName);
    return org && team ? teamView(org, team, match[3] || "overview") : notFoundView();
  }

  match = path.match(/^\/orgs\/([^/]+)(?:\/(repositories|teams|people))?$/);
  if (match) {
    const org = state.organizations.find((entry) => entry.name === decodeURIComponent(match[1]));
    if (!org) return notFoundView();
    if (match[2] === "repositories") return organizationRepositoriesView(org);
    if (match[2] === "teams") return organizationTeamsView(org);
    if (match[2] === "people") return organizationPeopleView(org);
    return organizationView(org);
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/issues\/new$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? newIssueView(repo) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/issues\/(\d+)$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    const issue = repo && state.issues.find((entry) => entry.repoId === repo.id && entry.number === Number(match[3]));
    return repo && issue ? issueView(repo, issue) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/issues$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? repositoryIssuesView(repo) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/pulls\/new$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? newPullRequestView(repo) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/pulls$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? repositoryPullsView(repo) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/compare\/([^/]+)\.\.\.([^/]+)$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? compareBranchesView(repo, decodeURIComponent(match[3]), decodeURIComponent(match[4])) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/pull\/(\d+)\/(commits|files)$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    const pull = repo && state.pullRequests.find((entry) => entry.repoId === repo.id && entry.number === Number(match[3]));
    if (!repo || !pull) return notFoundView();
    return match[4] === "commits" ? pullRequestCommitsView(repo, pull) : pullRequestFilesView(repo, pull);
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/pull\/(\d+)$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    const pull = repo && state.pullRequests.find((entry) => entry.repoId === repo.id && entry.number === Number(match[3]));
    return repo && pull ? pullRequestView(repo, pull) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/search$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? repositorySearchView(repo) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/commits$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? repositoryCommitsView(repo) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/commit\/([^/]+)$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? repositoryCommitView(repo, decodeURIComponent(match[3])) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/tree\/([^/]+)\/(.+)$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? repositoryDirectoryView(repo, decodeURIComponent(match[3]), decodeURIComponent(match[4])) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/blob\/([^/]+)\/(.+)$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? repositoryFileView(repo, decodeURIComponent(match[3]), decodeURIComponent(match[4])) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/new\/([^/]+)$/);
  if (match) {
    const repo = state.repositories.find((entry) => entry.owner === decodeURIComponent(match[1]) && entry.name === decodeURIComponent(match[2]));
    return repo ? newFileView(repo, decodeURIComponent(match[3])) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/settings(?:\/(access|branches))?$/);
  if (match) {
    const owner = decodeURIComponent(match[1]);
    const name = decodeURIComponent(match[2]);
    const repo = state.repositories.find((entry) => entry.owner === owner && entry.name === name);
    return repo ? repositorySettingsView(repo, match[3] || "general") : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)\/fork$/);
  if (match) {
    const owner = decodeURIComponent(match[1]);
    const name = decodeURIComponent(match[2]);
    const repo = state.repositories.find((entry) => entry.owner === owner && entry.name === name);
    return repo && canViewRepository(repo) ? forkRepositoryView(repo) : notFoundView();
  }

  match = path.match(/^\/([^/]+)\/([^/]+)$/);
  if (match) {
    const owner = decodeURIComponent(match[1]);
    const name = decodeURIComponent(match[2]);
    const repo = state.repositories.find((entry) => entry.owner === owner && entry.name === name);
    return repo ? repositoryView(repo) : notFoundView();
  }
  return notFoundView();
}

window.addEventListener("popstate", render);
render();
