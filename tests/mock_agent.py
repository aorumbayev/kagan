"""Mock RPC Agent for E2E testing without spawning real agents."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

    from textual.message_pump import MessagePump

    from kagan.config import AgentConfig


@dataclass
class MockAgentBehavior:
    """Configurable behavior for mock agent responses."""

    # Map iteration number to signal
    signals: dict[int, Literal["complete", "continue", "blocked"]] = field(
        default_factory=lambda: {1: "complete"}
    )
    # Map iteration number to response text
    response_templates: dict[int, str] = field(
        default_factory=lambda: {1: "Task completed.\n<complete/>"}
    )
    response_delay: float = 0.05
    timeout_on_ready: bool = False
    fail_on_iteration: int | None = None


class MockAgent:
    """Mock ACP agent that simulates real agent behavior for testing."""

    def __init__(
        self,
        project_root: Path,
        agent_config: AgentConfig,
        behavior: MockAgentBehavior | None = None,
    ) -> None:
        self.project_root = project_root
        self._agent_config = agent_config
        self.behavior = behavior or MockAgentBehavior()
        self.session_id = "mock-session-001"
        self.tool_calls: dict[str, object] = {}
        self._message_target: MessagePump | None = None
        self._iteration = 0
        self._response_text: list[str] = []
        self._ready_event = asyncio.Event()
        self._done_event = asyncio.Event()

    @property
    def command(self) -> str:
        return "mock-agent"

    def set_message_target(self, target: MessagePump | None) -> None:
        self._message_target = target

    def start(self, message_target: MessagePump | None = None) -> None:
        """Start mock agent - sets ready immediately unless configured otherwise."""
        self._message_target = message_target
        if not self.behavior.timeout_on_ready:
            self._ready_event.set()

    async def wait_ready(self, timeout: float = 30.0) -> None:
        """Wait for ready (immediate for mock unless timeout configured)."""
        if self.behavior.timeout_on_ready:
            raise TimeoutError("Mock agent configured to timeout")
        async with asyncio.timeout(timeout):
            await self._ready_event.wait()

    async def send_prompt(self, prompt: str) -> str | None:
        """Process prompt and return configured response."""
        self._iteration += 1

        if self.behavior.fail_on_iteration == self._iteration:
            raise Exception(f"Mock agent failed on iteration {self._iteration}")

        await asyncio.sleep(self.behavior.response_delay)

        template = self.behavior.response_templates.get(
            self._iteration, f"Iteration {self._iteration} response\n<continue/>"
        )

        self._response_text.clear()
        self._response_text.append(template)
        return "end_turn"

    async def stop(self) -> None:
        """Stop the mock agent."""
        self._done_event.set()

    def get_response_text(self) -> str:
        return "".join(self._response_text)


class MockAgentManager:
    """Drop-in replacement for AgentManager that uses MockAgent."""

    def __init__(self, default_behavior: MockAgentBehavior | None = None) -> None:
        self._agents: dict[str, MockAgent] = {}
        self._default_behavior = default_behavior or MockAgentBehavior()
        self._behaviors: dict[str, MockAgentBehavior] = {}

    def set_behavior(self, ticket_id: str, behavior: MockAgentBehavior) -> None:
        """Configure specific behavior for a ticket's agent."""
        self._behaviors[ticket_id] = behavior

    async def spawn(
        self,
        ticket_id: str,
        agent_config: AgentConfig,
        project_root: Path,
        role: object = None,
        auto_approve: bool = False,
    ) -> MockAgent:
        if ticket_id in self._agents:
            raise ValueError(f"Agent already running for {ticket_id}")

        behavior = self._behaviors.get(ticket_id, self._default_behavior)
        agent = MockAgent(project_root, agent_config, behavior)
        agent.start()
        self._agents[ticket_id] = agent
        return agent

    def get(self, ticket_id: str) -> MockAgent | None:
        return self._agents.get(ticket_id)

    def is_running(self, ticket_id: str) -> bool:
        return ticket_id in self._agents

    def list_active(self, role: object = None) -> list[str]:
        return list(self._agents.keys())

    async def terminate(self, ticket_id: str) -> None:
        if agent := self._agents.pop(ticket_id, None):
            await agent.stop()

    async def terminate_all(self) -> None:
        for ticket_id in list(self._agents.keys()):
            await self.terminate(ticket_id)
