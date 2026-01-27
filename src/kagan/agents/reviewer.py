"""Review agent for validating work and signaling approval/rejection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kagan.acp.agent import Agent
    from kagan.agents.prompt_loader import PromptLoader
    from kagan.database.models import Ticket

# Review signal patterns
REVIEW_SIGNALS = {
    "approve": re.compile(r"<approve\s*/?>", re.IGNORECASE),
    "approve_summary": re.compile(r'<approve\s+summary="([^"]+)"\s*/?>', re.IGNORECASE),
    "reject": re.compile(r'<reject\s+reason="([^"]+)"\s*/?>', re.IGNORECASE),
}

TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "review.md"


@dataclass
class ReviewResult:
    """Result of a code review."""

    approved: bool
    summary: str  # work summary for ticket description
    reason: str  # rejection reason if not approved


@cache
def _load_template() -> str:
    """Load the review prompt template."""
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH.read_text()
    # Fallback inline template
    return """# Code Review Request

## Ticket: {title}

**ID:** {ticket_id}
**Description:** {description}

## Changes Made

### Commits
{commits}

### Diff Summary
{diff_summary}

## Your Task

Review the changes and end with exactly ONE signal:
- `<approve summary="Brief summary"/>` - Changes are good
- `<reject reason="What needs fixing"/>` - Changes need work
"""


def parse_review_signal(output: str) -> ReviewResult:
    """Parse agent output for review signals.

    Args:
        output: The agent's response text.

    Returns:
        ReviewResult with approval status, summary, and reason.
    """
    # Check for approve with summary first (more specific)
    if match := REVIEW_SIGNALS["approve_summary"].search(output):
        return ReviewResult(approved=True, summary=match.group(1), reason="")

    # Check for simple approve
    if REVIEW_SIGNALS["approve"].search(output):
        return ReviewResult(approved=True, summary="", reason="")

    # Check for reject
    if match := REVIEW_SIGNALS["reject"].search(output):
        return ReviewResult(approved=False, summary="", reason=match.group(1))

    # Default: not approved if no signal found
    return ReviewResult(approved=False, summary="", reason="No review signal found in response")


def build_review_prompt(
    ticket: Ticket,
    commits: list[str],
    diff_summary: str,
    prompt_loader: PromptLoader | None = None,
) -> str:
    """Build the review prompt from template.

    Args:
        ticket: The ticket being reviewed.
        commits: List of commit messages/hashes.
        diff_summary: Summary of the diff changes.
        prompt_loader: Optional prompt loader for custom templates.

    Returns:
        Formatted prompt string.
    """
    commits_text = "\n".join(f"- {c}" for c in commits) if commits else "(No commits)"

    # Load template: prompt_loader > builtin
    template = prompt_loader.get_reviewer_prompt() if prompt_loader else _load_template()

    return template.format(
        title=ticket.title,
        ticket_id=ticket.id,
        description=ticket.description or "No description provided.",
        commits=commits_text,
        diff_summary=diff_summary or "(No changes)",
    )


async def run_review(
    agent: Agent,
    ticket: Ticket,
    commits: list[str],
    diff: str,
    prompt_loader: PromptLoader | None = None,
) -> ReviewResult:
    """Run a code review using the agent.

    Args:
        agent: The agent to use for review.
        ticket: The ticket being reviewed.
        commits: List of commit messages.
        diff: The diff summary to review.
        prompt_loader: Optional prompt loader for custom templates.

    Returns:
        ReviewResult with approval status and details.
    """
    prompt = build_review_prompt(ticket, commits, diff, prompt_loader)

    try:
        await agent.send_prompt(prompt)
        response = agent.get_response_text()
        return parse_review_signal(response)
    except Exception as e:
        return ReviewResult(
            approved=False,
            summary="",
            reason=f"Review failed: {e}",
        )
