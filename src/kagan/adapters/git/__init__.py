"""Git adapter contracts."""

from kagan.adapters.git.diff import DiffAdapter
from kagan.adapters.git.merge import MergeAdapter
from kagan.adapters.git.operations import GitOperationsAdapter
from kagan.adapters.git.types import DiffStats, MergeOutcome, RebaseOutcome, WorktreeInfo
from kagan.adapters.git.worktrees import GitWorktreeAdapter, WorktreeAdapter

__all__ = [
    "DiffAdapter",
    "DiffStats",
    "GitOperationsAdapter",
    "MergeAdapter",
    "MergeOutcome",
    "RebaseOutcome",
    "GitWorktreeAdapter",
    "WorktreeAdapter",
    "WorktreeInfo",
]
