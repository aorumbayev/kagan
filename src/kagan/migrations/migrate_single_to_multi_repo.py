"""Migrate existing single-repo data to multi-repo schema."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlmodel import col, select

from kagan.adapters.db.schema import (
    Merge,
    Project,
    ProjectRepo,
    Repo,
    Task,
    Workspace,
    WorkspaceRepo,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def migrate_existing_data(session: AsyncSession) -> None:
    """Migrate single-repo records to junction tables.

    Strategy:
    1. For each existing Repo (currently tied to project_id), create ProjectRepo
    2. For each Workspace with repo_id, create WorkspaceRepo with worktree_path
    3. Backfill merges.repo_id from workspace.repo_id or task.repo_id

    This migration is idempotent - safe to run multiple times.
    """
    await _migrate_project_repos(session)
    await _migrate_workspace_repos(session)
    await _backfill_merge_repo_ids(session)
    await session.commit()
    logger.info("Multi-repo data migration completed")


async def _migrate_project_repos(session: AsyncSession) -> None:
    """Create ProjectRepo links for existing repos."""
    result = await session.execute(select(Repo))
    repos = result.scalars().all()

    migrated = 0
    for repo in repos:
        if not repo.project_id:
            continue

        # Check if link already exists
        link_result = await session.execute(
            select(ProjectRepo).where(
                ProjectRepo.project_id == repo.project_id,
                ProjectRepo.repo_id == repo.id,
            )
        )
        if link_result.scalars().first() is not None:
            continue

        # Check if this is the default repo for the project
        project = await session.get(Project, repo.project_id)
        is_primary = project.default_repo_id == repo.id if project else False

        session.add(
            ProjectRepo(
                project_id=repo.project_id,
                repo_id=repo.id,
                is_primary=is_primary,
            )
        )
        migrated += 1

    if migrated > 0:
        logger.info(f"Created {migrated} ProjectRepo links")


async def _migrate_workspace_repos(session: AsyncSession) -> None:
    """Create WorkspaceRepo links for existing workspaces."""
    result = await session.execute(select(Workspace))
    workspaces = result.scalars().all()

    migrated = 0
    for workspace in workspaces:
        if not workspace.repo_id:
            continue

        # Check if link already exists
        link_result = await session.execute(
            select(WorkspaceRepo).where(
                WorkspaceRepo.workspace_id == workspace.id,
                WorkspaceRepo.repo_id == workspace.repo_id,
            )
        )
        if link_result.scalars().first() is not None:
            continue

        # Get target branch from repo
        repo = await session.get(Repo, workspace.repo_id)
        target_branch = repo.default_branch if repo else "main"

        session.add(
            WorkspaceRepo(
                workspace_id=workspace.id,
                repo_id=workspace.repo_id,
                target_branch=target_branch,
                worktree_path=workspace.path,
            )
        )
        migrated += 1

    if migrated > 0:
        logger.info(f"Created {migrated} WorkspaceRepo links")


async def _backfill_merge_repo_ids(session: AsyncSession) -> None:
    """Backfill merges.repo_id from workspace or task."""
    result = await session.execute(select(Merge).where(col(Merge.repo_id).is_(None)))
    merges = result.scalars().all()

    backfilled = 0
    for merge in merges:
        repo_id = None

        # Try to get repo_id from workspace first
        if merge.workspace_id:
            workspace = await session.get(Workspace, merge.workspace_id)
            if workspace:
                repo_id = workspace.repo_id

        # Fall back to task's repo_id
        if repo_id is None:
            task = await session.get(Task, merge.task_id)
            if task:
                repo_id = task.repo_id

        if repo_id:
            merge.repo_id = repo_id
            session.add(merge)
            backfilled += 1

    if backfilled > 0:
        logger.info(f"Backfilled repo_id for {backfilled} merges")
