"""E2E tests for review UX improvements.

Tests for visual indicators on REVIEW tickets:
- Border colors based on checks_passed state
- Review badge and semantic text display
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from kagan.app import KaganApp
from kagan.database.manager import StateManager
from kagan.database.models import Ticket, TicketPriority, TicketStatus, TicketType
from kagan.ui.widgets.card import TicketCard
from tests.helpers.git import init_git_repo_with_commit

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e


# =============================================================================
# Fixtures
# =============================================================================


async def _create_e2e_project(tmp_path: Path) -> SimpleNamespace:
    """Create a project with git repo and kagan config."""
    project = tmp_path / "test_project"
    project.mkdir()

    await init_git_repo_with_commit(project)

    kagan_dir = project / ".kagan"
    kagan_dir.mkdir()

    config_content = """# Kagan Test Configuration
[general]
auto_start = false
auto_merge = false
default_base_branch = "main"
default_worker_agent = "claude"

[agents.claude]
identity = "claude.ai"
name = "Claude"
short_name = "claude"
run_command."*" = "echo mock-claude"
interactive_command."*" = "echo mock-claude-interactive"
active = true
"""
    (kagan_dir / "config.toml").write_text(config_content)

    return SimpleNamespace(
        root=project,
        db=str(kagan_dir / "state.db"),
        config=str(kagan_dir / "config.toml"),
        kagan_dir=kagan_dir,
    )


async def _create_app_with_review_ticket(
    e2e_project: SimpleNamespace,
    checks_passed: bool | None,
    merge_failed: bool = False,
    merge_error: str | None = None,
) -> KaganApp:
    """Create a KaganApp with a REVIEW ticket having specified checks_passed."""
    manager = StateManager(e2e_project.db)
    await manager.initialize()
    ticket = Ticket.create(
        title="Review test ticket",
        description="Testing review state",
        priority=TicketPriority.MEDIUM,
        status=TicketStatus.REVIEW,
        ticket_type=TicketType.PAIR,
        checks_passed=checks_passed,
        review_summary="Test review summary",
        merge_failed=merge_failed,
        merge_error=merge_error,
    )
    await manager.create_ticket(ticket)
    await manager.close()
    return KaganApp(db_path=e2e_project.db, config_path=e2e_project.config, lock_path=None)


@pytest.fixture
async def e2e_project_review(tmp_path: Path) -> SimpleNamespace:
    """Create an E2E project for review tests."""
    return await _create_e2e_project(tmp_path)


# =============================================================================
# Review State CSS Class Tests
# =============================================================================


class TestReviewStateCssClasses:
    """Tests for CSS classes applied based on review state."""

    @pytest.mark.parametrize(
        ("checks_passed", "expected_class"),
        [
            (True, "-review-passed"),
            (False, "-review-failed"),
            (None, "-review-pending"),
        ],
        ids=["passed", "failed", "pending"],
    )
    async def test_review_ticket_has_correct_css_class(
        self,
        e2e_project_review: SimpleNamespace,
        checks_passed: bool | None,
        expected_class: str,
    ):
        """Test that REVIEW ticket card has correct CSS class based on checks_passed."""
        app = await _create_app_with_review_ticket(e2e_project_review, checks_passed)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            cards = list(pilot.app.screen.query(TicketCard))
            assert len(cards) == 1

            card = cards[0]
            assert card.has_class(expected_class)

    async def test_passed_ticket_does_not_have_failed_or_pending_class(
        self,
        e2e_project_review: SimpleNamespace,
    ):
        """Test passed ticket doesn't have failed or pending classes."""
        app = await _create_app_with_review_ticket(e2e_project_review, checks_passed=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            card = pilot.app.screen.query_one(TicketCard)
            assert card.has_class("-review-passed")
            assert not card.has_class("-review-failed")
            assert not card.has_class("-review-pending")


# =============================================================================
# Review Badge and Semantic Text Display Tests
# =============================================================================


class TestReviewBadgeDisplay:
    """Tests for review badge and semantic text in card display."""

    @pytest.mark.parametrize(
        ("checks_passed", "expected_badge", "expected_status_text"),
        [
            (True, "✓", "✓ Ready to merge"),
            (False, "✗", "✗ Needs revision"),
            (None, "⏳", "⏳ Review pending"),
        ],
        ids=["passed", "failed", "pending"],
    )
    async def test_card_displays_review_badge_and_status(
        self,
        e2e_project_review: SimpleNamespace,
        checks_passed: bool | None,
        expected_badge: str,
        expected_status_text: str,
    ):
        """Test card displays correct review badge and semantic status text."""
        app = await _create_app_with_review_ticket(e2e_project_review, checks_passed)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            card = pilot.app.screen.query_one(TicketCard)

            # Verify badge method returns expected value
            assert card._get_review_badge() == expected_badge

            # Verify semantic status text
            assert card._format_checks_status() == expected_status_text

    async def test_card_shows_review_summary(self, e2e_project_review: SimpleNamespace):
        """Test card displays review summary for REVIEW tickets."""
        app = await _create_app_with_review_ticket(e2e_project_review, checks_passed=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            card = pilot.app.screen.query_one(TicketCard)
            assert card.ticket is not None
            assert card.ticket.review_summary == "Test review summary"

            # Verify card-review label exists in composed children
            review_labels = card.query(".card-review")
            assert len(review_labels) == 1

            # Verify card-checks label exists
            checks_labels = card.query(".card-checks")
            assert len(checks_labels) == 1


# =============================================================================
# Non-Review Ticket Tests
# =============================================================================


class TestNonReviewTickets:
    """Tests verifying non-REVIEW tickets don't have review classes."""

    async def test_backlog_ticket_has_no_review_class(self, e2e_project_review: SimpleNamespace):
        """Test BACKLOG ticket doesn't have review CSS classes."""
        manager = StateManager(e2e_project_review.db)
        await manager.initialize()
        ticket = Ticket.create(
            title="Backlog ticket",
            description="Not in review",
            status=TicketStatus.BACKLOG,
        )
        await manager.create_ticket(ticket)
        await manager.close()

        app = KaganApp(
            db_path=e2e_project_review.db,
            config_path=e2e_project_review.config,
            lock_path=None,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            card = pilot.app.screen.query_one(TicketCard)
            assert not card.has_class("-review-passed")
            assert not card.has_class("-review-failed")
            assert not card.has_class("-review-pending")
            assert card.review_state == ""


# =============================================================================
# Merge Failure E2E Tests
# =============================================================================


class TestMergeFailureDisplay:
    """E2E tests for merge failure visual indicators."""

    async def test_merge_failed_ticket_has_correct_css_class(
        self, e2e_project_review: SimpleNamespace
    ):
        """Merge failure applies distinct CSS class for styling."""
        app = await _create_app_with_review_ticket(
            e2e_project_review,
            checks_passed=True,
            merge_failed=True,
            merge_error="uncommitted changes",
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            card = pilot.app.screen.query_one(TicketCard)
            assert card.has_class("-review-merge-failed")
            assert not card.has_class("-review-passed")

    async def test_merge_failed_shows_warning_badge(self, e2e_project_review: SimpleNamespace):
        """Merge failure displays warning badge instead of checkmark."""
        app = await _create_app_with_review_ticket(
            e2e_project_review,
            checks_passed=True,
            merge_failed=True,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            card = pilot.app.screen.query_one(TicketCard)
            assert card._get_review_badge() == "⚠"

    async def test_merge_failed_status_includes_error(self, e2e_project_review: SimpleNamespace):
        """Status text shows merge failure reason."""
        app = await _create_app_with_review_ticket(
            e2e_project_review,
            checks_passed=True,
            merge_failed=True,
            merge_error="conflict with main",
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            card = pilot.app.screen.query_one(TicketCard)
            status = card._format_checks_status()
            assert "Merge failed" in status
            assert "conflict" in status
