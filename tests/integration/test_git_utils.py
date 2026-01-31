"""Tests for git_utils module - all async functions."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from kagan.git_utils import get_current_branch, has_git_repo, init_git_repo, list_local_branches
from tests.helpers.git import configure_git_user

pytestmark = pytest.mark.integration


async def _run_git(repo_path: Path, *args: str) -> None:
    """Run git command silently."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()


class TestHasGitRepo:
    """Tests for has_git_repo function."""

    async def test_returns_true_for_valid_repo(self, tmp_path: Path) -> None:
        await _run_git(tmp_path, "init")
        assert await has_git_repo(tmp_path) is True

    async def test_returns_false_for_non_repo(self, tmp_path: Path) -> None:
        assert await has_git_repo(tmp_path) is False

    async def test_returns_false_when_git_not_found(self, tmp_path: Path) -> None:
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            assert await has_git_repo(tmp_path) is False


class TestListLocalBranches:
    """Tests for list_local_branches function."""

    async def test_returns_empty_for_non_repo(self, tmp_path: Path) -> None:
        assert await list_local_branches(tmp_path) == []

    async def test_returns_branches_for_valid_repo(self, tmp_path: Path) -> None:
        await _run_git(tmp_path, "init", "-b", "main")
        await configure_git_user(tmp_path)
        (tmp_path / "file.txt").write_text("content")
        await _run_git(tmp_path, "add", ".")
        await _run_git(tmp_path, "commit", "-m", "init")
        branches = await list_local_branches(tmp_path)
        assert "main" in branches

    async def test_returns_empty_when_git_not_found_on_branch_list(self, tmp_path: Path) -> None:
        """When has_git_repo succeeds but branch listing fails with FileNotFoundError."""
        await _run_git(tmp_path, "init")
        call_count = [0]

        async def mock_subprocess(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call (has_git_repo) - succeed
                mock_proc = MagicMock()
                mock_proc.communicate = AsyncMock(return_value=(b"true\n", b""))
                mock_proc.returncode = 0
                return mock_proc
            # Second call (branch list) - fail
            raise FileNotFoundError

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            assert await list_local_branches(tmp_path) == []


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    async def test_returns_empty_for_non_repo(self, tmp_path: Path) -> None:
        assert await get_current_branch(tmp_path) == ""

    async def test_returns_branch_name(self, tmp_path: Path) -> None:
        await _run_git(tmp_path, "init", "-b", "main")
        await configure_git_user(tmp_path)
        (tmp_path / "file.txt").write_text("content")
        await _run_git(tmp_path, "add", ".")
        await _run_git(tmp_path, "commit", "-m", "init")
        assert await get_current_branch(tmp_path) == "main"

    async def test_returns_empty_for_detached_head(self, tmp_path: Path) -> None:
        """When HEAD is detached, returns empty string."""
        call_count = [0]

        async def mock_subprocess(*args, **kwargs):
            call_count[0] += 1
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock()
            if call_count[0] == 1:
                # has_git_repo check
                mock_proc.communicate.return_value = (b"true\n", b"")
                mock_proc.returncode = 0
            else:
                # get current branch - detached HEAD
                mock_proc.communicate.return_value = (b"HEAD\n", b"")
                mock_proc.returncode = 0
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            assert await get_current_branch(tmp_path) == ""


class TestInitGitRepo:
    """Tests for init_git_repo function."""

    async def test_init_creates_repo_with_branch(self, tmp_path: Path) -> None:
        # Configure git globally for the test
        await _run_git(tmp_path, "config", "--global", "user.email", "test@test.com")
        await _run_git(tmp_path, "config", "--global", "user.name", "Test")
        result = await init_git_repo(tmp_path, "develop")
        assert result is True
        assert await has_git_repo(tmp_path)
        assert (tmp_path / ".gitkeep").exists()

    async def test_returns_false_when_git_not_found(self, tmp_path: Path) -> None:
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            assert await init_git_repo(tmp_path, "main") is False

    async def test_fallback_for_old_git_versions(self, tmp_path: Path) -> None:
        """When git init -b fails, falls back to git init + git branch -M."""
        call_count = [0]
        original_exec = asyncio.create_subprocess_exec

        async def mock_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count[0] += 1
            if call_count[0] == 1:
                # First call (init -b) fails
                mock_proc = MagicMock()
                mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
                mock_proc.returncode = 1
                return mock_proc
            # Subsequent calls use real implementation
            return await original_exec(*args, **kwargs)

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            result = await init_git_repo(tmp_path, "main")
            assert result is True

    async def test_returns_false_if_all_init_attempts_fail(self, tmp_path: Path) -> None:
        """When all init attempts fail, returns False."""

        async def mock_subprocess(*args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
            mock_proc.returncode = 1
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            assert await init_git_repo(tmp_path, "main") is False
