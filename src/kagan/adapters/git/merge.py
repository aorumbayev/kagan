"""Merge adapter contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from kagan.adapters.git.types import MergeOutcome, RebaseOutcome


class MergeAdapter(Protocol):
    """Adapter contract for merge-related git operations."""

    async def ensure_merge_worktree(self, *, base_branch: str) -> Path:
        """Ensure the merge worktree exists and return its path."""

    async def reset_merge_worktree(self, *, base_branch: str) -> Path:
        """Reset merge worktree to the latest base branch."""

    async def prepare_conflicts(self, *, branch_name: str, base_branch: str) -> MergeOutcome:
        """Prepare the merge worktree for manual conflict resolution."""

    async def preflight(self, *, worktree_path: Path, base_branch: str) -> MergeOutcome:
        """Check whether a merge would conflict without committing changes."""

    async def merge(
        self,
        *,
        branch_name: str,
        base_branch: str,
        allow_conflicts: bool = False,
    ) -> MergeOutcome:
        """Merge the branch into base via the merge worktree."""

    async def rebase_onto_base(self, *, branch_name: str, base_branch: str) -> RebaseOutcome:
        """Rebase the branch onto the latest base branch."""

    async def fast_forward_base(self, *, base_branch: str) -> MergeOutcome:
        """Fast-forward the base branch to the merge worktree head."""
