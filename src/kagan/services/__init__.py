"""Service layer interfaces."""

from kagan.services.automation import AutomationService, AutomationServiceImpl
from kagan.services.diffs import DiffService, DiffServiceImpl
from kagan.services.executions import ExecutionService, ExecutionServiceImpl
from kagan.services.merges import MergeService, MergeServiceImpl
from kagan.services.projects import ProjectService, ProjectServiceImpl
from kagan.services.repo_scripts import RepoScriptService, RepoScriptServiceImpl
from kagan.services.sessions import SessionService, SessionServiceImpl
from kagan.services.tasks import TaskService, TaskServiceImpl
from kagan.services.workspaces import WorkspaceService, WorkspaceServiceImpl

__all__ = [
    "AutomationService",
    "AutomationServiceImpl",
    "DiffService",
    "DiffServiceImpl",
    "ExecutionService",
    "ExecutionServiceImpl",
    "MergeService",
    "MergeServiceImpl",
    "ProjectService",
    "ProjectServiceImpl",
    "RepoScriptService",
    "RepoScriptServiceImpl",
    "SessionService",
    "SessionServiceImpl",
    "TaskService",
    "TaskServiceImpl",
    "WorkspaceService",
    "WorkspaceServiceImpl",
]
