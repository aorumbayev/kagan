"""Unified agent configuration resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kagan.config import AgentConfig, KaganConfig
    from kagan.database.models import Ticket


def resolve_model(
    config: KaganConfig,
    agent_identity: str,
) -> str | None:
    """Resolve the model to use based on config defaults.

    Priority:
    1. config.general.default_model_<agent> (project default for agent type)
    2. None (agent uses its own default)

    Args:
        config: The Kagan configuration
        agent_identity: The agent identity (e.g., 'claude.com', 'opencode')

    Returns:
        The model identifier to use, or None to use agent's default
    """
    # Priority 1: config's default model for this agent type
    if "claude" in agent_identity.lower():
        if config.general.default_model_claude:
            return config.general.default_model_claude
    elif "opencode" in agent_identity.lower():
        if config.general.default_model_opencode:
            return config.general.default_model_opencode

    # Priority 2: no override, agent uses its default
    return None


def resolve_agent_config(
    ticket: Ticket,
    config: KaganConfig,
) -> AgentConfig:
    """Resolve agent config with documented priority order.

    Priority:
    1. ticket.agent_backend (explicit override per ticket)
    2. config.general.default_worker_agent (project default)
    3. Fallback agent config (hardcoded sensible default)

    Args:
        ticket: The ticket to resolve config for
        config: The Kagan configuration

    Returns:
        The resolved AgentConfig
    """
    from kagan.config import get_fallback_agent_config
    from kagan.data.builtin_agents import get_builtin_agent

    # Priority 1: ticket's agent_backend field
    if ticket.agent_backend:
        if builtin := get_builtin_agent(ticket.agent_backend):
            return builtin.config
        if agent_config := config.get_agent(ticket.agent_backend):
            return agent_config

    # Priority 2: config's default_worker_agent
    default_agent = config.general.default_worker_agent
    if builtin := get_builtin_agent(default_agent):
        return builtin.config
    if agent_config := config.get_agent(default_agent):
        return agent_config

    # Priority 4: fallback
    return get_fallback_agent_config()
