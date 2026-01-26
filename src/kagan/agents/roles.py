"""Agent role definitions."""

from __future__ import annotations

from enum import Enum


class AgentRole(str, Enum):
    """Role classification for agents."""

    WORKER = "worker"
    REVIEWER = "reviewer"
    PLANNER = "planner"
