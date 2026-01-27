"""Agent management for Kagan."""

from kagan.acp.agent import Agent
from kagan.acp.messages import AgentFail, AgentReady
from kagan.agents.manager import AgentManager
from kagan.agents.prompt_loader import PromptLoader, dump_default_prompts
from kagan.agents.roles import AgentRole
from kagan.agents.scheduler import Scheduler
from kagan.agents.worktree import WorktreeError, WorktreeManager, slugify

__all__ = [
    "Agent",
    "AgentFail",
    "AgentManager",
    "AgentReady",
    "AgentRole",
    "PromptLoader",
    "Scheduler",
    "WorktreeError",
    "WorktreeManager",
    "dump_default_prompts",
    "slugify",
]
