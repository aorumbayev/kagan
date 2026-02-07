"""Workspace service with multi-repo support."""

from __future__ import annotations

import asyncio
import contextlib
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from sqlmodel import select

from kagan.adapters.git.worktrees import GitWorktreeAdapter
from kagan.core.events import WorkspaceProvisioned, WorkspaceReleased
from kagan.core.models.entities import Workspace as DomainWorkspace
from kagan.core.models.enums import WorkspaceStatus
from kagan.paths import get_worktree_base_dir

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from kagan.adapters.db.schema import Workspace as DbWorkspace
    from kagan.core.models.entities import Workspace
    from kagan.services.projects import ProjectService
    from kagan.services.tasks import TaskService
    from kagan.services.types import RepoId, TaskId, WorkspaceId


@dataclass
class RepoWorkspaceInput:
    """Input for creating a workspace repo."""

    repo_id: str
    repo_path: str
    target_branch: str


class WorkspaceService(Protocol):
    """Service interface for workspace operations."""

    async def provision(
        self,
        task_id: TaskId,
        repos: list[RepoWorkspaceInput],
        *,
        branch_name: str | None = None,
    ) -> str:
        """Provision a new workspace with worktrees for all repos."""

    async def provision_for_project(
        self,
        task_id: TaskId,
        project_id: str,
        *,
        branch_name: str | None = None,
    ) -> str:
        """Provision a workspace using all repos from the project."""

    async def release(
        self,
        workspace_id: WorkspaceId,
        *,
        reason: str | None = None,
        cleanup: bool = True,
    ) -> None:
        """Release a workspace and optionally clean up worktrees."""

    async def get_workspace_repos(self, workspace_id: WorkspaceId) -> list[dict]:
        """Get all repos for a workspace with their worktree paths."""

    async def get_agent_working_dir(self, workspace_id: WorkspaceId) -> Path:
        """Get the working directory for agents (typically primary repo)."""

    async def get_workspace(self, workspace_id: WorkspaceId) -> Workspace | None:
        """Return a workspace by ID."""

    async def list_workspaces(
        self,
        *,
        task_id: TaskId | None = None,
        repo_id: RepoId | None = None,
    ) -> list[Workspace]:
        """List workspaces filtered by task or repo."""

    async def create(self, task_id: TaskId, title: str, base_branch: str = "main") -> Path:
        """Create a worktree for the task and return its path."""

    async def delete(self, task_id: TaskId, *, delete_branch: bool = False) -> None:
        """Delete a worktree and optionally its branch."""

    async def get_path(self, task_id: TaskId) -> Path | None:
        """Return the worktree path, if it exists."""

    async def get_branch_name(self, task_id: TaskId) -> str | None:
        """Return the branch name for a worktree."""

    async def get_commit_log(self, task_id: TaskId, base_branch: str = "main") -> list[str]:
        """Return commit messages for the task worktree."""

    async def get_diff(self, task_id: TaskId, base_branch: str = "main") -> str:
        """Return the diff between task branch and base."""

    async def get_diff_stats(self, task_id: TaskId, base_branch: str = "main") -> str:
        """Return diff stats for the task branch."""

    async def get_files_changed(self, task_id: TaskId, base_branch: str = "main") -> list[str]:
        """Return files changed by the task branch."""

    async def get_merge_worktree_path(self, task_id: TaskId, base_branch: str = "main") -> Path:
        """Return the merge worktree path, creating it if needed."""

    async def prepare_merge_conflicts(
        self, task_id: TaskId, base_branch: str = "main"
    ) -> tuple[bool, str]:
        """Prepare merge worktree for manual conflict resolution."""

    async def cleanup_orphans(self, valid_task_ids: set[TaskId]) -> list[str]:
        """Remove worktrees not associated with any known task."""

    async def preflight_merge(self, task_id: TaskId, base_branch: str = "main") -> tuple[bool, str]:
        """Check whether merging would conflict."""

    async def rebase_onto_base(
        self, task_id: TaskId, base_branch: str = "main"
    ) -> tuple[bool, str, list[str]]:
        """Rebase the worktree branch onto the latest base branch."""

    async def get_files_changed_on_base(
        self, task_id: TaskId, base_branch: str = "main"
    ) -> list[str]:
        """Return files changed on the base branch since divergence."""

    async def merge_to_main(
        self,
        task_id: TaskId,
        base_branch: str = "main",
        squash: bool = True,
        allow_conflicts: bool = True,
    ) -> tuple[bool, str]:
        """Merge the worktree branch via the merge worktree."""


