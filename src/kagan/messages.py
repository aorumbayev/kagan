"""Centralized message definitions for Kagan TUI."""

from __future__ import annotations

from dataclasses import dataclass

from textual.message import Message


@dataclass
class TicketChanged(Message):
    """Posted when a ticket status changes, to trigger UI refresh.

    This message does NOT bubble - it's handled only by the current screen.
    The app callback posts this message, so if it bubbled back to the app,
    it would create an infinite loop.
    """

    bubble = False
