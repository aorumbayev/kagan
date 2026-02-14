"""Focused tests for CoreBackedApi typed GitHub wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from kagan.tui.core_client_api import CoreBackedApi


async def test_github_sync_issues_calls_tui_api_method() -> None:
    api = CoreBackedApi(MagicMock(), session_id="session-1")
    api._call_core = AsyncMock(return_value={"success": True, "stats": {"inserted": 1}})  # type: ignore[method-assign]

    result = await api.github_sync_issues(project_id="project-1", repo_id="repo-1")

    assert result["success"] is True
    assert result["stats"]["inserted"] == 1
    api._call_core.assert_awaited_once_with(  # type: ignore[attr-defined]
        "github_sync_issues",
        kwargs={"project_id": "project-1", "repo_id": "repo-1"},
    )


async def test_github_contract_probe_omits_blank_echo() -> None:
    api = CoreBackedApi(MagicMock(), session_id="session-1")
    api._call_core = AsyncMock(return_value={"success": True})  # type: ignore[method-assign]

    await api.github_contract_probe(echo="   ")

    api._call_core.assert_awaited_once_with(  # type: ignore[attr-defined]
        "github_contract_probe",
        kwargs={},
    )


async def test_github_connect_repo_rejects_empty_project_id() -> None:
    api = CoreBackedApi(MagicMock(), session_id="session-1")

    with pytest.raises(ValueError, match="project_id is required"):
        await api.github_connect_repo(project_id="")
