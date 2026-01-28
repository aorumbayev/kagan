"""Snapshot tests for Kagan TUI visual regression testing.

These tests capture the visual appearance of widgets and screens
to prevent unintended visual changes.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kagan.app import KaganApp
from kagan.database.models import (
    TicketCreate,
    TicketPriority,
    TicketStatus,
    TicketType,
    TicketUpdate,
)
from kagan.database.manager import StateManager


@pytest.fixture
def snapshot_app_factory():
    """Factory for creating apps with snapshot-compatible setup."""

    async def setup_db(db_path: Path, tickets: list[TicketCreate]) -> None:
        manager = StateManager(str(db_path))
        await manager.initialize()
        for ticket in tickets:
            await manager.create_ticket(ticket)
        await manager.close()

    def create_app(db_path: str) -> KaganApp:
        return KaganApp(db_path=db_path)

    return setup_db, create_app


class TestCardSnapshots:
    """Snapshot tests for TicketCard visual states."""

    def test_kanban_board_with_cards(self, snap_compare, tmp_path):
        """Snapshot test for the Kanban board with various card states."""
        import asyncio

        db_path = tmp_path / ".kagan" / "state.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        async def setup():
            manager = StateManager(str(db_path))
            await manager.initialize()

            # AUTO ticket (⚡ badge)
            await manager.create_ticket(
                TicketCreate(
                    title="Implement user auth",
                    description="Add JWT-based authentication",
                    priority=TicketPriority.HIGH,
                    status=TicketStatus.BACKLOG,
                    ticket_type=TicketType.AUTO,
                )
            )

            # PAIR ticket (👤 badge)
            await manager.create_ticket(
                TicketCreate(
                    title="Fix database connection",
                    description="Resolve timeout issues",
                    priority=TicketPriority.MEDIUM,
                    status=TicketStatus.BACKLOG,
                    ticket_type=TicketType.PAIR,
                )
            )

            # Low priority ticket
            await manager.create_ticket(
                TicketCreate(
                    title="Update docs",
                    description="Improve README",
                    priority=TicketPriority.LOW,
                    status=TicketStatus.BACKLOG,
                    ticket_type=TicketType.PAIR,
                )
            )

            # Long title that wraps
            await manager.create_ticket(
                TicketCreate(
                    title="This is a very long title that wraps",
                    description="Testing multi-line title wrapping",
                    priority=TicketPriority.MEDIUM,
                    status=TicketStatus.BACKLOG,
                    ticket_type=TicketType.AUTO,
                )
            )

            # In progress ticket
            await manager.create_ticket(
                TicketCreate(
                    title="Active work item",
                    description="Currently being worked on",
                    priority=TicketPriority.HIGH,
                    status=TicketStatus.IN_PROGRESS,
                    ticket_type=TicketType.AUTO,
                )
            )

            # Review ticket with summary
            review_ticket = await manager.create_ticket(
                TicketCreate(
                    title="Feature complete",
                    description="Ready for code review",
                    priority=TicketPriority.HIGH,
                    status=TicketStatus.REVIEW,
                    ticket_type=TicketType.AUTO,
                    review_summary="Added 3 new endpoints",
                    checks_passed=True,
                )
            )

            # Done ticket
            await manager.create_ticket(
                TicketCreate(
                    title="Completed task",
                    description="This work is finished",
                    priority=TicketPriority.MEDIUM,
                    status=TicketStatus.DONE,
                    ticket_type=TicketType.PAIR,
                )
            )

            await manager.close()

        asyncio.run(setup())
        app = KaganApp(db_path=str(db_path))
        assert snap_compare(app, terminal_size=(120, 40))


class TestPriorityIndicators:
    """Snapshot tests for priority visual indicators."""

    def test_priority_indicators_snapshot(self, snap_compare, tmp_path):
        """Snapshot test for priority indicator rendering."""
        import asyncio

        db_path = tmp_path / ".kagan" / "state.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        async def setup():
            manager = StateManager(str(db_path))
            await manager.initialize()

            # High priority (△)
            await manager.create_ticket(
                TicketCreate(
                    title="Urgent fix",
                    description="Critical bug fix",
                    priority=TicketPriority.HIGH,
                    status=TicketStatus.BACKLOG,
                )
            )

            # Medium priority (◇)
            await manager.create_ticket(
                TicketCreate(
                    title="Normal task",
                    description="Regular priority",
                    priority=TicketPriority.MEDIUM,
                    status=TicketStatus.BACKLOG,
                )
            )

            # Low priority (▽)
            await manager.create_ticket(
                TicketCreate(
                    title="Low priority",
                    description="Can wait",
                    priority=TicketPriority.LOW,
                    status=TicketStatus.BACKLOG,
                )
            )

            await manager.close()

        asyncio.run(setup())
        app = KaganApp(db_path=str(db_path))
        assert snap_compare(app, terminal_size=(120, 40))


class TestEmptyStateSnapshot:
    """Snapshot tests for empty state widgets."""

    def test_empty_board_snapshot(self, snap_compare):
        """Snapshot test for empty Kanban board."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / ".kagan" / "state.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)

            import asyncio

            async def setup():
                manager = StateManager(str(db_path))
                await manager.initialize()
                await manager.close()

            asyncio.run(setup())
            app = KaganApp(db_path=str(db_path))
            assert snap_compare(app, terminal_size=(120, 40))
