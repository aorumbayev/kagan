"""Git adapter contracts."""

from kagan.adapters.git.diff import DiffAdapter
from kagan.adapters.git.merge import MergeAdapter
from kagan.adapters.git.types import DiffStats, MergeOutcome, RebaseOutcome, WorktreeInfo
from kagan.adapters.git.worktrees import WorktreeAdapter

__all__ = [
    "DiffAdapter",
    "DiffStats",
    "MergeAdapter",
    "MergeOutcome",
    "RebaseOutcome",
    "WorktreeAdapter",
    "WorktreeInfo",
]
