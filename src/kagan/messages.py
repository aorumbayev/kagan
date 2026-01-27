"""Centralized message definitions for Kagan TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.message import Message

if TYPE_CHECKING:
    from kagan.database.models import Ticket, TicketStatus


@dataclass
class TicketChanged(Message):
    """Posted when a ticket status changes, to trigger UI refresh.

    This message does NOT bubble - it's handled only by the current screen.
    The app callback posts this message, so if it bubbled back to the app,
    it would create an infinite loop.
    """

    bubble = False


@dataclass
class TicketSelected(Message):
    """Posted when a ticket card is selected/clicked."""

    ticket: Ticket


@dataclass
class TicketMoveRequested(Message):
    """Posted when user requests ticket move (forward/backward)."""

    ticket: Ticket
    forward: bool = True


@dataclass
class TicketEditRequested(Message):
    """Posted when user requests to edit a ticket."""

    ticket: Ticket


@dataclass
class TicketDeleteRequested(Message):
    """Posted when user requests to delete a ticket."""

    ticket: Ticket


@dataclass
class TicketDragMove(Message):
    """Posted when a ticket is dragged to a new column."""

    ticket: Ticket
    target_status: TicketStatus | None
