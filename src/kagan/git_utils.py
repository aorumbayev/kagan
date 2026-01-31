"""Utility helpers for git repository setup and queries.

All functions are async to avoid blocking the event loop during subprocess calls.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


async def has_git_repo(repo_root: Path) -> bool:
    """Return True if the path is inside a git work tree."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--is-inside-work-tree",
            cwd=repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return proc.returncode == 0 and stdout.decode().strip() == "true"
    except FileNotFoundError:
        return False


async def list_local_branches(repo_root: Path) -> list[str]:
    """Return local branch names for a repository, if any."""
    if not await has_git_repo(repo_root):
        return []
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "branch",
            "--list",
            "--format",
            "%(refname:short)",
            cwd=repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []
        return [line.strip() for line in stdout.decode().splitlines() if line.strip()]
    except FileNotFoundError:
        return []


async def get_current_branch(repo_root: Path) -> str:
    """Return the current git branch name, or empty string if unavailable."""
    if not await has_git_repo(repo_root):
        return ""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
            cwd=repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return ""
        branch = stdout.decode().strip()
        return "" if branch == "HEAD" else branch
    except FileNotFoundError:
        return ""


async def init_git_repo(repo_root: Path, base_branch: str) -> bool:
    """Initialize a git repo with the requested base branch and initial commit.

    Creates an initial commit so that worktrees can be created from the base branch.
    Without a commit, `git worktree add -b <branch> <path> <base>` fails with
    'fatal: invalid reference: <base>'.
    """

    async def run_git(*args: str) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=repo_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            returncode = proc.returncode if proc.returncode is not None else 1
            return returncode, stdout.decode()
        except FileNotFoundError:
            return 1, ""

    # Try init with -b flag first
    code, _ = await run_git("init", "-b", base_branch)
    if code != 0:
        # Fallback for older git versions without -b support
        code, _ = await run_git("init")
        if code != 0:
            return False
        code, _ = await run_git("branch", "-M", base_branch)
        if code != 0:
            return False

    # Create initial commit so worktrees can be created
    # Without a commit, the base branch doesn't exist as a valid reference
    gitkeep = repo_root / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("")

    code, _ = await run_git("add", ".gitkeep")
    if code != 0:
        return False

    code, _ = await run_git("commit", "-m", "Initial commit (kagan)")
    return code == 0
