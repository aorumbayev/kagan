"""Buffered message bus for agent output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import log

from kagan.acp import messages

if TYPE_CHECKING:
    from textual.message import Message
    from textual.message_pump import MessagePump


class AgentMessageBus:
    """Capture and replay agent messages to UI subscribers."""

    def __init__(self, buffer_limit: int = 500) -> None:
        self._buffer_limit = buffer_limit
        self._messages: list[Message] = []
        self._subscribers: set[MessagePump] = set()

    def subscribe(self, target: MessagePump) -> None:
        """Attach a subscriber and replay buffered messages."""
        if target in self._subscribers:
            return
        self._subscribers.add(target)
        if self._messages:
            log.debug(
                "[AgentMessageBus] Replaying buffered messages",
                count=len(self._messages),
            )
            for msg in self._messages:
                target.post_message(msg)

    def unsubscribe(self, target: MessagePump) -> None:
        """Detach a subscriber."""
        self._subscribers.discard(target)

    def post_message(self, message: Message) -> bool:
        """Post to subscribers and store if safe to replay."""
        if self._should_buffer(message):
            self._messages.append(message)
            if len(self._messages) > self._buffer_limit:
                self._messages = self._messages[-self._buffer_limit :]

        posted = False
        for target in list(self._subscribers):
            try:
                target.post_message(message)
                posted = True
            except Exception:
                continue
        return posted

    def has_messages(self) -> bool:
        """Return True if any messages have been buffered."""
        return bool(self._messages)

    def _should_buffer(self, message: Message) -> bool:
        """Skip buffering for messages that should not be replayed."""
        return not isinstance(
            message,
            (
                messages.RequestPermission,
                messages.CreateTerminal,
                messages.KillTerminal,
                messages.GetTerminalState,
                messages.ReleaseTerminal,
                messages.WaitForTerminalExit,
            ),
        )
