"""Troubleshooting screen shown when a selected agent is not installed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Center, Container, Middle
from textual.screen import Screen
from textual.widgets import Footer, Static

from kagan.ui.widgets.header import KaganHeader

if TYPE_CHECKING:
    from textual.app import ComposeResult


@dataclass(frozen=True)
class MissingAgentInfo:
    """Details about an agent missing from the user's system."""

    name: str
    short_name: str
    run_command: str
    install_command: str | None


class AgentMissingScreen(Screen):
    """Screen shown when one or more selected agents are missing."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        Binding("enter", "quit", "Quit"),
    ]

    def __init__(self, missing_agents: list[MissingAgentInfo]) -> None:
        super().__init__()
        self._missing_agents = missing_agents

    def compose(self) -> ComposeResult:
        yield KaganHeader()
        with Container(id="agent-missing-container"):
            with Middle():
                with Center():
                    with Static(id="agent-missing-card"):
                        yield Static("Agent Not Installed", id="agent-missing-title")
                        yield Static(self._build_message(), id="agent-missing-message")
                        yield Static(
                            "Install the missing agent(s), then restart the Kagan TUI.",
                            id="agent-missing-hint",
                        )
        yield Footer()

    def _build_message(self) -> str:
        lines = [
            "One or more selected agents are not available on this system.",
            "",
            "Missing agents:",
        ]

        for agent in self._missing_agents:
            lines.append(f"- {agent.name} ({agent.short_name})")
            if agent.install_command:
                lines.append(f"  Install: {agent.install_command}")
            elif agent.run_command:
                lines.append(f"  Install: Ensure '{agent.run_command}' is available in PATH.")
            else:
                lines.append("  Install: Configure a valid run command for this agent.")
            lines.append("")

        return "\n".join(lines).rstrip()
