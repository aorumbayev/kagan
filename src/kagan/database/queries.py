"""SQL query helpers and row conversion for database operations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from kagan.database.models import Ticket, TicketPriority, TicketStatus, TicketType

if TYPE_CHECKING:
    import aiosqlite


def row_to_ticket(row: aiosqlite.Row) -> Ticket:
    """Convert a database row to a Ticket model."""
    try:
        ticket_type_raw = row["ticket_type"]
        ticket_type = TicketType(ticket_type_raw) if ticket_type_raw else TicketType.PAIR
    except (KeyError, IndexError):
        ticket_type = TicketType.PAIR

    return Ticket(
        id=row["id"],
        title=row["title"],
        description=row["description"] or "",
        status=TicketStatus(row["status"]),
        priority=TicketPriority(row["priority"]),
        ticket_type=ticket_type,
        assigned_hat=row["assigned_hat"],
        agent_backend=row["agent_backend"],
        parent_id=row["parent_id"],
        acceptance_criteria=deserialize_acceptance_criteria(row["acceptance_criteria"]),
        check_command=row["check_command"],
        review_summary=row["review_summary"],
        checks_passed=None if row["checks_passed"] is None else bool(row["checks_passed"]),
        session_active=bool(row["session_active"]),
        created_at=(
            datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now()
        ),
        updated_at=(
            datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now()
        ),
    )


def serialize_acceptance_criteria(criteria: list[str]) -> str:
    """Serialize acceptance criteria list for storage."""
    return json.dumps(criteria)


def deserialize_acceptance_criteria(raw: str | None) -> list[str]:
    """Deserialize acceptance criteria from storage."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        return [raw]
    return []


def build_update_params(update, serialize_fn) -> tuple[list[str], list]:
    """Build SQL UPDATE parameters from TicketUpdate model."""
    priority_val = (
        update.priority.value if isinstance(update.priority, TicketPriority) else update.priority
    )
    type_val = (
        update.ticket_type.value
        if isinstance(update.ticket_type, TicketType)
        else update.ticket_type
    )
    status_val = update.status.value if isinstance(update.status, TicketStatus) else update.status
    criteria_val = (
        serialize_fn(update.acceptance_criteria) if update.acceptance_criteria is not None else None
    )
    checks_val = (1 if update.checks_passed else 0) if update.checks_passed is not None else None
    session_val = (1 if update.session_active else 0) if update.session_active is not None else None

    fields = {
        "title": update.title,
        "description": update.description,
        "priority": priority_val,
        "ticket_type": type_val,
        "status": status_val,
        "assigned_hat": update.assigned_hat,
        "agent_backend": update.agent_backend,
        "parent_id": update.parent_id,
        "acceptance_criteria": criteria_val,
        "check_command": update.check_command,
        "review_summary": update.review_summary,
        "checks_passed": checks_val,
        "session_active": session_val,
    }

    updates, values = [], []
    for field, value in fields.items():
        if value is not None:
            updates.append(f"{field} = ?")
            values.append(value)

    return updates, values


def build_insert_params(ticket, serialize_fn) -> tuple:
    """Build INSERT parameters for a new ticket."""
    return (
        ticket.id,
        ticket.title,
        ticket.description,
        ticket.status.value if isinstance(ticket.status, TicketStatus) else ticket.status,
        ticket.priority.value if isinstance(ticket.priority, TicketPriority) else ticket.priority,
        (
            ticket.ticket_type.value
            if isinstance(ticket.ticket_type, TicketType)
            else ticket.ticket_type
        ),
        ticket.assigned_hat,
        ticket.agent_backend,
        ticket.parent_id,
        serialize_fn(ticket.acceptance_criteria),
        ticket.check_command,
        ticket.review_summary,
        None if ticket.checks_passed is None else (1 if ticket.checks_passed else 0),
        1 if ticket.session_active else 0,
        ticket.created_at.isoformat(),
        ticket.updated_at.isoformat(),
    )


# SQL Statements
INSERT_TICKET_SQL = """
INSERT INTO tickets
    (id, title, description, status, priority, ticket_type,
     assigned_hat, agent_backend, parent_id,
     acceptance_criteria, check_command, review_summary,
     checks_passed, session_active,
     created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_ALL_TICKETS_SQL = """
SELECT * FROM tickets
ORDER BY
    CASE status
        WHEN 'BACKLOG' THEN 0
        WHEN 'IN_PROGRESS' THEN 1
        WHEN 'REVIEW' THEN 2
        WHEN 'DONE' THEN 3
    END,
    priority DESC,
    created_at ASC
"""

SELECT_BY_STATUS_SQL = """
SELECT * FROM tickets
WHERE status = ?
ORDER BY priority DESC, created_at ASC
"""

UPSERT_SCRATCHPAD_SQL = """
INSERT INTO scratchpads (ticket_id, content, updated_at)
VALUES (?, ?, CURRENT_TIMESTAMP)
ON CONFLICT(ticket_id) DO UPDATE SET
content = excluded.content, updated_at = CURRENT_TIMESTAMP
"""
