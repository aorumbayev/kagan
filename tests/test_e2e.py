"""End-to-end tests using mock agents."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from kagan.agents.scheduler import Scheduler
from kagan.config import AgentConfig, GeneralConfig, KaganConfig
from kagan.database.models import Ticket, TicketStatus
from tests.mock_agent import MockAgent, MockAgentBehavior, MockAgentManager


class TestMockAgentIntegration:
    """Test that MockAgent correctly simulates real agent behavior."""

    async def test_mock_agent_completes_immediately(self):
        """Agent with default behavior completes on first iteration."""
        agent_config = AgentConfig(
            identity="test",
            name="Test",
            short_name="test",
            run_command={"*": "test"},
        )
        agent = MockAgent(Path("/tmp"), agent_config)
        agent.start()

        await agent.wait_ready()
        result = await agent.send_prompt("Do the task")

        assert result == "end_turn"
        assert "<complete/>" in agent.get_response_text()

    async def test_mock_agent_multi_iteration(self, multi_iteration_behavior):
        """Agent configured for multiple iterations."""
        agent_config = AgentConfig(
            identity="test",
            name="Test",
            short_name="test",
            run_command={"*": "test"},
        )
        agent = MockAgent(Path("/tmp"), agent_config, multi_iteration_behavior)
        agent.start()
        await agent.wait_ready()

        # Iteration 1: continue
        await agent.send_prompt("Start")
        assert "<continue/>" in agent.get_response_text()

        # Iteration 2: continue
        await agent.send_prompt("Continue")
        assert "<continue/>" in agent.get_response_text()

        # Iteration 3: complete
        await agent.send_prompt("Finish")
        assert "<complete/>" in agent.get_response_text()

    async def test_mock_agent_blocked(self, blocked_behavior):
        """Agent configured to get blocked."""
        agent_config = AgentConfig(
            identity="test",
            name="Test",
            short_name="test",
            run_command={"*": "test"},
        )
        agent = MockAgent(Path("/tmp"), agent_config, blocked_behavior)
        agent.start()
        await agent.wait_ready()

        await agent.send_prompt("Do something")
        response = agent.get_response_text()

        assert "<blocked" in response
        assert "missing config" in response

    async def test_mock_agent_timeout(self):
        """Agent configured to timeout on ready."""
        behavior = MockAgentBehavior(timeout_on_ready=True)
        agent_config = AgentConfig(
            identity="test",
            name="Test",
            short_name="test",
            run_command={"*": "test"},
        )
        agent = MockAgent(Path("/tmp"), agent_config, behavior)
        agent.start()

        with pytest.raises(TimeoutError):
            await agent.wait_ready()


class TestMockAgentManager:
    """Test MockAgentManager as drop-in replacement."""

    async def test_spawn_and_get(self):
        """Manager spawns and retrieves agents."""
        manager = MockAgentManager()
        agent_config = AgentConfig(
            identity="test",
            name="Test",
            short_name="test",
            run_command={"*": "test"},
        )

        agent = await manager.spawn("ticket-1", agent_config, Path("/tmp"))

        assert manager.get("ticket-1") is agent
        assert manager.is_running("ticket-1")
        assert "ticket-1" in manager.list_active()

    async def test_terminate(self):
        """Manager terminates agents."""
        manager = MockAgentManager()
        agent_config = AgentConfig(
            identity="test",
            name="Test",
            short_name="test",
            run_command={"*": "test"},
        )

        await manager.spawn("ticket-1", agent_config, Path("/tmp"))
        await manager.terminate("ticket-1")

        assert manager.get("ticket-1") is None
        assert not manager.is_running("ticket-1")

    async def test_custom_behavior_per_ticket(self):
        """Different behaviors for different tickets."""
        manager = MockAgentManager()
        blocked = MockAgentBehavior(
            signals={1: "blocked"},
            response_templates={1: "<blocked/>"},
        )
        manager.set_behavior("ticket-blocked", blocked)

        agent_config = AgentConfig(
            identity="test",
            name="Test",
            short_name="test",
            run_command={"*": "test"},
        )

        # Default behavior - completes
        agent1 = await manager.spawn("ticket-ok", agent_config, Path("/tmp"))
        await agent1.send_prompt("test")
        assert "<complete/>" in agent1.get_response_text()

        # Custom blocked behavior
        agent2 = await manager.spawn("ticket-blocked", agent_config, Path("/tmp"))
        await agent2.send_prompt("test")
        assert "<blocked/>" in agent2.get_response_text()


class TestSchedulerWithMockAgent:
    """Test Scheduler integration with MockAgentManager."""

    @pytest.fixture
    def mock_state(self):
        m = MagicMock()
        m.get_all_tickets = AsyncMock(return_value=[])
        m.update_ticket = AsyncMock()
        m.get_scratchpad = AsyncMock(return_value="")
        m.update_scratchpad = AsyncMock()
        m.delete_scratchpad = AsyncMock()
        return m

    @pytest.fixture
    def mock_worktrees(self):
        m = MagicMock()
        m.get_path = AsyncMock(return_value=Path("/tmp/worktree"))
        m.create = AsyncMock(return_value=Path("/tmp/worktree"))
        m.get_branch = AsyncMock(return_value="feat/test-branch")
        m.has_commits = AsyncMock(return_value=False)
        return m

    @pytest.fixture
    def config(self):
        return KaganConfig(
            general=GeneralConfig(
                auto_start=True,
                max_concurrent_agents=2,
                max_iterations=3,
            ),
            agents={
                "test": AgentConfig(
                    identity="test",
                    name="Test",
                    short_name="test",
                    run_command={"*": "test"},
                    active=True,
                )
            },
        )

    async def test_scheduler_with_mock_agent_complete(self, mock_state, mock_worktrees, config):
        """Scheduler moves ticket to REVIEW when agent completes."""
        ticket = Ticket(id="t1", title="Test", status=TicketStatus.IN_PROGRESS)
        mock_state.get_all_tickets.return_value = [ticket]

        # Use mock agent manager with quick complete behavior
        mock_agents = MockAgentManager(
            default_behavior=MockAgentBehavior(
                signals={1: "complete"},
                response_templates={1: "Done!\n<complete/>"},
                response_delay=0.01,
            )
        )

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)

        # Run one tick - should start the ticket loop
        await scheduler.tick()

        # Wait for the async task to complete
        await asyncio.sleep(0.2)

        # Verify ticket was updated to REVIEW
        mock_state.update_ticket.assert_called()
        calls = mock_state.update_ticket.call_args_list
        # Find the status update call
        status_updates = [
            c for c in calls if hasattr(c[0][1], "status") and c[0][1].status is not None
        ]
        assert len(status_updates) > 0
        last_update = status_updates[-1]
        assert last_update[0][1].status == TicketStatus.REVIEW

    async def test_notification_callback_called(self, mock_state, mock_worktrees, config):
        """Scheduler calls notification callback on status change."""
        ticket = Ticket(id="t1", title="Test", status=TicketStatus.IN_PROGRESS)
        mock_state.get_all_tickets.return_value = [ticket]

        mock_agents = MockAgentManager(
            default_behavior=MockAgentBehavior(
                signals={1: "complete"},
                response_templates={1: "Done!\n<complete/>"},
                response_delay=0.01,
            )
        )

        callback = MagicMock()
        scheduler = Scheduler(
            mock_state, mock_agents, mock_worktrees, config, on_ticket_changed=callback
        )

        await scheduler.tick()
        await asyncio.sleep(0.2)

        callback.assert_called()


class TestUIWithMockAgent:
    """Test UI interactions with mock agent system."""

    async def test_card_agent_active_state(self):
        """TicketCard correctly reflects agent active state."""
        from kagan.database.models import Ticket, TicketStatus
        from kagan.ui.widgets.card import TicketCard

        ticket = Ticket(id="t1", title="Test", status=TicketStatus.IN_PROGRESS)
        card = TicketCard(ticket)

        # Initially not active
        assert card.is_agent_active is False

        # Set to active
        card.is_agent_active = True
        assert card.is_agent_active is True
        assert "agent-active" in card.classes

        # Set to inactive
        card.is_agent_active = False
        assert card.is_agent_active is False
        assert "agent-active" not in card.classes
