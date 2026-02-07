"""SQLModel models for database entities."""

# NOTE: Intentionally NOT using `from __future__ import annotations` here
# because SQLModel/SQLAlchemy needs to evaluate type hints at runtime
# for relationship definitions to work properly.

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from kagan.config import KaganConfig


class TicketStatus(StrEnum):
    """Ticket status values for Kanban columns."""

    BACKLOG = "BACKLOG"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    DONE = "DONE"

    @classmethod
    def next_status(cls, current: "TicketStatus") -> "TicketStatus | None":
        """Get the next status in the workflow."""
        from kagan.constants import COLUMN_ORDER

        idx = COLUMN_ORDER.index(current)
        if idx < len(COLUMN_ORDER) - 1:
            return COLUMN_ORDER[idx + 1]
        return None

    @classmethod
    def prev_status(cls, current: "TicketStatus") -> "TicketStatus | None":
        """Get the previous status in the workflow."""
        from kagan.constants import COLUMN_ORDER

        idx = COLUMN_ORDER.index(current)
        if idx > 0:
            return COLUMN_ORDER[idx - 1]
        return None


class TicketPriority(IntEnum):
    """Ticket priority levels."""

    LOW = 0
    MEDIUM = 1
    HIGH = 2

    @property
    def label(self) -> str:
        """Short display label."""
        return {self.LOW: "LOW", self.MEDIUM: "MED", self.HIGH: "HIGH"}[self]

    @property
    def css_class(self) -> str:
        """CSS class name for styling."""
        return {self.LOW: "low", self.MEDIUM: "medium", self.HIGH: "high"}[self]


class TicketType(StrEnum):
    """Ticket execution type."""

    AUTO = "AUTO"  # Autonomous execution via ACP scheduler
    PAIR = "PAIR"  # Pair programming via tmux session


class MergeReadiness(StrEnum):
    """Merge readiness indicator for REVIEW tickets."""

    READY = "ready"
    RISK = "risk"
    BLOCKED = "blocked"


class TicketBase(SQLModel):
    """Base ticket fields shared across ticket models."""

    title: str = Field(min_length=1, max_length=200, index=True)
    description: str = Field(default="", max_length=10000)
    status: TicketStatus = Field(default=TicketStatus.BACKLOG, index=True)
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, index=True)
    ticket_type: TicketType = Field(default=TicketType.PAIR)
    assigned_hat: str | None = Field(default=None)
    agent_backend: str | None = Field(default=None)
    parent_id: str | None = Field(default=None, foreign_key="tickets.id", index=True)
    acceptance_criteria: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    review_summary: str | None = Field(default=None, max_length=5000)
    checks_passed: bool | None = Field(default=None)
    session_active: bool = Field(default=False)
    total_iterations: int = Field(default=0)
    merge_failed: bool = Field(default=False)
    merge_error: str | None = Field(default=None, max_length=500)
    merge_readiness: MergeReadiness = Field(default=MergeReadiness.RISK)
    last_error: str | None = Field(default=None, max_length=500)
    block_reason: str | None = Field(default=None, max_length=500)