class WorkspaceServiceImpl:
    """Implementation of multi-repo WorkspaceService."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_bus,
        git_adapter: GitWorktreeAdapter,
        task_service: TaskService,
        project_service: ProjectService,
    ) -> None:
        self._session_factory = session_factory
        self._events = event_bus
        self._git = git_adapter
        self._tasks = task_service
        self._projects = project_service
        self._merge_worktrees_dir = get_worktree_base_dir() / "merge-worktrees"

    def _get_session(self) -> AsyncSession:
        return self._session_factory()

    def _get_workspace_base_dir(self, workspace_id: str) -> Path:
        return get_worktree_base_dir() / "worktrees" / workspace_id

    async def provision(
        self,
        task_id: str,
        repos: list[RepoWorkspaceInput],
        *,
        branch_name: str | None = None,
    ) -> str:
        """Provision a workspace with worktrees for all repos."""
        from kagan.adapters.db.schema import Workspace, WorkspaceRepo
        import uuid

        if not repos:
            raise ValueError("At least one repo is required to provision a workspace")

        workspace_id = uuid.uuid4().hex[:8]
        branch_name = branch_name or f"kagan/{workspace_id}"

        task = await self._tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        base_dir = self._get_workspace_base_dir(workspace_id)
        base_dir.mkdir(parents=True, exist_ok=True)

        workspace = Workspace(
            id=workspace_id,
            project_id=task.project_id,
            repo_id=repos[0].repo_id,
            task_id=task_id,
            path=str(base_dir),
            branch_name=branch_name,
        )

        created_paths: list[Path] = []
        workspace_repos: list[WorkspaceRepo] = []
        try:
            for repo_input in repos:
                worktree_path = base_dir / Path(repo_input.repo_path).name
                await self._git.create_worktree(
                    repo_path=repo_input.repo_path,
                    worktree_path=str(worktree_path),
                    branch_name=branch_name,
                    base_branch=repo_input.target_branch,
                )
                created_paths.append(worktree_path)

                workspace_repos.append(
                    WorkspaceRepo(
                        workspace_id=workspace_id,
                        repo_id=repo_input.repo_id,
                        target_branch=repo_input.target_branch,
                        worktree_path=str(worktree_path),
                    )
                )

            async with self._get_session() as session:
                session.add(workspace)
                for wr in workspace_repos:
                    session.add(wr)
                await session.commit()

        except Exception:
            for path in created_paths:
                with contextlib.suppress(Exception):
                    await self._git.delete_worktree(str(path))
            shutil.rmtree(base_dir, ignore_errors=True)
            raise

        await self._events.publish(
            WorkspaceProvisioned(
                workspace_id=workspace_id,
                task_id=task_id,
                branch=branch_name,
                path=str(base_dir),
                repo_count=len(repos),
            )
        )

        return workspace_id

    async def provision_for_project(
        self,
        task_id: str,
        project_id: str,
        *,
        branch_name: str | None = None,
    ) -> str:
        """Provision workspace using all project repos."""
        from kagan.adapters.db.schema import ProjectRepo, Repo

        async with self._get_session() as session:
            result = await session.execute(
                select(ProjectRepo, Repo)
                .join(Repo)
                .where(ProjectRepo.project_id == project_id)
                .order_by(ProjectRepo.display_order)
            )
            project_repos = result.all()

        if not project_repos:
            raise ValueError(f"Project {project_id} has no repos")

        repos = [
            RepoWorkspaceInput(
                repo_id=repo.id,
                repo_path=repo.path,
                target_branch=repo.default_branch,
            )
            for project_repo, repo in project_repos
        ]

        return await self.provision(task_id, repos, branch_name=branch_name)

    async def release(
        self,
        workspace_id: str,
        *,
        reason: str | None = None,
        cleanup: bool = True,
    ) -> None:
        """Release workspace and clean up worktrees."""
        from kagan.adapters.db.schema import Workspace, WorkspaceRepo

        async with self._get_session() as session:
            result = await session.execute(select(Workspace).where(Workspace.id == workspace_id))
            workspace = result.scalars().first()

            if not workspace:
                raise ValueError(f"Workspace {workspace_id} not found")

            if cleanup:
                result = await session.execute(
                    select(WorkspaceRepo).where(WorkspaceRepo.workspace_id == workspace_id)
                )
                workspace_repos = result.scalars().all()

                for wr in workspace_repos:
                    if wr.worktree_path and Path(wr.worktree_path).exists():
                        with contextlib.suppress(Exception):
                            await self._git.delete_worktree(wr.worktree_path)

                if workspace.path and Path(workspace.path).exists():
                    shutil.rmtree(workspace.path, ignore_errors=True)

            workspace.status = WorkspaceStatus.ARCHIVED
            workspace.updated_at = datetime.now()
            session.add(workspace)
            await session.commit()

        await self._events.publish(
            WorkspaceReleased(
                workspace_id=workspace_id,
                task_id=workspace.task_id,
                reason=reason,
            )
        )

    async def get_workspace_repos(self, workspace_id: str) -> list[dict]:
        """Get all repos for a workspace with paths and status."""
        from kagan.adapters.db.schema import Repo, WorkspaceRepo

        async with self._get_session() as session:
            result = await session.execute(
                select(WorkspaceRepo, Repo)
                .join(Repo)
                .where(WorkspaceRepo.workspace_id == workspace_id)
            )
            results = result.all()

        items: list[dict] = []
        for workspace_repo, repo in results:
            has_changes = await self._has_changes(workspace_repo.worktree_path)
            diff_stats = None
            if has_changes and workspace_repo.worktree_path:
                diff_stats = await self._git.get_diff_stats(
                    workspace_repo.worktree_path,
                    workspace_repo.target_branch,
                )
            items.append(
                {
                    "repo_id": repo.id,
                    "repo_name": repo.name,
                    "repo_path": repo.path,
                    "worktree_path": workspace_repo.worktree_path,
                    "target_branch": workspace_repo.target_branch,
                    "has_changes": has_changes,
                    "diff_stats": diff_stats,
                }
            )

        return items

    async def get_agent_working_dir(self, workspace_id: str) -> Path:
        """Get working directory for agents (primary repo's worktree)."""
        workspace = await self._get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace {workspace_id} not found")

        repos = await self.get_workspace_repos(workspace_id)
        if not repos:
            raise ValueError(f"Workspace {workspace_id} has no repos")

        if workspace.repo_id:
            for repo in repos:
                if repo["repo_id"] == workspace.repo_id:
                    return Path(repo["worktree_path"])

        return Path(repos[0]["worktree_path"])

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        workspace = await self._get_workspace(workspace_id)
        if workspace is None:
            return None
        return DomainWorkspace.model_validate(workspace)

    async def list_workspaces(
        self,
        *,
        task_id: str | None = None,
        repo_id: str | None = None,
    ) -> list[Workspace]:
        from kagan.adapters.db.schema import Workspace

        async with self._get_session() as session:
            statement = select(Workspace).order_by(Workspace.created_at.desc())
            if task_id is not None:
                statement = statement.where(Workspace.task_id == task_id)
            if repo_id is not None:
                statement = statement.where(Workspace.repo_id == repo_id)
            result = await session.execute(statement)
            return [DomainWorkspace.model_validate(item) for item in result.scalars().all()]

    async def create(self, task_id: str, title: str, base_branch: str = "main") -> Path:
        """Create a workspace for the task and return primary worktree path."""
        del title
        task = await self._tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        repos = await self._projects.get_project_repos(task.project_id)
        if not repos:
            raise ValueError(f"Project {task.project_id} has no repos")

        repo_inputs = [
            RepoWorkspaceInput(
                repo_id=repo.id,
                repo_path=repo.path,
                target_branch=repo.default_branch or base_branch,
            )
            for repo in repos
        ]
        workspace_id = await self.provision(task_id, repo_inputs)
        return await self.get_agent_working_dir(workspace_id)

    async def delete(self, task_id: str, *, delete_branch: bool = False) -> None:
        del delete_branch
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return
        await self.release(workspace.id, cleanup=True)

    async def get_path(self, task_id: str) -> Path | None:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return None
        return await self.get_agent_working_dir(workspace.id)

    async def get_branch_name(self, task_id: str) -> str | None:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return None
        return workspace.branch_name

    async def get_commit_log(self, task_id: str, base_branch: str = "main") -> list[str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return []
        worktree_path = await self.get_agent_working_dir(workspace.id)
        target_branch = await self._get_primary_target_branch(workspace.id, base_branch)
        return await self._git.get_commit_log(str(worktree_path), target_branch)

    async def get_diff(self, task_id: str, base_branch: str = "main") -> str:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return ""
        worktree_path = await self.get_agent_working_dir(workspace.id)
        target_branch = await self._get_primary_target_branch(workspace.id, base_branch)
        return await self._git.get_diff(str(worktree_path), target_branch)

    async def get_diff_stats(self, task_id: str, base_branch: str = "main") -> str:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return ""
        worktree_path = await self.get_agent_working_dir(workspace.id)
        target_branch = await self._get_primary_target_branch(workspace.id, base_branch)
        stdout, _ = await self._run_git(
            "diff", "--stat", f"{target_branch}..HEAD", cwd=worktree_path, check=False
        )
        return stdout.strip()

    async def get_files_changed(self, task_id: str, base_branch: str = "main") -> list[str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return []
        worktree_path = await self.get_agent_working_dir(workspace.id)
        target_branch = await self._get_primary_target_branch(workspace.id, base_branch)
        return await self._git.get_files_changed(str(worktree_path), target_branch)

    async def get_merge_worktree_path(self, task_id: str, base_branch: str = "main") -> Path:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            raise ValueError(f"Workspace not found for task {task_id}")
        return await self._ensure_merge_worktree(workspace.repo_id, base_branch, workspace)

    async def prepare_merge_conflicts(
        self, task_id: str, base_branch: str = "main"
    ) -> tuple[bool, str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return False, f"Workspace not found for task {task_id}"
        branch_name = workspace.branch_name

        merge_path = await self._ensure_merge_worktree(workspace.repo_id, base_branch, workspace)
        if await self._merge_in_progress(merge_path):
            return True, "Merge already in progress"

        try:
            await self._reset_merge_worktree(merge_path, base_branch)
            await self._run_git(
                "merge",
                "--squash",
                branch_name,
                cwd=merge_path,
                check=False,
            )
            status_out, _ = await self._run_git("status", "--porcelain", cwd=merge_path)
            if any(marker in status_out for marker in ("UU ", "AA ", "DD ")):
                return True, "Merge conflicts prepared"

            await self._run_git("merge", "--abort", cwd=merge_path, check=False)
            return False, "No conflicts detected"
        except Exception as exc:
            return False, f"Prepare failed: {exc}"

    async def cleanup_orphans(self, valid_task_ids: set[str]) -> list[str]:
        from kagan.adapters.db.schema import Workspace

        async with self._get_session() as session:
            result = await session.execute(select(Workspace))
            workspaces = result.scalars().all()

        cleaned: list[str] = []
        for workspace in workspaces:
            if workspace.task_id and workspace.task_id not in valid_task_ids:
                await self.release(workspace.id, cleanup=True)
                cleaned.append(workspace.id)

        return cleaned

    async def preflight_merge(self, task_id: str, base_branch: str = "main") -> tuple[bool, str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return False, f"Workspace not found for task {task_id}"

        branch_name = workspace.branch_name
        merge_path = await self._ensure_merge_worktree(workspace.repo_id, base_branch, workspace)

        try:
            if await self._merge_in_progress(merge_path):
                return False, "Merge worktree has unresolved conflicts. Resolve before merging."

            await self._reset_merge_worktree(merge_path, base_branch)
            await self._run_git(
                "merge",
                "--no-commit",
                "--no-ff",
                branch_name,
                cwd=merge_path,
                check=False,
            )

            status_out, _ = await self._run_git("status", "--porcelain", cwd=merge_path)
            if any(marker in status_out for marker in ("UU ", "AA ", "DD ")):
                await self._run_git("merge", "--abort", cwd=merge_path, check=False)
                return False, "Merge conflict predicted. Please resolve before merging."

            await self._run_git("merge", "--abort", cwd=merge_path, check=False)
            return True, "Preflight clean"
        except Exception as exc:
            await self._run_git("merge", "--abort", cwd=merge_path, check=False)
            return False, f"Preflight failed: {exc}"

    async def rebase_onto_base(
        self, task_id: str, base_branch: str = "main"
    ) -> tuple[bool, str, list[str]]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return False, f"Workspace not found for task {task_id}", []

        wt_path = await self.get_agent_working_dir(workspace.id)
        try:
            await self._run_git("fetch", "origin", base_branch, cwd=wt_path, check=False)

            status_out, _ = await self._run_git("status", "--porcelain", cwd=wt_path)
            if status_out.strip():
                return False, "Cannot rebase: worktree has uncommitted changes", []

            stdout, stderr = await self._run_git(
                "rebase", f"origin/{base_branch}", cwd=wt_path, check=False
            )
            combined_output = f"{stdout}\n{stderr}".lower()
            if "conflict" in combined_output or "could not apply" in combined_output:
                status_out, _ = await self._run_git("status", "--porcelain", cwd=wt_path)
                conflicting_files = []
                for line in status_out.split("\n"):
                    if line.startswith("UU ") or line.startswith("AA ") or line.startswith("DD "):
                        conflicting_files.append(line[3:].strip())

                await self._run_git("rebase", "--abort", cwd=wt_path, check=False)
                return (
                    False,
                    f"Rebase conflict in {len(conflicting_files)} file(s)",
                    conflicting_files,
                )

            return True, f"Successfully rebased onto {base_branch}", []
        except Exception as exc:
            await self._run_git("rebase", "--abort", cwd=wt_path, check=False)
            return False, f"Rebase failed: {exc}", []

    async def get_files_changed_on_base(self, task_id: str, base_branch: str = "main") -> list[str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return []

        wt_path = await self.get_agent_working_dir(workspace.id)
        try:
            merge_base_out, _ = await self._run_git(
                "merge-base", "HEAD", f"origin/{base_branch}", cwd=wt_path, check=False
            )
            if not merge_base_out.strip():
                return []

            merge_base = merge_base_out.strip()
            diff_out, _ = await self._run_git(
                "diff", "--name-only", merge_base, f"origin/{base_branch}", cwd=wt_path
            )
            if not diff_out.strip():
                return []

            return [line.strip() for line in diff_out.split("\n") if line.strip()]
        except Exception:
            return []

    async def merge_to_main(
        self,
        task_id: str,
        base_branch: str = "main",
        squash: bool = True,
        allow_conflicts: bool = True,
    ) -> tuple[bool, str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return False, f"Workspace not found for task {task_id}"

        wt_path = await self.get_agent_working_dir(workspace.id)
        branch_name = workspace.branch_name
        repo_id = workspace.repo_id
        merge_path = await self._ensure_merge_worktree(workspace.repo_id, base_branch, workspace)

        try:
            if await self._merge_in_progress(merge_path):
                if not allow_conflicts:
                    return False, "Merge worktree has unresolved conflicts. Resolve before merging."

                status_out, _ = await self._run_git("status", "--porcelain", cwd=merge_path)
                if any(marker in status_out for marker in ("UU ", "AA ", "DD ")):
                    return False, "Merge conflicts still unresolved. Finish resolution first."

                commits = await self.get_commit_log(task_id, base_branch)
                if commits:
                    title = self._format_title_from_branch(branch_name)
                    staged, _ = await self._run_git(
                        "diff", "--cached", "--name-only", cwd=merge_path
                    )
                    if staged.strip():
                        commit_msg = await self._generate_semantic_commit(task_id, title, commits)
                        await self._run_git("commit", "-m", commit_msg, cwd=merge_path)

                return await self._fast_forward_base(
                    base_branch, repo_root=wt_path, repo_id=repo_id
                )

            await self._reset_merge_worktree(merge_path, base_branch)

            commits = await self.get_commit_log(task_id, base_branch)
            if not commits:
                return False, f"No commits to merge for task {task_id}"

            title = self._format_title_from_branch(branch_name)

            if squash:
                await self._run_git("merge", "--squash", branch_name, cwd=merge_path, check=False)
                status_out, _ = await self._run_git("status", "--porcelain", cwd=merge_path)
                if any(marker in status_out for marker in ("UU ", "AA ", "DD ")):
                    if not allow_conflicts:
                        await self._run_git("merge", "--abort", cwd=merge_path, check=False)
                    return False, "Merge conflict detected. Resolve in merge worktree."

                commit_msg = await self._generate_semantic_commit(task_id, title, commits)
                await self._run_git("commit", "-m", commit_msg, cwd=merge_path)
            else:
                stdout, stderr = await self._run_git(
                    "merge",
                    branch_name,
                    "-m",
                    f"Merge branch '{branch_name}'",
                    cwd=merge_path,
                    check=False,
                )
                if "CONFLICT" in stderr or "CONFLICT" in stdout:
                    if not allow_conflicts:
                        await self._run_git("merge", "--abort", cwd=merge_path, check=False)
                    return False, "Merge conflict detected. Resolve in merge worktree."

            return await self._fast_forward_base(base_branch, repo_root=wt_path, repo_id=repo_id)
        except Exception as exc:
            return False, f"Merge failed: {exc}"

    async def _has_changes(self, worktree_path: str | None) -> bool:
        if not worktree_path or not Path(worktree_path).exists():
            return False
        return await self._git.has_uncommitted_changes(worktree_path)

    async def _get_workspace(self, workspace_id: str) -> DbWorkspace | None:
        from kagan.adapters.db.schema import Workspace

        async with self._get_session() as session:
            return await session.get(Workspace, workspace_id)

    async def _get_latest_workspace_for_task(self, task_id: str) -> DbWorkspace | None:
        from kagan.adapters.db.schema import Workspace

        async with self._get_session() as session:
            result = await session.execute(
                select(Workspace)
                .where(Workspace.task_id == task_id)
                .order_by(Workspace.created_at.desc())
            )
            return result.scalars().first()

    async def _get_primary_target_branch(self, workspace_id: str, fallback: str) -> str:
        from kagan.adapters.db.schema import WorkspaceRepo

        async with self._get_session() as session:
            result = await session.execute(
                select(WorkspaceRepo)
                .where(WorkspaceRepo.workspace_id == workspace_id)
                .order_by(WorkspaceRepo.created_at.asc())
            )
            workspace_repo = result.scalars().first()

        if workspace_repo and workspace_repo.target_branch:
            return workspace_repo.target_branch
        return fallback

    async def _ensure_merge_worktree(
        self, repo_id: str, base_branch: str, workspace: DbWorkspace
    ) -> Path:
        merge_path = self._merge_worktrees_dir / repo_id
        merge_path.parent.mkdir(parents=True, exist_ok=True)

        if merge_path.exists():
            return merge_path

        worktree_path = await self.get_agent_working_dir(workspace.id)
        repo_root = self._resolve_repo_root(worktree_path)
        await self._run_git(
            "worktree",
            "add",
            "-B",
            self._merge_branch_name(repo_id),
            str(merge_path),
            base_branch,
            cwd=repo_root,
        )
        return merge_path

    async def _reset_merge_worktree(self, merge_path: Path, base_branch: str) -> Path:
        await self._run_git("fetch", "origin", base_branch, cwd=merge_path, check=False)

        base_ref = base_branch
        if await self._ref_exists(f"refs/remotes/origin/{base_branch}", cwd=merge_path):
            base_ref = f"origin/{base_branch}"

        await self._run_git("checkout", self._merge_branch_name(merge_path.name), cwd=merge_path)
        await self._run_git("reset", "--hard", base_ref, cwd=merge_path)
        return merge_path

    async def _ref_exists(self, ref: str, cwd: Path) -> bool:
        stdout, _ = await self._run_git(
            "rev-parse",
            "--verify",
            "--quiet",
            ref,
            cwd=cwd,
            check=False,
        )
        return bool(stdout.strip())

    async def _merge_in_progress(self, cwd: Path) -> bool:
        stdout, _ = await self._run_git(
            "rev-parse",
            "-q",
            "--verify",
            "MERGE_HEAD",
            cwd=cwd,
            check=False,
        )
        return bool(stdout.strip())

    async def _fast_forward_base(
        self, base_branch: str, repo_root: Path, repo_id: str
    ) -> tuple[bool, str]:
        resolved_root = self._resolve_repo_root(repo_root)
        status_out, _ = await self._run_git("status", "--porcelain", cwd=resolved_root, check=False)
        if status_out.strip():
            return False, (
                "Cannot update base branch: repository has uncommitted changes. "
                "Please commit or stash your changes first."
            )

        head_branch, _ = await self._run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=resolved_root)
        if head_branch.strip() != base_branch:
            return (
                False,
                f"Cannot update base branch: checked out on '{head_branch}'. "
                f"Switch to '{base_branch}' and retry.",
            )

        try:
            await self._run_git(
                "merge",
                "--no-ff",
                self._merge_branch_name(repo_id),
                cwd=resolved_root,
            )
        except Exception as exc:
            return False, f"Fast-forward failed: {exc}"

        return True, f"Fast-forwarded {base_branch} to merge worktree"

    def _resolve_repo_root(self, worktree_path: Path) -> Path:
        git_file = worktree_path / ".git"
        if not git_file.exists():
            return worktree_path
        content = git_file.read_text().strip()
        if not content.startswith("gitdir:"):
            return worktree_path
        git_dir = content.split(":", 1)[1].strip()
        return Path(git_dir).parent.parent.parent

    async def _run_git(
        self, *args: str, check: bool = True, cwd: Path | None = None
    ) -> tuple[str, str]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        if check and proc.returncode != 0:
            raise RuntimeError(stderr_str or f"git {args[0]} failed with code {proc.returncode}")

        return stdout_str, stderr_str

    def _format_title_from_branch(self, branch_name: str) -> str:
        title = branch_name.split("/", 1)[-1]
        if "-" in title:
            parts = title.split("-", 1)
            if len(parts) > 1:
                title = parts[1].replace("-", " ").title()
        return title

    async def _generate_semantic_commit(self, task_id: str, title: str, commits: list[str]) -> str:
        del task_id
        title_lower = title.lower()

        if any(kw in title_lower for kw in ("fix", "bug", "issue")):
            commit_type = "fix"
        elif any(kw in title_lower for kw in ("add", "create", "implement", "new")):
            commit_type = "feat"
        elif any(kw in title_lower for kw in ("refactor", "clean", "improve")):
            commit_type = "refactor"
        elif any(kw in title_lower for kw in ("doc", "readme")):
            commit_type = "docs"
        elif "test" in title_lower:
            commit_type = "test"
        else:
            commit_type = "chore"

        scope = ""
        scope_match = re.match(r"^\w+\s+(\w+)", title)
        if scope_match:
            potential_scope = scope_match.group(1).lower()
            if len(potential_scope) > 2 and potential_scope not in (
                "the",
                "for",
                "and",
                "with",
                "from",
                "into",
            ):
                scope = potential_scope

        header = f"{commit_type}({scope}): {title}" if scope else f"{commit_type}: {title}"

        if commits:
            body_lines = []
            for commit in commits:
                parts = commit.split(" ", 1)
                msg = parts[1] if len(parts) > 1 else commit
                body_lines.append(f"- {msg}")
            body = "\n".join(body_lines)
            return f"{header}\n\n{body}"

        return header

    def _merge_branch_name(self, repo_id: str) -> str:
        return f"kagan/merge-worktree-{repo_id[:8]}"
