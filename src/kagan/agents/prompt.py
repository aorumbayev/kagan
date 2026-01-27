"""Build iteration prompts for agents."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kagan.config import HatConfig
    from kagan.database.models import Ticket

TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "iteration.md"


@cache
def _load_template() -> str:
    if TEMPLATE_PATH.exists():
        return TEMPLATE_PATH.read_text()
    # Fallback inline template
    return """# Iteration {iteration} of {max_iterations}

## Task: {title}

{description}

## Your Progress So Far
{scratchpad}

## Instructions
Work on the task. At the END of your response, include exactly ONE signal:
- `<complete/>` - Task fully done
- `<continue/>` - Made progress, need more iterations
- `<blocked reason="..."/>` - Need human help

{hat_instructions}
"""


def build_prompt(
    ticket: Ticket,
    iteration: int,
    max_iterations: int,
    scratchpad: str,
    hat: HatConfig | None = None,
) -> str:
    """Build the prompt for an agent iteration."""
    return _load_template().format(
        iteration=iteration,
        max_iterations=max_iterations,
        title=ticket.title,
        description=ticket.description or "No description provided.",
        scratchpad=scratchpad or "(No previous progress - this is iteration 1)",
        hat_instructions=f"## Role\n{hat.system_prompt}" if hat and hat.system_prompt else "",
    )
