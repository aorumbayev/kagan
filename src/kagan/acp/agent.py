"""Agent module - re-exports KaganAgent for convenience."""

from __future__ import annotations

from kagan.acp.kagan_agent import KaganAgent

# Re-export KaganAgent as the main Agent class
Agent = KaganAgent

__all__ = ["Agent", "KaganAgent"]