class Ticket(TicketBase, table=True):
    """Ticket table model representing a Kanban card."""

    __tablename__ = "tickets"

    id: Optional[str] = Field(default_factory=lambda: uuid4().hex[:8], primary_key=True)  # noqa: UP045
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    parent: Optional["Ticket"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Ticket.id"},
    )
    children: list["Ticket"] = Relationship(back_populates="parent")
    scratchpad: Optional["Scratchpad"] = Relationship(
        back_populates="ticket",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    logs: list["AgentLog"] = Relationship(
        back_populates="ticket",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    events: list["TicketEvent"] = Relationship(
        back_populates="ticket",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @property
    def short_id(self) -> str:
        """Return shortened ID for display."""
        return (self.id or "")[:8]

    @property
    def priority_label(self) -> str:
        """Return human-readable priority label."""
        return self.priority.label

    @classmethod
    def create(
        cls,
        title: str,
        description: str = "",
        priority: TicketPriority = TicketPriority.MEDIUM,
        ticket_type: TicketType = TicketType.PAIR,
        status: TicketStatus = TicketStatus.BACKLOG,
        assigned_hat: str | None = None,
        parent_id: str | None = None,
        agent_backend: str | None = None,
        acceptance_criteria: list[str] | None = None,
        review_summary: str | None = None,
        checks_passed: bool | None = None,
        session_active: bool = False,
        merge_failed: bool = False,
        merge_error: str | None = None,
        merge_readiness: MergeReadiness = MergeReadiness.RISK,
        last_error: str | None = None,
        block_reason: str | None = None,
    ) -> "Ticket":
        """Create a new ticket with generated ID and timestamps."""
        return cls(
            title=title,
            description=description,
            priority=priority,
            ticket_type=ticket_type,
            status=status,
            assigned_hat=assigned_hat,
            parent_id=parent_id,
            agent_backend=agent_backend,
            acceptance_criteria=acceptance_criteria or [],
            review_summary=review_summary,
            checks_passed=checks_passed,
            session_active=session_active,
            merge_failed=merge_failed,
            merge_error=merge_error,
            merge_readiness=merge_readiness,
            last_error=last_error,
            block_reason=block_reason,
        )

    def get_agent_config(self, config: "KaganConfig") -> Any:
        """Resolve agent config with priority order."""
        from kagan.config import get_fallback_agent_config
        from kagan.data.builtin_agents import get_builtin_agent

        if self.agent_backend:
            if builtin := get_builtin_agent(self.agent_backend):
                return builtin.config
            if agent_config := config.get_agent(self.agent_backend):
                return agent_config

        default_agent = config.general.default_worker_agent
        if builtin := get_builtin_agent(default_agent):
            return builtin.config
        if agent_config := config.get_agent(default_agent):
            return agent_config

        return get_fallback_agent_config()


class TicketCreate(SQLModel):
    """Input DTO for creating a ticket."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM)
    ticket_type: TicketType = Field(default=TicketType.PAIR)
    assigned_hat: str | None = None
    agent_backend: str | None = None
    parent_id: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)


class TicketUpdate(SQLModel):
    """Input DTO for updating a ticket."""

    title: str | None = None
    description: str | None = None
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    ticket_type: TicketType | None = None
    assigned_hat: str | None = None
    agent_backend: str | None = None
    acceptance_criteria: list[str] | None = None
    review_summary: str | None = None
    checks_passed: bool | None = None
    session_active: bool | None = None
    merge_failed: bool | None = None
    merge_error: str | None = None
    merge_readiness: MergeReadiness | None = None
    last_error: str | None = None
    block_reason: str | None = None


class TicketPublic(TicketBase):
    """Output DTO for API responses."""

    id: str
    created_at: datetime
    updated_at: datetime


class TicketSummary(SQLModel):
    """Lightweight output DTO for ticket lists."""

    id: str
    title: str
    status: TicketStatus
    priority: TicketPriority
    ticket_type: TicketType
    session_active: bool
    has_children: bool = False
    has_active_agent: bool = False
    last_agent_failed: bool = False


class Scratchpad(SQLModel, table=True):
    """Scratchpad for agent iteration memory."""

    __tablename__ = "scratchpads"

    ticket_id: str = Field(primary_key=True, foreign_key="tickets.id")
    content: str = Field(default="")
    updated_at: datetime = Field(default_factory=datetime.now)

    ticket: Ticket = Relationship(back_populates="scratchpad")


class AgentLog(SQLModel, table=True):
    """Agent execution log entry."""

    __tablename__ = "agent_logs"

    id: int | None = Field(default=None, primary_key=True)
    ticket_id: str = Field(foreign_key="tickets.id", index=True)
    log_type: str
    iteration: int = Field(default=1)
    content: str
    created_at: datetime = Field(default_factory=datetime.now)

    ticket: Ticket = Relationship(back_populates="logs")


class TicketEvent(SQLModel, table=True):
    """Audit event for ticket actions."""

    __tablename__ = "ticket_events"

    id: int | None = Field(default=None, primary_key=True)
    ticket_id: str = Field(foreign_key="tickets.id", index=True)
    event_type: str
    message: str
    created_at: datetime = Field(default_factory=datetime.now)

    ticket: Ticket = Relationship(back_populates="events")
