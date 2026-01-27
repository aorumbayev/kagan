"""Agent manager for multiple ACP agent processes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import log

from kagan.acp.agent import Agent
from kagan.agents.message_bus import AgentMessageBus
from kagan.agents.roles import AgentRole

if TYPE_CHECKING:
    from pathlib import Path

    from textual.message_pump import MessagePump

    from kagan.config import AgentConfig


class AgentManager:
    """Manages multiple ACP agent processes."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._roles: dict[str, AgentRole] = {}
        self._buses: dict[str, AgentMessageBus] = {}

    async def spawn(
        self,
        ticket_id: str,
        agent_config: AgentConfig,
        cwd: Path,
        message_target: MessagePump | None = None,
        role: AgentRole = AgentRole.WORKER,
        auto_approve: bool = False,
    ) -> Agent:
        """Spawn a new agent for a ticket.

        Args:
            ticket_id: Unique ticket identifier.
            agent_config: Agent configuration with run command.
            cwd: Working directory for the agent.
            message_target: Textual widget to receive agent messages.
            role: Agent role classification.
            auto_approve: If True, auto-approve all permission requests.

        Returns:
            The spawned Agent instance.

        Raises:
            ValueError: If an agent is already running for this ticket.
        """
        log.info(f"[AgentManager.spawn] ticket_id={ticket_id}, cwd={cwd}, role={role}")
        log.info(f"[AgentManager.spawn] agent_config.name={agent_config.name}")
        log.info(f"[AgentManager.spawn] agent_config.run_command={agent_config.run_command}")

        if ticket_id in self._agents:
            log.warning(f"[AgentManager.spawn] Agent already running for {ticket_id}")
            raise ValueError(f"Agent already running for {ticket_id}")

        bus = self._buses.get(ticket_id)
        if bus is None:
            bus = AgentMessageBus()
            self._buses[ticket_id] = bus
        if message_target is not None:
            bus.subscribe(message_target)

        log.info("[AgentManager.spawn] Creating Agent instance...")
        agent = Agent(cwd, agent_config)
        if auto_approve:
            agent.set_auto_approve(True)
        log.info("[AgentManager.spawn] Calling agent.start()...")
        agent.start(bus)
        self._agents[ticket_id] = agent
        self._roles[ticket_id] = role
        log.info(f"[AgentManager.spawn] Agent started for {ticket_id}")
        return agent

    def get(self, ticket_id: str) -> Agent | None:
        """Get agent by ticket_id."""
        return self._agents.get(ticket_id)

    def get_role(self, ticket_id: str) -> AgentRole | None:
        """Get role for an agent."""
        return self._roles.get(ticket_id)

    def has_logs(self, ticket_id: str) -> bool:
        """Check if an agent has buffered output."""
        bus = self._buses.get(ticket_id)
        return bus.has_messages() if bus else False

    def list_known(self, role: AgentRole | None = None) -> list[str]:
        """List all agents with buffered output (active or inactive)."""
        ids = list(self._buses.keys())
        if role is None:
            return ids
        return [agent_id for agent_id in ids if self._roles.get(agent_id) == role]

    async def terminate(self, ticket_id: str) -> None:
        """Terminate a specific agent and clean up role tracking."""
        if agent := self._agents.pop(ticket_id, None):
            await agent.stop()
        # Clean up role tracking (keep _buses for log replay)
        self._roles.pop(ticket_id, None)

    def cleanup(self, ticket_id: str) -> None:
        """Fully clean up all resources for a ticket including message bus.

        Call this when logs are no longer needed (e.g., ticket is done/deleted).
        """
        self._agents.pop(ticket_id, None)
        self._roles.pop(ticket_id, None)
        if bus := self._buses.pop(ticket_id, None):
            # Clear subscribers to break reference cycles
            bus._subscribers.clear()
            bus._messages.clear()

    async def terminate_all(self) -> None:
        """Terminate all agents and clean up all resources."""
        for agent in list(self._agents.values()):
            await agent.stop()
        self._agents.clear()
        self._roles.clear()
        # Clear all buses to free memory
        for bus in self._buses.values():
            bus._subscribers.clear()
            bus._messages.clear()
        self._buses.clear()

    def list_active(self, role: AgentRole | None = None) -> list[str]:
        """List ticket_ids with active agents."""
        if role is None:
            return list(self._agents.keys())
        return [agent_id for agent_id in self._agents if self._roles.get(agent_id) == role]

    def count_active(self, role: AgentRole | None = None) -> int:
        """Count active agents, optionally filtered by role."""
        return len(self.list_active(role))

    def is_running(self, ticket_id: str) -> bool:
        """Check if an agent is running for a ticket."""
        return ticket_id in self._agents

    def subscribe(self, ticket_id: str, target: MessagePump) -> None:
        """Subscribe a UI target to buffered output for an agent."""
        if bus := self._buses.get(ticket_id):
            bus.subscribe(target)

    def unsubscribe(self, ticket_id: str, target: MessagePump) -> None:
        """Unsubscribe a UI target from an agent stream."""
        if bus := self._buses.get(ticket_id):
            bus.unsubscribe(target)
