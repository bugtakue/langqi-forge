from __future__ import annotations


GITHUB_ACCOUNT_PREFIXES = (
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
)


def github_fixture_environment(base_url: str, profile: str = "baseline") -> dict[str, str]:
    if profile not in {"baseline", "adversarial"}:
        raise ValueError(f"unsupported fixture profile: {profile}")
    root = base_url.rstrip("/")
    environment: dict[str, str] = {}
    for index, prefix in enumerate(GITHUB_ACCOUNT_PREFIXES, 1):
        username = f"fixture-user-{index:02d}"
        environment[f"{prefix}_USERNAME"] = username
        environment[f"{prefix}_EMAIL"] = f"{username}@example.test"
        environment[f"{prefix}_PASSWORD"] = "Fixture-password-123!"

    environment.update(
        {
            "FACTORY26_RESET_FIXTURES": "1",
            "E2E_PASSWORD_CHANGE_NEW_PASSWORD": "Changed-password-456!",
            "E2E_PASSWORD_CHANGE_REQUIRED_NEW_PASSWORD": "Required-password-456!",
            "E2E_PROTECTED_URL": f"{root}/settings/password",
            "E2E_PUBLIC_ORGANIZATION_URL": f"{root}/orgs/open-labs",
            "E2E_PUBLIC_ORGANIZATION_REPOSITORY": "roadmap-app",
            "E2E_PRIVATE_ORGANIZATION_REPOSITORY": "private-ledger",
            "E2E_ORGANIZATION_URL": f"{root}/orgs/acme",
            "E2E_ORGANIZATION_UNGRANTED_PRIVATE_REPOSITORY_URL": f"{root}/acme/private-repo",
            "E2E_EXISTING_ORGANIZATION": "existing-org",
            "E2E_TEAM_URL": f"{root}/orgs/acme/teams/platform-team",
            "E2E_TEAM_CANDIDATE_USERNAME": "team-candidate",
            "E2E_CYCLIC_TEAM_URL": f"{root}/orgs/acme/teams/parent-team",
            "E2E_CYCLIC_TEAM_DESCENDANT": "child-team",
            "E2E_CYCLIC_TEAM_ORIGINAL_PARENT": "root-team",
            "E2E_ORGANIZATION_MEMBER_TO_REMOVE": "removable-user",
            "E2E_MANAGED_REPOSITORY_URL": f"{root}/acme/managed-repo",
            "E2E_ACCESS_TEAM_NAME": "platform-team",
            "E2E_ACCESS_ROLE_CHANGE_REPOSITORY_URL": f"{root}/acme/access-repo",
            "E2E_ACCESS_ROLE_CHANGE_TEAM_NAME": "security-team",
            "E2E_PUBLIC_REPOSITORY_NAME": "roadmap-app",
            "E2E_PRIVATE_REPOSITORY_NAME": "private-ledger",
            "E2E_EXISTING_OWNED_REPOSITORY": "existing-repo",
            "E2E_FORK_SOURCE_REPOSITORY_URL": f"{root}/open-labs/fork-source",
            "E2E_FORK_SOURCE_REPOSITORY_NAME": "fork-source",
            "E2E_EXISTING_FORK_NAME": "existing-fork",
            "E2E_PUBLIC_REPOSITORY_URL": f"{root}/open-labs/roadmap-app",
            "E2E_VISIBILITY_REPOSITORY_URL": f"{root}/acme/visibility-repo",
            "E2E_VISIBILITY_REPOSITORY_NAME": "visibility-repo",
            "E2E_CODE_REPOSITORY_URL": f"{root}/open-labs/code-repo",
            "E2E_CODE_DIRECTORY": "src",
            "E2E_CODE_FILE_NAME": "index.js",
            "E2E_CODE_FILE_CONTENT": "export const answer = 42;",
            "E2E_COMMIT_MESSAGE": "Seed the verified code fixture",
            "E2E_COMMIT_AUTHOR": "fixture-author",
            "E2E_COMMIT_URL": f"{root}/open-labs/code-repo/commit/seed-commit",
            "E2E_CHANGED_FILE": "src/index.js",
            "E2E_CODE_SEARCH_QUERY": "answer = 42",
            "E2E_CODE_SEARCH_FILE": "src/index.js",
            "E2E_CODE_SEARCH_EMPTY_QUERY": "not-present-in-repository",
            "E2E_BRANCH_REPOSITORY_URL": f"{root}/acme/branch-repo",
            "E2E_ACTIVE_BRANCH": "main",
            "E2E_TARGET_BRANCH": "feature",
            "E2E_TARGET_BRANCH_FILE": "feature.txt",
            "E2E_UNKNOWN_BRANCH_QUERY": "missing-branch",
            "E2E_DEFAULT_BRANCH_REPOSITORY_URL": f"{root}/acme/default-repo",
            "E2E_OLD_DEFAULT_BRANCH": "main",
            "E2E_NEW_DEFAULT_BRANCH": "develop",
            "E2E_FILE_REPOSITORY_URL": f"{root}/acme/file-repo",
            "E2E_ISSUES_URL": f"{root}/acme/issues-repo/issues",
            "E2E_OPEN_ISSUE_TITLE": "Active fixture issue",
            "E2E_CLOSED_ISSUE_TITLE": "Resolved fixture issue",
            "E2E_ISSUE_URL": f"{root}/acme/issues-repo/issues/1",
            "E2E_ISSUE_TITLE": "Fixture issue detail",
            "E2E_ISSUE_DESCRIPTION": "A durable issue description for browser acceptance.",
            "E2E_EDITABLE_ISSUE_URL": f"{root}/acme/issues-repo/issues/2",
            "E2E_INVALID_EDIT_ISSUE_URL": f"{root}/acme/issues-repo/issues/3",
            "E2E_INVALID_EDIT_ISSUE_TITLE": "Protected fixture issue",
            "E2E_COMMENTABLE_ISSUE_URL": f"{root}/acme/issues-repo/issues/4",
            "E2E_COMMENT_VALIDATION_ISSUE_URL": f"{root}/acme/issues-repo/issues/5",
            "E2E_ASSIGNABLE_ISSUE_URL": f"{root}/acme/issues-repo/issues/6",
            "E2E_ISSUE_ASSIGNEE": "issue-assignee",
            "E2E_LABELABLE_ISSUE_URL": f"{root}/acme/issues-repo/issues/7",
            "E2E_ISSUE_LABEL": "priority:high",
            "E2E_MILESTONE_ISSUE_URL": f"{root}/acme/issues-repo/issues/8",
            "E2E_ISSUE_MILESTONE": "Qualifier",
            "E2E_CLOSABLE_ISSUE_URL": f"{root}/acme/issues-repo/issues/9",
            "E2E_PROTECTED_ISSUE_URL": f"{root}/acme/issues-repo/issues/10",
            "E2E_PROTECTION_REPOSITORY_URL": f"{root}/acme/protection-repo",
            "E2E_PROTECTED_BRANCH_PATTERN": "main",
            "E2E_PROTECTION_PULL_REQUEST_URL": f"{root}/acme/protection-repo/pull/1",
            "E2E_PULL_REQUESTS_URL": f"{root}/acme/pr-repo/pulls",
            "E2E_OPEN_PULL_REQUEST_TITLE": "Active fixture pull request",
            "E2E_PR_BASE_BRANCH": "main",
            "E2E_PR_COMPARE_BRANCH": "feature",
            "E2E_PR_CHANGED_FILE": "src/feature.js",
            "E2E_VALID_COMPARE_URL": f"{root}/acme/pr-repo/compare/main...feature",
            "E2E_DRAFT_COMPARE_URL": f"{root}/acme/pr-repo/compare/main...review-feature",
            "E2E_DRAFT_PULL_REQUEST_SOURCE_BRANCH": "review-feature",
            "E2E_DRAFT_PULL_REQUEST_TARGET_BRANCH": "main",
            "E2E_DRAFT_PULL_REQUEST_TITLE": "Fixture work-in-progress pull request",
            "E2E_DRAFT_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/2",
            "E2E_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/3",
            "E2E_PULL_REQUEST_TITLE": "Fixture pull request detail",
            "E2E_PUBLIC_PULL_REQUEST_URL": f"{root}/open-labs/roadmap-app/pull/1",
            "E2E_REVIEWABLE_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/4",
            "E2E_PENDING_REVIEW_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/5",
            "E2E_CHANGE_REQUEST_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/6",
            "E2E_ASSIGNABLE_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/7",
            "E2E_REQUESTED_REVIEWER": "requested-reviewer",
            "E2E_MERGEABLE_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/8",
            "E2E_UNMERGEABLE_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/9",
            "E2E_CLOSABLE_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/10",
            "E2E_PROTECTED_PULL_REQUEST_URL": f"{root}/acme/pr-repo/pull/11",
        }
    )
    if profile == "adversarial":
        for index, prefix in enumerate(GITHUB_ACCOUNT_PREFIXES, 1):
            username = f"qa-zeta-{index:02d}"
            environment[f"{prefix}_USERNAME"] = username
            environment[f"{prefix}_EMAIL"] = f"{username}@mutation.test"
            environment[f"{prefix}_PASSWORD"] = "Mutated-password-784!"
        environment.update(
            {
                "E2E_PASSWORD_CHANGE_NEW_PASSWORD": "Mutated-change-785!",
                "E2E_PASSWORD_CHANGE_REQUIRED_NEW_PASSWORD": "Mutated-required-786!",
                "E2E_PUBLIC_ORGANIZATION_REPOSITORY": "atlas-service",
                "E2E_PRIVATE_ORGANIZATION_REPOSITORY": "vault-service",
                "E2E_EXISTING_ORGANIZATION": "reserved-studio",
                "E2E_TEAM_CANDIDATE_USERNAME": "candidate-zeta",
                "E2E_CYCLIC_TEAM_DESCENDANT": "child-zeta",
                "E2E_ORGANIZATION_MEMBER_TO_REMOVE": "removable-zeta",
                "E2E_PUBLIC_REPOSITORY_NAME": "atlas-service",
                "E2E_PRIVATE_REPOSITORY_NAME": "vault-service",
                "E2E_EXISTING_OWNED_REPOSITORY": "locked-repository",
                "E2E_FORK_SOURCE_REPOSITORY_NAME": "origin-kit",
                "E2E_EXISTING_FORK_NAME": "locked-fork",
                "E2E_VISIBILITY_REPOSITORY_NAME": "visibility-zeta",
                "E2E_TARGET_BRANCH": "release-zeta",
                "E2E_TARGET_BRANCH_FILE": "release-note.txt",
                "E2E_UNKNOWN_BRANCH_QUERY": "ghost-zeta",
                "E2E_OLD_DEFAULT_BRANCH": "trunk",
                "E2E_NEW_DEFAULT_BRANCH": "stable",
                "E2E_OPEN_ISSUE_TITLE": "Active zeta incident",
                "E2E_CLOSED_ISSUE_TITLE": "Resolved zeta incident",
                "E2E_ISSUE_TITLE": "Zeta issue detail",
                "E2E_ISSUE_DESCRIPTION": "A mutated durable issue description.",
                "E2E_INVALID_EDIT_ISSUE_TITLE": "Protected zeta issue",
                "E2E_ISSUE_ASSIGNEE": "assignee-zeta",
                "E2E_ISSUE_LABEL": "severity:critical",
                "E2E_ISSUE_MILESTONE": "Release Z",
                "E2E_PROTECTED_BRANCH_PATTERN": "release/*",
                "E2E_OPEN_PULL_REQUEST_TITLE": "Active zeta pull request",
                "E2E_DRAFT_PULL_REQUEST_SOURCE_BRANCH": "review-zeta",
                "E2E_DRAFT_PULL_REQUEST_TITLE": "Zeta work-in-progress pull request",
                "E2E_PULL_REQUEST_TITLE": "Zeta pull request detail",
                "E2E_REQUESTED_REVIEWER": "reviewer-zeta",
            }
        )
        environment.update(
            {
                "E2E_PUBLIC_ORGANIZATION_URL": f"{root}/orgs/open-labs",
                "E2E_FORK_SOURCE_REPOSITORY_URL": f"{root}/open-labs/origin-kit",
                "E2E_PUBLIC_REPOSITORY_URL": f"{root}/open-labs/atlas-service",
                "E2E_VISIBILITY_REPOSITORY_URL": f"{root}/acme/visibility-zeta",
                "E2E_DRAFT_COMPARE_URL": f"{root}/acme/pr-repo/compare/main...review-zeta",
                "E2E_PUBLIC_PULL_REQUEST_URL": f"{root}/open-labs/atlas-service/pull/1",
            }
        )
    return environment


def public_fixture_environment(task_id: str, base_url: str, profile: str = "baseline") -> dict[str, str]:
    if task_id == "github":
        return github_fixture_environment(base_url, profile)
    if profile != "baseline":
        raise ValueError(f"fixture profile {profile!r} is only available for github")
    return {}
