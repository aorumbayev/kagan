"""GitHub plugin API mixin.

Contains typed wrappers for the stable GitHub plugin contract operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.plugins.github.contract import (
    GITHUB_CAPABILITY,
    GITHUB_CONTRACT_PROBE_METHOD,
    GITHUB_METHOD_CONNECT_REPO,
    GITHUB_METHOD_SYNC_ISSUES,
)

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


class GitHubApiMixin:
    """Mixin providing typed GitHub plugin operation methods.

    Expects ``self._ctx`` to be an :class:`AppContext` instance,
    initialised by :class:`KaganAPI.__init__`.
    """

    _ctx: AppContext

    async def _invoke_github_operation(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Invoke a registered GitHub plugin operation by canonical method name."""
        plugin_registry = getattr(self._ctx, "plugin_registry", None)
        if plugin_registry is None:
            raise RuntimeError("Plugin registry is not initialized")

        operation = plugin_registry.resolve_operation(GITHUB_CAPABILITY, method)
        if operation is None:
            raise RuntimeError(f"GitHub plugin operation is not registered: {method}")

        result = await operation.handler(self._ctx, params)
        if not isinstance(result, dict):
            raise RuntimeError(f"GitHub plugin operation returned invalid payload: {method}")
        return result

    async def github_contract_probe(self, *, echo: str | None = None) -> dict[str, Any]:
        """Probe the GitHub plugin contract for verification."""
        params: dict[str, Any] = {}
        if echo is not None:
            params["echo"] = echo
        return await self._invoke_github_operation(GITHUB_CONTRACT_PROBE_METHOD, params)

    async def github_connect_repo(
        self,
        *,
        project_id: str,
        repo_id: str | None = None,
    ) -> dict[str, Any]:
        """Connect a repository to GitHub with preflight checks."""
        project_id = project_id.strip()
        if not project_id:
            raise ValueError("project_id cannot be empty")

        params: dict[str, Any] = {"project_id": project_id}
        if repo_id is not None:
            cleaned_repo_id = repo_id.strip()
            if not cleaned_repo_id:
                raise ValueError("repo_id cannot be empty")
            params["repo_id"] = cleaned_repo_id

        return await self._invoke_github_operation(GITHUB_METHOD_CONNECT_REPO, params)

    async def github_sync_issues(
        self,
        *,
        project_id: str,
        repo_id: str | None = None,
    ) -> dict[str, Any]:
        """Sync GitHub issues to Kagan tasks."""
        project_id = project_id.strip()
        if not project_id:
            raise ValueError("project_id cannot be empty")

        params: dict[str, Any] = {"project_id": project_id}
        if repo_id is not None:
            cleaned_repo_id = repo_id.strip()
            if not cleaned_repo_id:
                raise ValueError("repo_id cannot be empty")
            params["repo_id"] = cleaned_repo_id

        return await self._invoke_github_operation(GITHUB_METHOD_SYNC_ISSUES, params)


__all__ = ["GitHubApiMixin"]
