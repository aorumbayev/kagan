"""Shared git adapter data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from kagan.services.types import TaskId, WorkspaceId


@dataclass(frozen=True)
class WorktreeInfo:
    """Descriptor for a managed worktree."""

    workspace_id: WorkspaceId
    task_id: TaskId | None
    path: Path
    branch: str
    base_branch: str


@dataclass(frozen=True)
class MergeOutcome:
    """Outcome for merge-related git operations."""

    ok: bool
    message: str
    conflict_files: list[str] = field(default_factory=list)
    worktree_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RebaseOutcome:
    """Outcome for rebase operations."""

    ok: bool
    message: str
    conflict_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiffStats:
    """Diff summary information."""

    raw: str
    files_changed: int | None = None
    insertions: int | None = None
    deletions: int | None = None
