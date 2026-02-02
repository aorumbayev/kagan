"""Unit tests for TicketCard review state functionality."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import Vertical

from kagan.database.models import Ticket, TicketPriority, TicketStatus, TicketType
from kagan.ui.widgets.card import TicketCard

pytestmark = pytest.mark.unit


def create_review_ticket(
    checks_passed: bool | None = None,
    title: str = "Review ticket",
    merge_failed: bool = False,
    merge_error: str | None = None,
) -> Ticket:
    """Create a ticket in REVIEW status with specified checks_passed value."""
    return Ticket.create(
        title=title,
        description="Test description",
        status=TicketStatus.REVIEW,
        priority=TicketPriority.MEDIUM,
        ticket_type=TicketType.PAIR,
        checks_passed=checks_passed,
        merge_failed=merge_failed,
        merge_error=merge_error,
    )


class CardTestApp(App):
    """Test app for TicketCard widget."""

    def compose(self) -> ComposeResult:
        yield Vertical(id="container")


# =============================================================================
# _get_review_badge() Tests
# =============================================================================


class TestGetReviewBadge:
    """Tests for _get_review_badge() method."""

    @pytest.mark.parametrize(
        ("checks_passed", "expected_badge"),
        [
            (True, "✓"),
            (False, "✗"),
            (None, "⏳"),
        ],
        ids=["passed", "failed", "pending"],
    )
    async def test_returns_correct_icon(self, checks_passed: bool | None, expected_badge: str):
        """Test _get_review_badge returns correct icon for each state."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket(checks_passed=checks_passed)
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            assert card._get_review_badge() == expected_badge

    async def test_returns_pending_when_ticket_is_none(self):
        """Test _get_review_badge returns pending icon when ticket is None."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket()
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            # Simulate ticket being None
            card.ticket = None
            assert card._get_review_badge() == "⏳"


# =============================================================================
# _format_checks_status() Tests
# =============================================================================


class TestFormatChecksStatus:
    """Tests for _format_checks_status() method."""

    @pytest.mark.parametrize(
        ("checks_passed", "expected_text"),
        [
            (True, "✓ Ready to merge"),
            (False, "✗ Needs revision"),
            (None, "⏳ Review pending"),
        ],
        ids=["passed", "failed", "pending"],
    )
    async def test_returns_semantic_text(self, checks_passed: bool | None, expected_text: str):
        """Test _format_checks_status returns correct semantic text for each state."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket(checks_passed=checks_passed)
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            assert card._format_checks_status() == expected_text

    async def test_returns_pending_when_ticket_is_none(self):
        """Test _format_checks_status returns pending text when ticket is None."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket()
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            card.ticket = None
            assert card._format_checks_status() == "⏳ Review pending"


# =============================================================================
# _update_review_state() Tests
# =============================================================================


class TestUpdateReviewState:
    """Tests for _update_review_state() method and CSS class application."""

    @pytest.mark.parametrize(
        ("checks_passed", "expected_state"),
        [
            (True, "-review-passed"),
            (False, "-review-failed"),
            (None, "-review-pending"),
        ],
        ids=["passed", "failed", "pending"],
    )
    async def test_sets_correct_review_state(self, checks_passed: bool | None, expected_state: str):
        """Test _update_review_state sets correct state for CSS class toggle."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket(checks_passed=checks_passed)
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            assert card.review_state == expected_state
            assert card.has_class(expected_state)

    async def test_clears_state_for_non_review_ticket(self):
        """Test _update_review_state clears state for non-REVIEW status tickets."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = Ticket.create(
                title="Backlog ticket",
                description="Test",
                status=TicketStatus.BACKLOG,
            )
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            assert card.review_state == ""
            assert not card.has_class("-review-passed")
            assert not card.has_class("-review-failed")
            assert not card.has_class("-review-pending")

    async def test_clears_state_when_ticket_is_none(self):
        """Test _update_review_state clears state when ticket is None."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket(checks_passed=True)
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            # Initially should have review-passed
            assert card.review_state == "-review-passed"

            # Set ticket to None and trigger update
            card.ticket = None
            await pilot.pause()

            assert card.review_state == ""


# =============================================================================
# watch_review_state() Tests
# =============================================================================


class TestWatchReviewState:
    """Tests for watch_review_state reactive watcher."""

    async def test_removes_old_class_adds_new_class(self):
        """Test watch_review_state removes old class and adds new class."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket(checks_passed=True)
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            assert card.has_class("-review-passed")
            assert not card.has_class("-review-failed")

            # Manually trigger state change (simulating ticket update)
            ticket.checks_passed = False
            card._update_review_state()
            await pilot.pause()

            assert not card.has_class("-review-passed")
            assert card.has_class("-review-failed")


# =============================================================================
# watch_ticket() Tests
# =============================================================================


class TestWatchTicket:
    """Tests for ticket watcher triggering review state update."""

    async def test_ticket_change_updates_review_state(self):
        """Test that changing ticket triggers _update_review_state."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket1 = create_review_ticket(checks_passed=True)
            card = TicketCard(ticket1)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            assert card.review_state == "-review-passed"

            # Change to a different ticket
            ticket2 = create_review_ticket(checks_passed=False)
            card.ticket = ticket2
            await pilot.pause()

            assert card.review_state == "-review-failed"


# =============================================================================
# Merge Failure State Tests
# =============================================================================


class TestMergeFailureState:
    """Tests for merge failure visual indicators."""

    async def test_merge_failed_shows_warning_badge(self):
        """Merge failure takes precedence over checks_passed for badge."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket(checks_passed=True, merge_failed=True)
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            assert card._get_review_badge() == "⚠"

    async def test_merge_failed_shows_error_message(self):
        """Status text includes merge error reason."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket(
                checks_passed=True,
                merge_failed=True,
                merge_error="uncommitted changes on base",
            )
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            status = card._format_checks_status()
            assert "Merge failed" in status
            assert "uncommitted" in status

    async def test_merge_failed_sets_correct_css_class(self):
        """Merge failure applies -review-merge-failed class."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            ticket = create_review_ticket(checks_passed=True, merge_failed=True)
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            assert card.review_state == "-review-merge-failed"
            assert card.has_class("-review-merge-failed")
            assert not card.has_class("-review-passed")

    async def test_merge_failed_takes_precedence_over_checks_passed(self):
        """Merge failure state supersedes review passed state."""
        app = CardTestApp()
        async with app.run_test() as pilot:
            # Even with checks_passed=True, merge_failed should dominate
            ticket = create_review_ticket(checks_passed=True, merge_failed=True)
            card = TicketCard(ticket)
            await app.query_one("#container").mount(card)
            await pilot.pause()

            # Badge shows warning, not checkmark
            assert card._get_review_badge() == "⚠"
            # CSS class is merge-failed, not passed
            assert card.review_state == "-review-merge-failed"
