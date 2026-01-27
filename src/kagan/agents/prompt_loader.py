"""Prompt loader with layered override support."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kagan.config import HatConfig, KaganConfig

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
    roles_dir = target_dir / "roles"

    # Create directories
    target_dir.mkdir(parents=True, exist_ok=True)
    roles_dir.mkdir(exist_ok=True)

    # Write worker template
    worker_content = _load_builtin_template("iteration.md")
    (target_dir / "worker.md").write_text(worker_content)

    # Write reviewer template
    reviewer_content = _load_builtin_template("review.md")
    (target_dir / "reviewer.md").write_text(reviewer_content)

    # Write planner prompt (no comments - they get sent to the AI)
    planner_content = _get_default_planner_prompt()
    (target_dir / "planner.md").write_text(planner_content)

    # Write example hat role file
    example_role = """\
# Example Hat Role

This file defines role-specific instructions for a hat.
Edit this file or create new ones in this directory.

## Instructions

You are a [role name]. Focus on:
- [Key responsibility 1]
- [Key responsibility 2]
- [Key responsibility 3]

## Guidelines

[Add any specific guidelines for this role]
"""
    (roles_dir / "example.md").write_text(example_role)


class PromptLoader:
    """Load prompts with layered override support.

    Priority: User files > TOML inline > Built-in defaults

    User files are loaded from:
        .kagan/prompts/worker.md
        .kagan/prompts/reviewer.md
        .kagan/prompts/planner.md
        .kagan/prompts/roles/<hat_name>.md
    """

    def __init__(self, config: KaganConfig, prompts_dir: Path | None = None) -> None:
        """Initialize the prompt loader.

        Args:
            config: The Kagan configuration.
            prompts_dir: Optional custom prompts directory (defaults to .kagan/prompts).
        """
        self._config = config
        self._prompts_dir = prompts_dir or DEFAULT_PROMPTS_DIR

    def get_worker_prompt(self) -> str:
        """Load worker template: .kagan/prompts/worker.md > toml > builtin."""
        # Priority 1: User file override
        user_file = self._prompts_dir / "worker.md"
        if user_file.exists():
            return user_file.read_text()

        # Priority 2: TOML inline config
        if self._config.prompts.worker_system_prompt:
            return self._config.prompts.worker_system_prompt

        # Priority 3: Built-in default
        return _load_builtin_template("iteration.md")

    def get_reviewer_prompt(self) -> str:
        """Load reviewer template: .kagan/prompts/reviewer.md > toml > builtin."""
        # Priority 1: User file override
        user_file = self._prompts_dir / "reviewer.md"
        if user_file.exists():
            return user_file.read_text()

        # Priority 2: TOML inline config
        if self._config.prompts.reviewer_system_prompt:
            return self._config.prompts.reviewer_system_prompt

        # Priority 3: Built-in default
        return _load_builtin_template("review.md")

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

    def get_hat_instructions(self, hat: HatConfig | None) -> str:
        """Load hat role instructions.

        Priority: .kagan/prompts/roles/{hat.prompt_file} > hat.system_prompt

        Args:
            hat: The hat configuration, or None.

        Returns:
            The hat instructions string, or empty string if no hat.
        """
        if hat is None:
            return ""

        # Priority 1: Hat prompt file
        if hat.prompt_file:
            role_file = self._prompts_dir / "roles" / hat.prompt_file
            if role_file.exists():
                return role_file.read_text()
            # Try without extension if provided without .md
            if not hat.prompt_file.endswith(".md"):
                role_file = self._prompts_dir / "roles" / f"{hat.prompt_file}.md"
                if role_file.exists():
                    return role_file.read_text()

        # Priority 2: Inline system_prompt
        return hat.system_prompt


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

    # Fallback inline templates
    if filename == "iteration.md":
        return _get_fallback_worker_template()
    elif filename == "review.md":
        return _get_fallback_reviewer_template()

    return ""


def _get_fallback_worker_template() -> str:
    """Get fallback worker template when file not found."""
    return """# Iteration {iteration} of {max_iterations}

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


def _get_fallback_reviewer_template() -> str:
    """Get fallback reviewer template when file not found."""
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
