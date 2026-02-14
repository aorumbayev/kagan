"""Runtime adapter functions for bundled GitHub plugin operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.plugins.github import service as github_service

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext

GH_NOT_CONNECTED = github_service.GH_NOT_CONNECTED
GH_SYNC_FAILED = github_service.GH_SYNC_FAILED
GH_ISSUE_REQUIRED = github_service.GH_ISSUE_REQUIRED
GH_TASK_REQUIRED = github_service.GH_TASK_REQUIRED
GH_PR_CREATE_FAILED = github_service.GH_PR_CREATE_FAILED
GH_PR_LINK_FAILED = github_service.GH_PR_LINK_FAILED
GH_PR_NOT_FOUND = github_service.GH_PR_NOT_FOUND
GH_WORKSPACE_REQUIRED = github_service.GH_WORKSPACE_REQUIRED


def build_contract_probe_payload(params: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, machine-readable contract response for probe calls."""
    return github_service.GitHubPluginService.build_contract_probe_payload(params)


async def handle_connect_repo(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Connect a repository to GitHub with preflight checks."""
    return await github_service.GitHubPluginService(ctx).connect_repo(params)


async def handle_sync_issues(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Sync GitHub issues to Kagan task projections."""
    return await github_service.GitHubPluginService(ctx).sync_issues(params)


async def handle_acquire_lease(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Acquire a lease on a GitHub issue for the current Kagan instance."""
    return await github_service.GitHubPluginService(ctx).acquire_lease(params)


async def handle_release_lease(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Release a lease on a GitHub issue."""
    return await github_service.GitHubPluginService(ctx).release_lease(params)


async def handle_get_lease_state(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Get the current lease state for a GitHub issue."""
    return await github_service.GitHubPluginService(ctx).get_lease_state(params)


async def handle_create_pr_for_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a PR for a task and link it."""
    return await github_service.GitHubPluginService(ctx).create_pr_for_task(params)


async def handle_link_pr_to_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Link an existing PR to a task."""
    return await github_service.GitHubPluginService(ctx).link_pr_to_task(params)


async def handle_reconcile_pr_status(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Reconcile PR status for a task and apply deterministic board transitions."""
    return await github_service.GitHubPluginService(ctx).reconcile_pr_status(params)


__all__ = [
    "build_contract_probe_payload",
    "handle_acquire_lease",
    "handle_connect_repo",
    "handle_create_pr_for_task",
    "handle_get_lease_state",
    "handle_link_pr_to_task",
    "handle_reconcile_pr_status",
    "handle_release_lease",
    "handle_sync_issues",
]
