"""Tests for auto-merge functionality with agent-based review."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from kagan.agents.scheduler import Scheduler
from kagan.database.models import Ticket, TicketStatus, TicketType

if TYPE_CHECKING:
    from kagan.database.manager import StateManager

pytestmark = pytest.mark.integration


def _create_review_agent(response: str) -> MagicMock:
    """Create a mock review agent with specified response."""
    agent = MagicMock()
    agent.set_auto_approve = MagicMock()
    agent.start = MagicMock()
    agent.wait_ready = AsyncMock()
    agent.send_prompt = AsyncMock()
    agent.get_response_text = MagicMock(return_value=response)
    agent.stop = AsyncMock()
    return agent


@pytest.fixture
def auto_merge_scheduler(
    state_manager, mock_worktree_manager, auto_merge_config, mock_session_manager, mocker
):
    """Create a scheduler with auto_merge enabled."""
    mock_worktree_manager.get_commit_log = mocker.AsyncMock(return_value=["feat: add feature"])
    mock_worktree_manager.get_diff_stats = mocker.AsyncMock(return_value="1 file changed")
    return Scheduler(
        state_manager=state_manager,
        worktree_manager=mock_worktree_manager,
        config=auto_merge_config,
        session_manager=mock_session_manager,
        on_ticket_changed=mocker.MagicMock(),
    )


async def _create_auto_ticket(state_manager: StateManager) -> Ticket:
    """Create a standard AUTO ticket in IN_PROGRESS status."""
    return await state_manager.create_ticket(
        Ticket.create(
            title="Auto ticket",
            ticket_type=TicketType.AUTO,
            status=TicketStatus.IN_PROGRESS,
        )
    )


class TestAutoMerge:
    """Tests for auto-merge functionality with agent-based review."""

    async def test_auto_merge_when_review_approved(
        self,
        auto_merge_scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
        mock_session_manager,
        mock_review_agent,
        mocker,
    ):
        """Test auto-merge happens when auto_merge=true and review is approved."""
        ticket = await _create_auto_ticket(state_manager)

        mock_worktree_manager.merge_to_main = mocker.AsyncMock(return_value=(True, "Merged"))
        mock_worktree_manager.delete = mocker.AsyncMock()
        mocker.patch("kagan.agents.scheduler.Agent", return_value=mock_review_agent)

        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        await auto_merge_scheduler._handle_complete(full_ticket)

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.DONE
        assert updated.checks_passed is True
        assert updated.review_summary == "Implementation complete"

        mock_worktree_manager.merge_to_main.assert_called_once()
        mock_worktree_manager.delete.assert_called_once()
        mock_session_manager.kill_session.assert_called_once_with(ticket.id)

    async def test_no_auto_merge_when_disabled(
        self,
        scheduler,  # Uses default config (auto_merge=false)
        state_manager: StateManager,
        mock_worktree_manager,
        mocker,
    ):
        """Test no auto-merge when auto_merge=false."""
        ticket = await _create_auto_ticket(state_manager)

        mock_worktree_manager.get_commit_log = mocker.AsyncMock(return_value=["feat: add feature"])
        mock_worktree_manager.get_diff_stats = mocker.AsyncMock(return_value="1 file changed")
        mocker.patch(
            "kagan.agents.scheduler.Agent",
            return_value=_create_review_agent('<approve summary="Done"/>'),
        )

        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        await scheduler._handle_complete(full_ticket)

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.REVIEW
        assert updated.checks_passed is True
        mock_worktree_manager.merge_to_main.assert_not_called()

    @pytest.mark.parametrize(
        "response,expected_passed,expected_summary_contains",
        [
            ('<reject reason="No unit tests added"/>', False, "No unit tests added"),
            ("The code looks fine but I need more context.", False, "No review signal found"),
        ],
        ids=["rejected", "no_signal"],
    )
    async def test_no_auto_merge_on_review_issues(
        self,
        auto_merge_scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
        mocker,
        response,
        expected_passed,
        expected_summary_contains,
    ):
        """Test no auto-merge when review is rejected or has no signal."""
        ticket = await _create_auto_ticket(state_manager)

        mocker.patch("kagan.agents.scheduler.Agent", return_value=_create_review_agent(response))

        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        await auto_merge_scheduler._handle_complete(full_ticket)

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.REVIEW
        assert updated.checks_passed is expected_passed
        assert expected_summary_contains in (updated.review_summary or "")
        mock_worktree_manager.merge_to_main.assert_not_called()


class TestAutoMergeEdgeCases:
    """Edge cases for auto-merge functionality."""

    async def test_stays_in_review_when_merge_fails_non_conflict(
        self,
        auto_merge_scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
        mock_review_agent,
        mocker,
    ):
        """Test ticket stays in REVIEW if merge fails with non-conflict error."""
        ticket = await _create_auto_ticket(state_manager)

        # Non-conflict error should NOT trigger auto-retry
        mock_worktree_manager.merge_to_main = mocker.AsyncMock(
            return_value=(False, "Uncommitted changes on base branch")
        )
        mocker.patch("kagan.agents.scheduler.Agent", return_value=mock_review_agent)

        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        await auto_merge_scheduler._handle_complete(full_ticket)

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.REVIEW
        assert updated.merge_failed is True
        mock_worktree_manager.delete.assert_not_called()

    async def test_retries_on_merge_conflict_when_enabled(
        self,
        auto_merge_scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
        mock_review_agent,
        mocker,
    ):
        """Test ticket retries (goes back to IN_PROGRESS) on merge conflict."""
        ticket = await _create_auto_ticket(state_manager)

        # Merge conflict should trigger auto-retry
        mock_worktree_manager.merge_to_main = mocker.AsyncMock(
            return_value=(False, "Merge conflict detected")
        )
        # Mock the rebase and related methods
        mock_worktree_manager.rebase_onto_base = mocker.AsyncMock(
            return_value=(False, "Rebase conflict", ["src/file.py"])
        )
        mock_worktree_manager.get_files_changed_on_base = mocker.AsyncMock(
            return_value=["src/other.py"]
        )
        mocker.patch("kagan.agents.scheduler.Agent", return_value=mock_review_agent)

        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        await auto_merge_scheduler._handle_complete(full_ticket)

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        # Ticket should be back in IN_PROGRESS for retry
        assert updated.status == TicketStatus.IN_PROGRESS
        # Merge state should be cleared for retry
        assert updated.merge_failed is False
        assert updated.merge_error is None
        assert updated.checks_passed is None
        mock_worktree_manager.delete.assert_not_called()

    async def test_no_retry_when_auto_retry_disabled(
        self,
        state_manager: StateManager,
        mock_worktree_manager,
        mock_review_agent,
        mock_session_manager,
        mocker,
    ):
        """Test no retry when auto_retry_on_merge_conflict is disabled."""
        from kagan.config import AgentConfig, GeneralConfig, KaganConfig

        # Create config with auto_merge=True but auto_retry_on_merge_conflict=False
        config = KaganConfig(
            general=GeneralConfig(
                auto_start=True,
                auto_merge=True,
                auto_retry_on_merge_conflict=False,
                max_concurrent_agents=2,
                max_iterations=3,
                iteration_delay_seconds=0.01,
                default_worker_agent="test",
                default_base_branch="main",
            ),
            agents={
                "test": AgentConfig(
                    identity="test.agent",
                    name="Test Agent",
                    short_name="test",
                    run_command={"*": "echo test"},
                )
            },
        )

        mock_worktree_manager.get_commit_log = mocker.AsyncMock(return_value=["feat: add feature"])
        mock_worktree_manager.get_diff_stats = mocker.AsyncMock(return_value="1 file changed")

        scheduler = Scheduler(
            state_manager=state_manager,
            worktree_manager=mock_worktree_manager,
            config=config,
            session_manager=mock_session_manager,
            on_ticket_changed=mocker.MagicMock(),
        )

        ticket = await _create_auto_ticket(state_manager)

        # Conflict error but auto-retry disabled
        mock_worktree_manager.merge_to_main = mocker.AsyncMock(
            return_value=(False, "Merge conflict detected")
        )
        mocker.patch("kagan.agents.scheduler.Agent", return_value=mock_review_agent)

        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        await scheduler._handle_complete(full_ticket)

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        # Should stay in REVIEW since auto-retry is disabled
        assert updated.status == TicketStatus.REVIEW
        assert updated.merge_failed is True
        mock_worktree_manager.delete.assert_not_called()

    @pytest.mark.parametrize(
        "response,expected_passed,expected_summary",
        [
            ('<approve summary="All good"/>', True, "All good"),
            ('<reject reason="Needs work"/>', False, "Needs work"),
        ],
        ids=["approve", "reject"],
    )
    async def test_run_review_helper(
        self,
        auto_merge_scheduler,
        state_manager: StateManager,
        mocker,
        response,
        expected_passed,
        expected_summary,
    ):
        """Test _run_review helper method parses signals correctly."""
        from pathlib import Path

        ticket = await state_manager.create_ticket(
            Ticket.create(title="Test ticket", ticket_type=TicketType.AUTO, description="Test")
        )
        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        wt_path = Path("/tmp/test-worktree")

        mocker.patch("kagan.agents.scheduler.Agent", return_value=_create_review_agent(response))

        passed, summary = await auto_merge_scheduler._run_review(full_ticket, wt_path)
        assert passed is expected_passed
        assert summary == expected_summary


class TestMergeLockSerialization:
    """Tests for merge lock preventing concurrent merge race conditions."""

    async def test_concurrent_merges_are_serialized(
        self,
        auto_merge_scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
        mock_review_agent,
        mocker,
    ):
        """Concurrent _auto_merge calls should be serialized by the lock.

        When two tickets complete around the same time, they should merge
        one at a time, not interleave operations.
        """
        import asyncio

        # Create two tickets
        ticket1 = await state_manager.create_ticket(
            Ticket.create(
                title="Ticket 1",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )
        ticket2 = await state_manager.create_ticket(
            Ticket.create(
                title="Ticket 2",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Track the order of merge operations
        merge_order: list[str] = []
        merge_started: dict[str, asyncio.Event] = {
            ticket1.id: asyncio.Event(),
            ticket2.id: asyncio.Event(),
        }
        merge_completed: dict[str, asyncio.Event] = {
            ticket1.id: asyncio.Event(),
            ticket2.id: asyncio.Event(),
        }

        async def tracking_merge(ticket_id: str, **kwargs):
            """Track merge start/end to verify serialization."""
            merge_order.append(f"start:{ticket_id}")
            merge_started[ticket_id].set()
            # Simulate some async work
            await asyncio.sleep(0.05)
            merge_order.append(f"end:{ticket_id}")
            merge_completed[ticket_id].set()
            return (True, "Merged")

        mock_worktree_manager.merge_to_main = mocker.AsyncMock(side_effect=tracking_merge)
        mock_worktree_manager.delete = mocker.AsyncMock()
        mocker.patch("kagan.agents.scheduler.Agent", return_value=mock_review_agent)

        full_ticket1 = await state_manager.get_ticket(ticket1.id)
        full_ticket2 = await state_manager.get_ticket(ticket2.id)

        # Start both merges concurrently
        task1 = asyncio.create_task(auto_merge_scheduler._handle_complete(full_ticket1))
        task2 = asyncio.create_task(auto_merge_scheduler._handle_complete(full_ticket2))

        await asyncio.gather(task1, task2)

        # Verify serialization: should be start1, end1, start2, end2 OR start2, end2, start1, end1
        # NOT start1, start2, end1, end2 (interleaved)
        assert len(merge_order) == 4, f"Expected 4 events, got: {merge_order}"

        # Check that each merge completes before the next starts
        # The pattern should be: start_X, end_X, start_Y, end_Y
        # which means merge_order[0] starts with "start:" and merge_order[1] starts with "end:"
        # and they should be for the same ticket
        first_ticket = merge_order[0].split(":")[1]
        second_ticket = merge_order[2].split(":")[1]

        assert merge_order[0] == f"start:{first_ticket}"
        assert merge_order[1] == f"end:{first_ticket}"
        assert merge_order[2] == f"start:{second_ticket}"
        assert merge_order[3] == f"end:{second_ticket}"
        assert first_ticket != second_ticket


class TestMergeFailureTracking:
    """Tests for merge failure state persistence."""

    async def test_merge_failure_sets_ticket_state(
        self,
        auto_merge_scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
        mock_review_agent,
        mocker,
    ):
        """Merge failure persists error state on ticket."""
        ticket = await _create_auto_ticket(state_manager)

        mock_worktree_manager.merge_to_main = mocker.AsyncMock(
            return_value=(False, "uncommitted changes on base")
        )
        mocker.patch("kagan.agents.scheduler.Agent", return_value=mock_review_agent)

        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        await auto_merge_scheduler._handle_complete(full_ticket)

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.merge_failed is True
        assert "uncommitted" in (updated.merge_error or "")

    async def test_spawn_resets_review_state(
        self,
        auto_merge_scheduler,
        state_manager: StateManager,
        mocker,
    ):
        """Spawning agent clears previous review and merge state."""
        # Create ticket with stale review state
        ticket = await state_manager.create_ticket(
            Ticket.create(
                title="Retry ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
                checks_passed=False,
                review_summary="Old review",
                merge_failed=True,
                merge_error="Old error",
            )
        )

        # Mock the actual spawn process to avoid full agent creation
        mocker.patch.object(auto_merge_scheduler, "_run_ticket_loop", new_callable=AsyncMock)

        await auto_merge_scheduler._spawn(ticket)

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.checks_passed is None
        assert updated.review_summary is None
        assert updated.merge_failed is False
        assert updated.merge_error is None
