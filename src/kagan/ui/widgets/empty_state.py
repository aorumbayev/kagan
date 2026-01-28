"""Empty state widget for planner screen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static

from kagan.constants import BOX_DRAWING, PLANNER_EXAMPLE_PROMPTS, PLANNER_PRO_TIPS

if TYPE_CHECKING:
    from textual.app import ComposeResult


class EmptyState(Widget):
    """Empty state widget showing tutorial content for planner screen."""

    DEFAULT_CLASSES = "empty-state"

    def compose(self) -> ComposeResult:
        """Compose the empty state layout."""
        yield Static("Ready to Build?", classes="empty-state-title")

        with Horizontal(classes="empty-state-cards"):
            # Left card: Example Prompts
            with Vertical(classes="empty-state-card"):
                yield Static("Examples", classes="empty-card-title")
                for prompt in PLANNER_EXAMPLE_PROMPTS:
                    yield Static(
                        f"{BOX_DRAWING['BULLET']} {prompt}",
                        classes="card-item",
                    )

            # Right card: Process
            with Vertical(classes="empty-state-card"):
                yield Static("Process", classes="empty-card-title")
                yield Static(
                    f"{BOX_DRAWING['BULLET']} 1. AI analyzes your requirements",
                    classes="card-item",
                )
                yield Static(
                    f"{BOX_DRAWING['BULLET']} 2. Asks clarifying questions",
                    classes="card-item",
                )
                yield Static(
                    f"{BOX_DRAWING['BULLET']} 3. Generates structured tickets",
                    classes="card-item",
                )
                yield Static(
                    f"{BOX_DRAWING['BULLET']} 4. You review & approve",
                    classes="card-item",
                )

        # Bottom card: Pro Tips (full width)
        with Vertical(classes="empty-state-card empty-state-tips"):
            yield Static("Tips", classes="empty-card-title")
            for tip in PLANNER_PRO_TIPS:
                yield Static(
                    f"{BOX_DRAWING['BULLET']} {tip}",
                    classes="card-item",
                )

        yield Static(
            "Begin by describing your feature below",
            classes="empty-state-footer",
        )
