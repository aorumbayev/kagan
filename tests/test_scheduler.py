"""Tests for Scheduler class."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kagan.agents.scheduler import Scheduler
from kagan.config import AgentConfig, GeneralConfig, HatConfig, KaganConfig
from kagan.database.models import Ticket, TicketStatus


@pytest.fixture
def mock_state():
    m = MagicMock()
    m.get_all_tickets = AsyncMock(return_value=[])
    m.update_ticket = AsyncMock()
    m.get_scratchpad = AsyncMock(return_value="")
    m.update_scratchpad = AsyncMock()
    m.delete_scratchpad = AsyncMock()
    m.add_knowledge = AsyncMock()
    return m


@pytest.fixture
def mock_agents():
    m = MagicMock()
    m.get = MagicMock(return_value=None)
    m.list_active = MagicMock(return_value=[])
    m.spawn = AsyncMock()
    m.terminate = AsyncMock()
    return m


@pytest.fixture
def mock_worktrees():
    m = MagicMock()
    m.get_path = AsyncMock(return_value=None)
    m.create = AsyncMock(return_value=Path("/tmp/wt"))
    return m


@pytest.fixture
def config():
    return KaganConfig(
        general=GeneralConfig(auto_start=True, max_concurrent_agents=2),
        hats={"dev": HatConfig(agent_command="claude", args=["--model", "opus"])},
    )


@pytest.fixture
def review_config():
    """Config with agents for review loop tests."""
    return KaganConfig(
        general=GeneralConfig(auto_start=True, max_concurrent_agents=2),
        hats={"dev": HatConfig(agent_command="claude", args=["--model", "opus"])},
        agents={
            "claude": AgentConfig(
                identity="claude.com",
                name="Claude",
                short_name="claude",
                run_command={"*": "claude"},
                active=True,
            )
        },
    )


class TestScheduler:
    async def test_respects_auto_start_false(self, mock_state, mock_agents, mock_worktrees):
        """No agents spawned when auto_start=False."""
        config = KaganConfig(general=GeneralConfig(auto_start=False))
        ticket = Ticket(id="t3", title="Test", status=TicketStatus.IN_PROGRESS)
        mock_state.get_all_tickets.return_value = [ticket]

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)
        await scheduler.tick()

        # Verify no ticket loop was started (no spawn calls)
        mock_agents.spawn.assert_not_called()

    async def test_respects_max_concurrent(self, mock_state, mock_agents, mock_worktrees):
        """Respects max_concurrent_agents limit."""
        config = KaganConfig(general=GeneralConfig(auto_start=True, max_concurrent_agents=1))
        tickets = [
            Ticket(id="t1", title="Test1", status=TicketStatus.IN_PROGRESS),
            Ticket(id="t2", title="Test2", status=TicketStatus.IN_PROGRESS),
        ]
        mock_state.get_all_tickets.return_value = tickets

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)

        loop_calls = []

        async def tracking_loop(ticket):
            loop_calls.append(ticket.id)
            # Don't actually run the loop
            await asyncio.sleep(0.1)

        with patch.object(scheduler, "_run_ticket_loop", side_effect=tracking_loop):
            await scheduler.tick()
            await asyncio.sleep(0.05)
            # Only one ticket should start due to max_concurrent=1
            assert len(loop_calls) == 1

    async def test_starts_ticket_loop(self, mock_state, mock_agents, mock_worktrees, config):
        """Starts iterative loop for IN_PROGRESS ticket."""
        ticket = Ticket(id="t5", title="Feature", status=TicketStatus.IN_PROGRESS)
        mock_state.get_all_tickets.return_value = [ticket]

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)

        with patch.object(scheduler, "_run_ticket_loop", new_callable=AsyncMock) as mock_loop:
            await scheduler.tick()
            await asyncio.sleep(0.01)
            mock_loop.assert_called_once_with(ticket)

    async def test_get_iteration(self, mock_state, mock_agents, mock_worktrees, config):
        """Returns current iteration count for ticket."""
        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)
        # Simulate iteration tracking via a completed iteration
        scheduler._iteration_counts["t1"] = 3
        assert scheduler.get_iteration("t1") == 3
        assert scheduler.get_iteration("unknown") is None


class TestSchedulerStatusTransitions:
    """Tests for Scheduler status transition methods."""

    async def test_handle_complete_updates_to_review(
        self, mock_state, mock_agents, mock_worktrees, config
    ):
        """_handle_complete updates ticket status to REVIEW."""
        ticket = Ticket(id="t10", title="Complete me", status=TicketStatus.IN_PROGRESS)
        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)

        await scheduler._handle_complete(ticket)

        mock_state.update_ticket.assert_called_once()
        update = mock_state.update_ticket.call_args[0][1]
        assert update.status == TicketStatus.REVIEW

    async def test_handle_blocked_updates_to_backlog(
        self, mock_state, mock_agents, mock_worktrees, config
    ):
        """_handle_blocked updates ticket status to BACKLOG."""
        ticket = Ticket(id="t11", title="Block me", status=TicketStatus.IN_PROGRESS)
        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)

        await scheduler._handle_blocked(ticket)

        mock_state.update_ticket.assert_called_once()
        update = mock_state.update_ticket.call_args[0][1]
        assert update.status == TicketStatus.BACKLOG

    async def test_handle_max_iterations_updates_to_backlog(
        self, mock_state, mock_agents, mock_worktrees, config
    ):
        """_handle_max_iterations updates ticket status to BACKLOG."""
        ticket = Ticket(id="t12", title="Too many iterations", status=TicketStatus.IN_PROGRESS)
        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)

        await scheduler._handle_max_iterations(ticket)

        mock_state.update_ticket.assert_called_once()
        update = mock_state.update_ticket.call_args[0][1]
        assert update.status == TicketStatus.BACKLOG

    async def test_status_update_triggers_notification_callback(
        self, mock_state, mock_agents, mock_worktrees, config
    ):
        """Status updates trigger notification callback."""
        notifications = []

        scheduler = Scheduler(
            mock_state,
            mock_agents,
            mock_worktrees,
            config,
            on_ticket_changed=lambda: notifications.append(True),
        )

        await scheduler._update_ticket_status("t13", TicketStatus.REVIEW)

        mock_state.update_ticket.assert_called_once()
        assert len(notifications) == 1

    async def test_status_update_works_without_callback(
        self, mock_state, mock_agents, mock_worktrees, config
    ):
        """Status update works when no notification callback set."""
        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)

        await scheduler._update_ticket_status("t14", TicketStatus.DONE)

        mock_state.update_ticket.assert_called_once()


class TestSchedulerReviewLoop:
    """Tests for the _run_review_loop method."""

    async def test_review_no_worktree_returns_to_backlog(
        self, mock_state, mock_agents, mock_worktrees, config
    ):
        """Returns to BACKLOG when no worktree exists."""
        ticket = Ticket(id="r1", title="No worktree", status=TicketStatus.REVIEW)
        mock_worktrees.get_path.return_value = None

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)
        await scheduler._run_review_loop(ticket)

        mock_state.update_ticket.assert_called_once()
        update = mock_state.update_ticket.call_args[0][1]
        assert update.status == TicketStatus.BACKLOG

    async def test_review_no_commits_returns_to_backlog(
        self, mock_state, mock_agents, mock_worktrees, config
    ):
        """Returns to BACKLOG when no commits exist."""
        ticket = Ticket(id="r2", title="No commits", status=TicketStatus.REVIEW)
        mock_worktrees.get_path.return_value = Path("/tmp/wt")
        mock_worktrees.get_commit_log = AsyncMock(return_value=[])

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, config)
        await scheduler._run_review_loop(ticket)

        mock_state.update_ticket.assert_called_once()
        update = mock_state.update_ticket.call_args[0][1]
        assert update.status == TicketStatus.BACKLOG

    async def test_review_approved_merges_and_updates_to_done(
        self, mock_state, mock_agents, mock_worktrees, review_config
    ):
        """Approved review merges to main and updates ticket to DONE."""
        ticket = Ticket(id="r3", title="Approved", status=TicketStatus.REVIEW)
        mock_worktrees.get_path.return_value = Path("/tmp/wt")
        mock_worktrees.get_commit_log = AsyncMock(return_value=["abc123 Initial commit"])
        mock_worktrees.merge_to_main = AsyncMock(return_value=(True, "merged"))
        mock_worktrees.delete = AsyncMock()

        mock_agent = MagicMock()
        mock_agent.wait_ready = AsyncMock()
        mock_agent.send_prompt = AsyncMock()
        mock_agent.get_response_text = MagicMock(return_value='<approve summary="Done"/>')
        mock_agents.spawn.return_value = mock_agent

        mock_state.get_ticket = AsyncMock(return_value=ticket)

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, review_config)

        with patch.object(scheduler, "_get_changed_files", new_callable=AsyncMock) as mock_files:
            mock_files.return_value = ["src/main.py", "tests/test_main.py"]
            await scheduler._run_review_loop(ticket)

        # Find status update to DONE
        done_updates = [
            c
            for c in mock_state.update_ticket.call_args_list
            if c[0][1].status == TicketStatus.DONE
        ]
        assert len(done_updates) == 1
        mock_worktrees.delete.assert_called_once_with("r3", delete_branch=True)

    async def test_review_approved_merge_fails_returns_to_in_progress(
        self, mock_state, mock_agents, mock_worktrees, review_config
    ):
        """Approved review with merge failure returns to IN_PROGRESS."""
        ticket = Ticket(id="r4", title="Merge fail", status=TicketStatus.REVIEW)
        mock_worktrees.get_path.return_value = Path("/tmp/wt")
        mock_worktrees.get_commit_log = AsyncMock(return_value=["abc123 Commit"])
        mock_worktrees.merge_to_main = AsyncMock(return_value=(False, "conflict in main.py"))

        mock_agent = MagicMock()
        mock_agent.wait_ready = AsyncMock()
        mock_agent.send_prompt = AsyncMock()
        mock_agent.get_response_text = MagicMock(return_value="<approve/>")
        mock_agents.spawn.return_value = mock_agent

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, review_config)

        with patch.object(scheduler, "_get_changed_files", new_callable=AsyncMock) as mock_files:
            mock_files.return_value = ["src/main.py"]
            await scheduler._run_review_loop(ticket)

        # Verify status updated to IN_PROGRESS
        in_progress_updates = [
            c
            for c in mock_state.update_ticket.call_args_list
            if c[0][1].status == TicketStatus.IN_PROGRESS
        ]
        assert len(in_progress_updates) == 1

        # Verify scratchpad mentions merge failure
        mock_state.update_scratchpad.assert_called()
        scratchpad_content = mock_state.update_scratchpad.call_args[0][1]
        assert "Merge" in scratchpad_content or "conflict" in scratchpad_content

    async def test_review_rejected_returns_to_in_progress(
        self, mock_state, mock_agents, mock_worktrees, review_config
    ):
        """Rejected review returns to IN_PROGRESS with reason in scratchpad."""
        ticket = Ticket(id="r5", title="Rejected", status=TicketStatus.REVIEW)
        mock_worktrees.get_path.return_value = Path("/tmp/wt")
        mock_worktrees.get_commit_log = AsyncMock(return_value=["abc123 Commit"])

        mock_agent = MagicMock()
        mock_agent.wait_ready = AsyncMock()
        mock_agent.send_prompt = AsyncMock()
        mock_agent.get_response_text = MagicMock(return_value='<reject reason="needs tests"/>')
        mock_agents.spawn.return_value = mock_agent

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, review_config)

        with patch.object(scheduler, "_get_changed_files", new_callable=AsyncMock) as mock_files:
            mock_files.return_value = ["src/main.py"]
            await scheduler._run_review_loop(ticket)

        # Verify status updated to IN_PROGRESS
        in_progress_updates = [
            c
            for c in mock_state.update_ticket.call_args_list
            if c[0][1].status == TicketStatus.IN_PROGRESS
        ]
        assert len(in_progress_updates) == 1

        # Verify scratchpad contains rejection reason
        mock_state.update_scratchpad.assert_called()
        scratchpad_content = mock_state.update_scratchpad.call_args[0][1]
        assert "needs tests" in scratchpad_content

    async def test_review_timeout_returns_to_backlog(
        self, mock_state, mock_agents, mock_worktrees, review_config
    ):
        """Timeout during review returns to BACKLOG."""
        ticket = Ticket(id="r6", title="Timeout", status=TicketStatus.REVIEW)
        mock_worktrees.get_path.return_value = Path("/tmp/wt")
        mock_worktrees.get_commit_log = AsyncMock(return_value=["abc123 Commit"])

        mock_agent = MagicMock()
        mock_agent.wait_ready = AsyncMock(side_effect=TimeoutError("Agent timed out"))
        mock_agents.spawn.return_value = mock_agent

        scheduler = Scheduler(mock_state, mock_agents, mock_worktrees, review_config)

        with patch.object(scheduler, "_get_changed_files", new_callable=AsyncMock) as mock_files:
            mock_files.return_value = ["src/main.py"]
            await scheduler._run_review_loop(ticket)

        # Verify status updated to BACKLOG
        backlog_updates = [
            c
            for c in mock_state.update_ticket.call_args_list
            if c[0][1].status == TicketStatus.BACKLOG
        ]
        assert len(backlog_updates) == 1

        # Verify agent was terminated
        mock_agents.terminate.assert_called_with("r6-review")
