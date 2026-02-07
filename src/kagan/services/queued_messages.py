"""Queued follow-up message service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class QueuedMessage:
    """Queued follow-up message for a session."""

    content: str
    author: str | None
    metadata: dict[str, Any] | None
    queued_at: datetime


@dataclass(frozen=True)
class QueueStatus:
    """Queue status for a session."""

    has_queued: bool
    queued_at: datetime | None
    content_preview: str | None
    author: str | None


class QueuedMessageService(Protocol):
    """Service interface for queued follow-up messages."""

    async def queue_message(
        self,
        session_id: str,
        content: str,
        *,
        author: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueuedMessage:
        """Queue a follow-up message for a session."""
        ...

    async def cancel_queued(self, session_id: str) -> None:
        """Cancel any queued message for a session."""
        ...

    async def get_status(self, session_id: str) -> QueueStatus:
        """Get queued message status for a session."""
        ...

    async def take_queued(self, session_id: str) -> QueuedMessage | None:
        """Return and clear the queued message for a session."""
        ...

    async def take_all_queued(self, session_id: str) -> list[QueuedMessage]: ...

    async def get_queued(self, session_id: str) -> list[QueuedMessage]:
        """Get all queued messages without removing them."""
        ...

    async def remove_message(self, session_id: str, index: int) -> bool:
        """Remove a specific message by index. Returns True if removed."""
        ...


class QueuedMessageServiceImpl:
    """In-memory queued message service keyed by session."""

    def __init__(self, *, preview_chars: int = 120) -> None:
        self._lock = asyncio.Lock()
        self._preview_chars = max(preview_chars, 8)
        self._queue: dict[str, list[QueuedMessage]] = {}

    async def queue_message(
        self,
        session_id: str,
        content: str,
        *,
        author: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueuedMessage:
        message = QueuedMessage(
            content=content,
            author=author,
            metadata=metadata,
            queued_at=datetime.now(),
        )
        async with self._lock:
            self._queue.setdefault(session_id, []).append(message)
        return message

    async def cancel_queued(self, session_id: str) -> None:
        async with self._lock:
            self._queue.pop(session_id, None)

    async def get_status(self, session_id: str) -> QueueStatus:
        async with self._lock:
            messages = self._queue.get(session_id)
        if not messages:
            return QueueStatus(
                has_queued=False,
                queued_at=None,
                content_preview=None,
                author=None,
            )
        last = messages[-1]
        count = len(messages)
        preview = self._preview(last.content)
        if count > 1:
            preview = f"({count} messages) {preview}"
        return QueueStatus(
            has_queued=True,
            queued_at=last.queued_at,
            content_preview=preview,
            author=last.author,
        )

    async def take_queued(self, session_id: str) -> QueuedMessage | None:
        async with self._lock:
            messages = self._queue.pop(session_id, None)
        if not messages:
            return None
        if len(messages) == 1:
            return messages[0]
        merged_content = "\n\n".join(m.content for m in messages)
        return QueuedMessage(
            content=merged_content,
            author=messages[-1].author,
            metadata=messages[-1].metadata,
            queued_at=messages[-1].queued_at,
        )

    async def take_all_queued(self, session_id: str) -> list[QueuedMessage]:
        async with self._lock:
            return self._queue.pop(session_id, [])

    async def get_queued(self, session_id: str) -> list[QueuedMessage]:
        async with self._lock:
            return list(self._queue.get(session_id, []))

    async def remove_message(self, session_id: str, index: int) -> bool:
        async with self._lock:
            messages = self._queue.get(session_id)
            if not messages or index < 0 or index >= len(messages):
                return False
            messages.pop(index)
            if not messages:
                self._queue.pop(session_id, None)
            return True

    def _preview(self, content: str) -> str:
        if len(content) <= self._preview_chars:
            return content
        cutoff = max(self._preview_chars - 3, 0)
        return f"{content[:cutoff]}..."
