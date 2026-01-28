"""Prompt loader with layered override support."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    from kagan.config import KaganConfig

# Default prompts directory (user overrides)
DEFAULT_PROMPTS_DIR = Path(".kagan/prompts")

# Built-in prompts directory (package defaults)
BUILTIN_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def dump_default_prompts(prompts_dir: Path | None = None) -> None:
    """Dump default prompt templates to the user's prompts directory.

    Creates the prompts directory structure and writes the built-in templates
    so users can customize them.

    Args:
        prompts_dir: Target directory (defaults to .kagan/prompts).
    """
    target_dir = prompts_dir or DEFAULT_PROMPTS_DIR

    # Create directory
    target_dir.mkdir(parents=True, exist_ok=True)

    # Write planner prompt (no comments - they get sent to the AI)
    planner_content = _get_default_planner_prompt()
    (target_dir / "planner.md").write_text(planner_content)


class PromptLoader:
    """Load prompts with layered override support.

    Priority: User files > TOML inline > Built-in defaults

    User files are loaded from:
        .kagan/prompts/planner.md
    """

    def __init__(self, config: KaganConfig, prompts_dir: Path | None = None) -> None:
        """Initialize the prompt loader.

        Args:
            config: The Kagan configuration.
            prompts_dir: Optional custom prompts directory (defaults to .kagan/prompts).
        """
        self._config = config
        self._prompts_dir = prompts_dir or DEFAULT_PROMPTS_DIR

    def get_planner_prompt(self) -> str:
        """Load planner system prompt: .kagan/prompts/planner.md > toml > hardcoded."""
        # Priority 1: User file override
        user_file = self._prompts_dir / "planner.md"
        if user_file.exists():
            return user_file.read_text()

        # Priority 2: TOML inline config
        if self._config.prompts.planner_system_prompt:
            return self._config.prompts.planner_system_prompt

        # Priority 3: Built-in default (hardcoded in planner.py)
        return _get_default_planner_prompt()

    def get_worker_prompt(self) -> str:
        """Load worker/iteration prompt template.

        Looks for .kagan/prompts/iteration.md, falls back to built-in.
        """
        # Priority 1: User file override
        user_file = self._prompts_dir / "iteration.md"
        if user_file.exists():
            return user_file.read_text()

        # Priority 2: Built-in template
        return _load_builtin_template("iteration.md") or _get_default_iteration_prompt()

    def get_hat_instructions(self, hat: Any | None) -> str:
        """Get hat-specific instructions.

        Args:
            hat: Optional hat configuration object with system_prompt attribute.

        Returns:
            The system prompt for the hat, or empty string.
        """
        if hat and hasattr(hat, "system_prompt") and hat.system_prompt:
            return hat.system_prompt
        return ""

    def load_review_prompt(
        self,
        title: str,
        ticket_id: str,
        description: str,
        commits: str,
        diff_summary: str,
    ) -> str:
        """Load and format the review prompt template.

        Args:
            title: Ticket title.
            ticket_id: Ticket ID.
            description: Ticket description.
            commits: Formatted commit messages.
            diff_summary: Diff statistics summary.

        Returns:
            Formatted review prompt.
        """
        # Priority 1: User file override
        user_file = self._prompts_dir / "review.md"
        if user_file.exists():
            template = user_file.read_text()
        else:
            # Priority 2: Built-in template
            template = _load_builtin_template("review.md") or _get_default_review_prompt()

        return template.format(
            title=title,
            ticket_id=ticket_id,
            description=description,
            commits=commits,
            diff_summary=diff_summary,
        )


@cache
def _load_builtin_template(filename: str) -> str:
    """Load a built-in template file.

    Args:
        filename: The template filename (e.g., "iteration.md").

    Returns:
        The template content, or fallback inline template if not found.
    """
    template_path = BUILTIN_PROMPTS_DIR / filename
    if template_path.exists():
        return template_path.read_text()

    return ""


def _get_default_iteration_prompt() -> str:
    """Get the default iteration prompt template."""
    return """\
# Iteration {iteration} of {max_iterations}

## Task: {title}

{description}

{hat_instructions}

## Your Progress So Far
{scratchpad}

## CRITICAL: Response Signal Required

You MUST end your response with exactly ONE of these XML signals:
- `<complete/>` - Task is FULLY DONE and verified working
- `<continue/>` - Made progress, need another iteration
- `<blocked reason="why"/>` - Cannot proceed without human help

**If you completed the task, output `<complete/>` as the last thing in your response.**
"""


def _get_default_planner_prompt() -> str:
    """Get the default planner preamble (customizable part only).

    Note: The output format section is always appended by build_planner_prompt()
    to ensure ticket parsing works correctly.
    """
    return """\
You are a project planning assistant. Your job is to take user requests
and create well-structured development tickets.

When the user describes what they want to build or accomplish,
analyze their request and create ONE detailed ticket.

## Guidelines
1. Title should start with a verb (Create, Implement, Fix, Add, Update, etc.)
2. Description should be thorough enough for a developer to understand the task
3. Include acceptance criteria as bullet points
4. If the request is vague, make reasonable assumptions and note them

After outputting the ticket, briefly explain what you created and any assumptions you made.
"""


def _get_default_review_prompt() -> str:
    """Get the default review prompt template."""
    return """\
# Code Review Request

## Ticket: {title}

**ID:** {ticket_id}
**Description:** {description}

## Changes Made

### Commits
{commits}

### Diff Summary
{diff_summary}

## Review Criteria

Please review the changes against:
1. Does the implementation match the ticket description?
2. Are there any obvious bugs or issues?
3. Is the code reasonably clean and maintainable?

## Your Task

1. Review the changes
2. Provide a brief summary of what was implemented
3. End with exactly ONE signal:

- `<approve summary="Brief 1-2 sentence summary of work done"/>` - Changes are good
- `<reject reason="What needs to be fixed"/>` - Changes need work

Example:
```
The implementation looks good. Added the new feature with proper error handling.
<approve summary="Implemented user authentication with JWT tokens and proper validation"/>
```
"""
