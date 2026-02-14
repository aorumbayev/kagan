"""Focused tests for typed GitHub API methods and TUI API dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from _api_helpers import build_api

from kagan.core.plugins.github.contract import (
    GITHUB_CAPABILITY,
    GITHUB_METHOD_SYNC_ISSUES,
)
from kagan.core.request_handlers import handle_tui_api_call

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from kagan.core.api import KaganAPI
    from kagan.core.bootstrap import AppContext


@pytest.fixture
async def github_api_env(
    tmp_path: Path,
) -> AsyncGenerator[tuple[KaganAPI, AppContext]]:
    repo, api, ctx = await build_api(tmp_path)
    yield api, ctx
    await repo.close()


async def test_github_sync_issues_invokes_registered_operation(
    github_api_env: tuple[KaganAPI, AppContext],
) -> None:
    api, ctx = github_api_env
    handler = AsyncMock(return_value={"success": True, "stats": {"inserted": 3}})
    registry = MagicMock()
    registry.resolve_operation.return_value = SimpleNamespace(handler=handler)
    ctx.plugin_registry = registry

    result = await api.github_sync_issues(project_id=" project-1 ", repo_id=" repo-1 ")

    assert result["success"] is True
    assert result["stats"]["inserted"] == 3
    registry.resolve_operation.assert_called_once_with(GITHUB_CAPABILITY, GITHUB_METHOD_SYNC_ISSUES)
    handler.assert_awaited_once_with(
        ctx,
        {
            "project_id": "project-1",
            "repo_id": "repo-1",
        },
    )


async def test_github_connect_repo_rejects_empty_project_id(
    github_api_env: tuple[KaganAPI, AppContext],
) -> None:
    api, _ctx = github_api_env

    with pytest.raises(ValueError, match="project_id cannot be empty"):
        await api.github_connect_repo(project_id="   ")


async def test_tui_api_call_dispatches_github_sync_to_typed_api(
    github_api_env: tuple[KaganAPI, AppContext],
) -> None:
    api, ctx = github_api_env
    handler = AsyncMock(return_value={"success": True, "stats": {"updated": 2}})
    registry = MagicMock()
    registry.resolve_operation.return_value = SimpleNamespace(handler=handler)
    ctx.plugin_registry = registry

    result = await handle_tui_api_call(
        api,
        {
            "method": "github_sync_issues",
            "kwargs": {
                "project_id": "project-1",
                "repo_id": "repo-1",
            },
        },
    )

    assert result["success"] is True
    assert result["method"] == "github_sync_issues"
    assert result["value"]["success"] is True
    assert result["value"]["stats"]["updated"] == 2
