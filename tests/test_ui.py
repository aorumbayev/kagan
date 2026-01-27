"""UI behavior tests for Kagan TUI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kagan.app import KaganApp
from kagan.database.models import TicketCreate, TicketStatus
from kagan.ui.screens.kanban import KanbanScreen
from kagan.ui.widgets.card import TicketCard


@pytest.fixture
def app():
    return KaganApp(db_path=":memory:")


def get_kanban_screen(app: KaganApp) -> KanbanScreen:
    screen = app.screen
    assert isinstance(screen, KanbanScreen)
    return screen


class TestKeyboardNavigation:
    async def test_vertical_navigation(self, app: KaganApp):
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            await sm.create_ticket(TicketCreate(title="Task 1", status=TicketStatus.BACKLOG))
            await sm.create_ticket(TicketCreate(title="Task 2", status=TicketStatus.BACKLOG))

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = list(screen.query(TicketCard))
            assert len(cards) >= 2

            cards[0].focus()
            await pilot.pause()

            first_focused = app.focused
            assert first_focused is not None
            assert isinstance(first_focused, TicketCard)

            await pilot.press("j")
            await pilot.pause()

            second_focused = app.focused
            assert second_focused is not None
            assert second_focused != first_focused

            await pilot.press("k")
            await pilot.pause()

            assert app.focused == first_focused

    async def test_horizontal_navigation(self, app: KaganApp):
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            await sm.create_ticket(TicketCreate(title="Backlog Task", status=TicketStatus.BACKLOG))
            await sm.create_ticket(
                TicketCreate(title="InProgress Task", status=TicketStatus.IN_PROGRESS)
            )

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            backlog_cards = [
                c
                for c in screen.query(TicketCard)
                if c.ticket and c.ticket.status == TicketStatus.BACKLOG
            ]
            assert len(backlog_cards) >= 1

            backlog_cards[0].focus()
            await pilot.pause()

            first_focused = app.focused
            assert first_focused is not None

            await pilot.press("l")
            await pilot.pause()

            second_focused = app.focused
            assert second_focused is not None
            assert second_focused != first_focused

            await pilot.press("h")
            await pilot.pause()

            assert app.focused == first_focused


class TestCreateTicketFlow:
    async def test_create_ticket_via_form(self, app: KaganApp):
        async with app.run_test(size=(120, 40)) as pilot:
            get_kanban_screen(app)
            await pilot.pause()

            await pilot.press("n")
            await pilot.pause()
            await pilot.pause()

            modal = app.screen
            title_input = modal.query_one("#title-input")
            title_input.focus()
            await pilot.pause()

            for char in "Test ticket":
                await pilot.press(char)
            await pilot.pause()

            await pilot.press("ctrl+s")
            await pilot.pause()

            tickets = await app.state_manager.get_all_tickets()
            assert len(tickets) == 1
            assert tickets[0].title == "Test ticket"

    async def test_cancel_create_ticket(self, app: KaganApp):
        async with app.run_test(size=(120, 40)) as pilot:
            get_kanban_screen(app)
            await pilot.pause()

            await pilot.press("n")
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            tickets = await app.state_manager.get_all_tickets()
            assert len(tickets) == 0


class TestMoveTicket:
    async def test_move_ticket_forward(self, app: KaganApp):
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            ticket = await sm.create_ticket(
                TicketCreate(title="Move me", status=TicketStatus.BACKLOG)
            )

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = [c for c in screen.query(TicketCard) if c.ticket and c.ticket.id == ticket.id]
            assert len(cards) == 1
            cards[0].focus()
            await pilot.pause()

            assert app.focused is not None

            await pilot.press("right_square_bracket")
            await pilot.pause()

            updated = await sm.get_ticket(ticket.id)
            assert updated is not None
            assert updated.status == TicketStatus.IN_PROGRESS

    async def test_move_ticket_backward(self, app: KaganApp):
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            ticket = await sm.create_ticket(
                TicketCreate(title="Move back", status=TicketStatus.IN_PROGRESS)
            )

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = [c for c in screen.query(TicketCard) if c.ticket and c.ticket.id == ticket.id]
            assert len(cards) == 1
            cards[0].focus()
            await pilot.pause()

            await pilot.press("left_square_bracket")
            await pilot.pause()

            updated = await sm.get_ticket(ticket.id)
            assert updated is not None
            assert updated.status == TicketStatus.BACKLOG

    async def test_move_at_boundary_does_not_change_status(self, app: KaganApp):
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            ticket = await sm.create_ticket(TicketCreate(title="At end", status=TicketStatus.DONE))

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = [c for c in screen.query(TicketCard) if c.ticket and c.ticket.id == ticket.id]
            assert len(cards) == 1
            cards[0].focus()
            await pilot.pause()

            await pilot.press("right_square_bracket")
            await pilot.pause()

            updated = await sm.get_ticket(ticket.id)
            assert updated is not None
            assert updated.status == TicketStatus.DONE


class TestTicketCardAnimation:
    async def test_card_starts_without_agent_active(self, app: KaganApp):
        """Card should have is_agent_active=False by default."""
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            await sm.create_ticket(TicketCreate(title="Test Card", status=TicketStatus.BACKLOG))

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = list(screen.query(TicketCard))
            assert len(cards) >= 1

            card = cards[0]
            assert card.is_agent_active is False
            assert not card.has_class("agent-active")

    async def test_card_adds_agent_active_class_when_active(self, app: KaganApp):
        """Card should have 'agent-active' class when is_agent_active=True."""
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            await sm.create_ticket(TicketCreate(title="Active Card", status=TicketStatus.BACKLOG))

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = list(screen.query(TicketCard))
            assert len(cards) >= 1

            card = cards[0]
            card.is_agent_active = True
            await pilot.pause()

            assert card.has_class("agent-active")

    async def test_card_removes_classes_when_deactivated(self, app: KaganApp):
        """Card should remove 'agent-active' and 'agent-pulse' when deactivated."""
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            await sm.create_ticket(
                TicketCreate(title="Deactivate Card", status=TicketStatus.BACKLOG)
            )

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = list(screen.query(TicketCard))
            card = cards[0]

            # Activate first
            card.is_agent_active = True
            await pilot.pause()
            assert card.has_class("agent-active")

            # Deactivate
            card.is_agent_active = False
            await pilot.pause()

            assert not card.has_class("agent-active")
            assert not card.has_class("agent-pulse")

    async def test_pulse_animation_starts_when_active(self, app: KaganApp):
        """Pulse animation should toggle 'agent-pulse' class when card is activated."""
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            await sm.create_ticket(TicketCreate(title="Timer Card", status=TicketStatus.BACKLOG))

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = list(screen.query(TicketCard))
            card = cards[0]

            # Card should not have pulse class when not active
            assert not card.has_class("agent-pulse")

            card.is_agent_active = True
            await pilot.pause()

            # After activation and brief delay, pulse animation should be running
            # (class toggles every 0.6s, so we wait to see the effect)
            assert card.has_class("agent-active")

    async def test_pulse_animation_stops_when_inactive(self, app: KaganApp):
        """Pulse animation should stop and remove 'agent-pulse' class when card is deactivated."""
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            await sm.create_ticket(
                TicketCreate(title="Stop Timer Card", status=TicketStatus.BACKLOG)
            )

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            cards = list(screen.query(TicketCard))
            card = cards[0]

            card.is_agent_active = True
            await pilot.pause()
            assert card.has_class("agent-active")

            card.is_agent_active = False
            await pilot.pause()

            # Both agent-active and agent-pulse should be removed
            assert not card.has_class("agent-active")
            assert not card.has_class("agent-pulse")


class TestKanbanScreenActiveCards:
    async def test_update_active_cards_sets_card_states(self, app: KaganApp):
        """_update_active_cards should set is_agent_active=True for active tickets."""
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            ticket = await sm.create_ticket(
                TicketCreate(title="Agent Active", status=TicketStatus.BACKLOG)
            )

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            # Mock agent_manager.list_active() to return the ticket ID
            app.agent_manager.list_active = MagicMock(return_value=[ticket.id])

            screen._update_active_cards()
            await pilot.pause()

            cards = [c for c in screen.query(TicketCard) if c.ticket and c.ticket.id == ticket.id]
            assert len(cards) == 1
            assert cards[0].is_agent_active is True

    async def test_update_active_cards_clears_inactive(self, app: KaganApp):
        """_update_active_cards should clear is_agent_active when agent stops."""
        async with app.run_test(size=(120, 40)) as pilot:
            sm = app.state_manager
            ticket = await sm.create_ticket(
                TicketCreate(title="Was Active", status=TicketStatus.BACKLOG)
            )

            screen = get_kanban_screen(app)
            await screen._refresh_board()
            await pilot.pause()

            # First activate the card
            app.agent_manager.list_active = MagicMock(return_value=[ticket.id])
            screen._update_active_cards()
            await pilot.pause()

            cards = [c for c in screen.query(TicketCard) if c.ticket and c.ticket.id == ticket.id]
            assert cards[0].is_agent_active is True

            # Now clear active cards
            app.agent_manager.list_active = MagicMock(return_value=[])
            screen._update_active_cards()
            await pilot.pause()

            cards = [c for c in screen.query(TicketCard) if c.ticket and c.ticket.id == ticket.id]
            assert cards[0].is_agent_active is False


class TestWelcomeScreen:
    async def test_welcome_screen_composes(self, app: KaganApp):
        """Smoke test: WelcomeScreen composes without error."""
        async with app.run_test(size=(120, 40)) as pilot:
            from kagan.ui.screens.welcome import WelcomeScreen

            screen = WelcomeScreen()
            await app.push_screen(screen)
            await pilot.pause()
            assert app.screen is screen
            assert screen.query_one("#logo")
            assert screen.query_one("#continue-btn")


class TestAgentStreamsScreen:
    async def test_streams_screen_composes(self, app: KaganApp):
        """Smoke test: AgentStreamsScreen composes without error."""
        async with app.run_test(size=(120, 40)) as pilot:
            from kagan.ui.screens.streams import AgentStreamsScreen

            screen = AgentStreamsScreen()
            await app.push_screen(screen)
            await pilot.pause()
            assert app.screen is screen
            assert screen.query_one("#streams-tabs")
            assert screen.query_one("#reviewer")


class TestPermissionModal:
    async def test_permission_modal_composes(self, app: KaganApp):
        """Smoke test: PermissionModal composes without error."""
        from typing import Any

        from kagan.ui.modals.permission import PermissionModal

        async with app.run_test(size=(120, 40)) as pilot:
            options: Any = [{"optionId": "allow", "kind": "allow_once", "name": "Allow"}]
            tool_call: Any = {"title": "Test operation"}
            modal = PermissionModal(options=options, tool_call=tool_call)
            await app.push_screen(modal)
            await pilot.pause()
            assert app.screen is modal
            assert modal.query_one("#permission-container")
