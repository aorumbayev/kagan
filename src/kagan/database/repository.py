"""Ticket repository with async session management."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import col, select

from kagan.database.engine import create_db_engine, create_db_tables
from kagan.database.models import (
    AgentLog,
    MergeReadiness,
    Scratchpad,
    Ticket,
    TicketCreate,
    TicketEvent,
    TicketPublic,
    TicketStatus,
    TicketSummary,
    TicketUpdate,
)
from kagan.limits import SCRATCHPAD_LIMIT

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class TicketRepository:
    """Async repository for ticket operations."""

    def __init__(
        self,
        db_path: str | Path = ".kagan/state.db",
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._lock = asyncio.Lock()
        self._on_change = on_change
        self._on_status_change: (
            Callable[[str, TicketStatus | None, TicketStatus | None], None] | None
        ) = None

    async def initialize(self) -> None:
        """Initialize engine and create tables."""
        self._engine = await create_db_engine(self.db_path)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        await create_db_tables(self._engine)

    async def close(self) -> None:
        """Close engine and release resources."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    def _get_session(self) -> AsyncSession:
        """Get a new async session."""
        assert self._session_factory, "Repository not initialized"
        return self._session_factory()

    def set_status_change_callback(
        self,
        callback: Callable[[str, TicketStatus | None, TicketStatus | None], None] | None,
    ) -> None:
        """Set callback for ticket status changes."""
        self._on_status_change = callback

    def _notify_change(self, ticket_id: str) -> None:
        if self._on_change:
            self._on_change(ticket_id)

    def _notify_status_change(
        self,
        ticket_id: str,
        old_status: TicketStatus | None,
        new_status: TicketStatus | None,
    ) -> None:
        if self._on_status_change:
            self._on_status_change(ticket_id, old_status, new_status)

    async def create(self, data: TicketCreate | Ticket) -> Ticket:
        """Create a new ticket from TicketCreate or Ticket."""
        ticket = data if isinstance(data, Ticket) else Ticket.model_validate(data.model_dump())

        async with self._lock:
            async with self._get_session() as session:
                session.add(ticket)
                await session.commit()
                await session.refresh(ticket)

        if ticket.id:
            self._notify_change(ticket.id)
            self._notify_status_change(ticket.id, None, ticket.status)
        return ticket

    async def get(self, ticket_id: str) -> Ticket | None:
        """Get a ticket by ID."""
        async with self._get_session() as session:
            return await session.get(Ticket, ticket_id)

    async def get_all(self) -> Sequence[Ticket]:
        """Get all tickets ordered by status, priority, created_at."""
        async with self._get_session() as session:
            result = await session.execute(
                select(Ticket).order_by(
                    case(
                        (Ticket.status == TicketStatus.BACKLOG, 0),
                        (Ticket.status == TicketStatus.IN_PROGRESS, 1),
                        (Ticket.status == TicketStatus.REVIEW, 2),
                        (Ticket.status == TicketStatus.DONE, 3),
                        else_=99,
                    ),
                    col(Ticket.priority).desc(),
                    Ticket.created_at.asc(),
                )
            )
            return result.scalars().all()

    async def get_by_status(self, status: TicketStatus) -> Sequence[Ticket]:
        """Get all tickets with a specific status."""
        async with self._get_session() as session:
            result = await session.execute(
                select(Ticket)
                .where(Ticket.status == status)
                .order_by(col(Ticket.priority).desc(), Ticket.created_at.asc())
            )
            return result.scalars().all()

    async def update(self, ticket_id: str, data: TicketUpdate) -> Ticket | None:
        """Update a ticket with TicketUpdate DTO."""
        async with self._lock:
            async with self._get_session() as session:
                ticket = await session.get(Ticket, ticket_id)
                if not ticket:
                    return None

                old_status = ticket.status
                update_data = data.model_dump(exclude_unset=True)

                ticket.sqlmodel_update(update_data)
                ticket.updated_at = datetime.now()

                session.add(ticket)
                await session.commit()
                await session.refresh(ticket)

                if data.status and data.status != old_status:
                    self._notify_status_change(ticket_id, old_status, data.status)

                self._notify_change(ticket_id)
                return ticket

    async def update_fields(self, ticket_id: str, **kwargs: Any) -> Ticket | None:
        """Update a ticket with keyword arguments."""
        data = TicketUpdate(**kwargs)
        return await self.update(ticket_id, data)

    async def delete(self, ticket_id: str) -> bool:
        """Delete a ticket. Returns True if deleted."""
        async with self._lock:
            async with self._get_session() as session:
                ticket = await session.get(Ticket, ticket_id)
                if not ticket:
                    return False

                old_status = ticket.status
                await session.delete(ticket)
                await session.commit()

        self._notify_change(ticket_id)
        self._notify_status_change(ticket_id, old_status, None)
        return True

    async def get_public(self, ticket_id: str) -> TicketPublic | None:
        """Get a ticket as TicketPublic DTO."""
        ticket = await self.get(ticket_id)
        if not ticket:
            return None
        return TicketPublic.model_validate(ticket)

    async def get_all_public(self) -> list[TicketPublic]:
        """Get all tickets as TicketPublic DTOs."""
        tickets = await self.get_all()
        return [TicketPublic.model_validate(t) for t in tickets]

    async def get_summaries(self) -> list[TicketSummary]:
        """Get lightweight ticket summaries for list views."""
        tickets = await self.get_all()
        if not tickets:
            return []

        async with self._get_session() as session:
            children_counts: dict[str, int] = {}
            for ticket in tickets:
                if not ticket.id:
                    continue
                result = await session.execute(
                    select(func.count(Ticket.id)).where(Ticket.parent_id == ticket.id)
                )
                children_counts[ticket.id] = result.scalar() or 0

        summaries: list[TicketSummary] = []
        for ticket in tickets:
            if not ticket.id:
                continue
            summaries.append(
                TicketSummary(
                    id=ticket.id,
                    title=ticket.title,
                    status=ticket.status,
                    priority=ticket.priority,
                    ticket_type=ticket.ticket_type,
                    session_active=ticket.session_active,
                    has_children=children_counts.get(ticket.id, 0) > 0,
                    has_active_agent=ticket.session_active,
                    last_agent_failed=ticket.last_error is not None,
                )
            )
        return summaries

    async def sync_status_from_agent_complete(self, ticket_id: str, success: bool) -> Ticket | None:
        """Auto-transition ticket when agent completes."""
        ticket = await self.get(ticket_id)
        if not ticket:
            return None

        if success and ticket.status == TicketStatus.IN_PROGRESS:
            return await self.update_fields(
                ticket_id,
                status=TicketStatus.REVIEW,
                session_active=False,
                last_error=None,
            )
        if not success:
            return await self.update_fields(ticket_id, session_active=False)
        return ticket

    async def sync_status_from_review_pass(self, ticket_id: str) -> Ticket | None:
        """Auto-transition ticket when review passes (REVIEW -> DONE)."""
        ticket = await self.get(ticket_id)
        if not ticket or ticket.status != TicketStatus.REVIEW:
            return ticket

        return await self.update_fields(
            ticket_id,
            status=TicketStatus.DONE,
            checks_passed=True,
            merge_readiness=MergeReadiness.READY,
        )

    async def sync_status_from_review_reject(
        self, ticket_id: str, reason: str | None = None
    ) -> Ticket | None:
        """Move ticket back to IN_PROGRESS after review rejection."""
        ticket = await self.get(ticket_id)
        if not ticket or ticket.status != TicketStatus.REVIEW:
            return ticket

        return await self.update_fields(
            ticket_id,
            status=TicketStatus.IN_PROGRESS,
            checks_passed=False,
            review_summary=reason,
        )

    async def move(self, ticket_id: str, new_status: TicketStatus) -> Ticket | None:
        """Move a ticket to a new status."""
        return await self.update_fields(ticket_id, status=new_status)

    async def mark_session_active(self, ticket_id: str, active: bool) -> Ticket | None:
        """Mark ticket session as active/inactive."""
        return await self.update_fields(ticket_id, session_active=active)

    async def set_review_summary(
        self, ticket_id: str, summary: str, checks_passed: bool | None
    ) -> Ticket | None:
        """Set review summary and checks status."""
        return await self.update_fields(
            ticket_id, review_summary=summary, checks_passed=checks_passed
        )

    async def increment_total_iterations(self, ticket_id: str) -> None:
        """Increment the total_iterations counter."""
        async with self._lock:
            async with self._get_session() as session:
                ticket = await session.get(Ticket, ticket_id)
                if ticket:
                    ticket.total_iterations += 1
                    session.add(ticket)
                    await session.commit()

    async def get_counts(self) -> dict[TicketStatus, int]:
        """Get ticket counts by status."""
        async with self._get_session() as session:
            result = await session.execute(
                select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
            )
            counts = {status: 0 for status in TicketStatus}
            for status, count in result.all():
                counts[status] = count
            return counts

    async def search(self, query: str) -> Sequence[Ticket]:
        """Search tickets by title, description, or ID."""
        if not query or not query.strip():
            return []

        query = query.strip()
        pattern = f"%{query}%"

        async with self._get_session() as session:
            result = await session.execute(
                select(Ticket)
                .where(
                    (Ticket.id == query)
                    | (Ticket.title.ilike(pattern))
                    | (Ticket.description.ilike(pattern))
                )
                .order_by(Ticket.updated_at.desc())
            )
            return result.scalars().all()

    async def get_scratchpad(self, ticket_id: str) -> str:
        """Get scratchpad content for a ticket."""
        async with self._get_session() as session:
            scratchpad = await session.get(Scratchpad, ticket_id)
            return scratchpad.content if scratchpad else ""

    async def update_scratchpad(self, ticket_id: str, content: str) -> None:
        """Update or create scratchpad content."""
        content = content[-SCRATCHPAD_LIMIT:] if len(content) > SCRATCHPAD_LIMIT else content

        async with self._lock:
            async with self._get_session() as session:
                scratchpad = await session.get(Scratchpad, ticket_id)
                if scratchpad:
                    scratchpad.content = content
                    scratchpad.updated_at = datetime.now()
                else:
                    scratchpad = Scratchpad(ticket_id=ticket_id, content=content)
                session.add(scratchpad)
                await session.commit()

    async def delete_scratchpad(self, ticket_id: str) -> None:
        """Delete scratchpad for a ticket."""
        async with self._lock:
            async with self._get_session() as session:
                scratchpad = await session.get(Scratchpad, ticket_id)
                if scratchpad:
                    await session.delete(scratchpad)
                    await session.commit()

    async def append_agent_log(
        self, ticket_id: str, log_type: str, iteration: int, content: str
    ) -> None:
        """Append a log entry for agent execution."""
        async with self._lock:
            async with self._get_session() as session:
                log = AgentLog(
                    ticket_id=ticket_id,
                    log_type=log_type,
                    iteration=iteration,
                    content=content,
                )
                session.add(log)
                await session.commit()

    async def get_agent_logs(self, ticket_id: str, log_type: str) -> Sequence[AgentLog]:
        """Get all log entries for a ticket and log type."""
        async with self._get_session() as session:
            result = await session.execute(
                select(AgentLog)
                .where(AgentLog.ticket_id == ticket_id, AgentLog.log_type == log_type)
                .order_by(AgentLog.iteration.asc(), AgentLog.created_at.asc())
            )
            return result.scalars().all()

    async def clear_agent_logs(self, ticket_id: str) -> None:
        """Clear all agent logs for a ticket."""
        async with self._lock:
            async with self._get_session() as session:
                result = await session.execute(
                    select(AgentLog).where(AgentLog.ticket_id == ticket_id)
                )
                for log in result.scalars().all():
                    await session.delete(log)
                await session.commit()

    async def append_event(self, ticket_id: str, event_type: str, message: str) -> None:
        """Append an audit event for a ticket."""
        async with self._lock:
            async with self._get_session() as session:
                event = TicketEvent(
                    ticket_id=ticket_id,
                    event_type=event_type,
                    message=message,
                )
                session.add(event)
                await session.commit()

    async def get_events(self, ticket_id: str, limit: int = 20) -> Sequence[TicketEvent]:
        """Get recent audit events for a ticket."""
        async with self._get_session() as session:
            result = await session.execute(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket_id)
                .order_by(TicketEvent.created_at.desc(), TicketEvent.id.desc())
                .limit(limit)
            )
            return result.scalars().all()
