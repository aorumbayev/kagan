"""Diff adapter contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from kagan.adapters.git.types import DiffStats


class DiffAdapter(Protocol):
    """Adapter contract for diff and log operations."""

    async def get_commit_log(self, *, worktree_path: Path, base_branch: str) -> list[str]:
        """Return commit log entries for the worktree branch."""

    async def get_diff(self, *, worktree_path: Path, base_branch: str) -> str:
        """Return git diff text between base and worktree."""

    async def get_diff_stats(self, *, worktree_path: Path, base_branch: str) -> DiffStats:
        """Return diff statistics for the worktree."""

    async def get_files_changed(self, *, worktree_path: Path, base_branch: str) -> list[str]:
        """Return file paths changed in the worktree."""

    async def get_files_changed_on_base(
        self,
        *,
        worktree_path: Path,
        base_branch: str,
    ) -> list[str]:
        """Return file paths changed on base since the worktree branched."""
