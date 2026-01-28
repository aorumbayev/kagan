"""Troubleshooting screen shown for pre-flight check failures."""

from __future__ import annotations

import platform
import shlex
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Middle, VerticalScroll
from textual.widgets import Footer, Static

from kagan.theme import KAGAN_THEME
from kagan.ui.screens.welcome import KAGAN_LOGO

if TYPE_CHECKING:
    from kagan.config import AgentConfig


class IssueType(Enum):
    """Types of pre-flight issues."""

    WINDOWS_OS = "windows_os"
    INSTANCE_LOCKED = "instance_locked"
    TMUX_MISSING = "tmux_missing"
    AGENT_MISSING = "agent_missing"


class IssueSeverity(Enum):
    """Severity levels for issues."""

    BLOCKING = "blocking"
    WARNING = "warning"


@dataclass(frozen=True)
class IssuePreset:
    """Predefined issue configuration."""

    type: IssueType
    severity: IssueSeverity
    icon: str
    title: str
    message: str
    hint: str
    url: str | None = None


# Predefined issue messages
ISSUE_PRESETS: dict[IssueType, IssuePreset] = {
    IssueType.WINDOWS_OS: IssuePreset(
        type=IssueType.WINDOWS_OS,
        severity=IssueSeverity.BLOCKING,
        icon="[!]",
        title="Windows Not Supported",
        message=(
            "Kagan does not currently support Windows.\n"
            "We recommend using WSL2 (Windows Subsystem for Linux)."
        ),
        hint="Install WSL2 and run Kagan from there",
        url="https://github.com/aorumbayev/kagan",
    ),
    IssueType.INSTANCE_LOCKED: IssuePreset(
        type=IssueType.INSTANCE_LOCKED,
        severity=IssueSeverity.BLOCKING,
        icon="[!]",
        title="Another Instance Running",
        message=(
            "Another Kagan instance is already running in this folder.\n"
            "Please return to that window or close it before starting."
        ),
        hint="Close the other instance and try again",
    ),
    IssueType.TMUX_MISSING: IssuePreset(
        type=IssueType.TMUX_MISSING,
        severity=IssueSeverity.BLOCKING,
        icon="[!]",
        title="tmux Not Available",
        message=(
            "tmux is required for PAIR mode but was not found in PATH.\n"
            "PAIR mode uses tmux for interactive agent sessions."
        ),
        hint="Install tmux: brew install tmux (macOS) or apt install tmux (Linux)",
    ),
    IssueType.AGENT_MISSING: IssuePreset(
        type=IssueType.AGENT_MISSING,
        severity=IssueSeverity.BLOCKING,
        icon="[!]",
        title="Default Agent Not Installed",
        message="The default agent was not found in PATH.",
        hint="Install the agent to continue",
    ),
}


@dataclass(frozen=True)
class DetectedIssue:
    """A detected pre-flight issue with optional runtime details."""

    preset: IssuePreset
    details: str | None = None


@dataclass
class PreflightResult:
    """Result of pre-flight checks."""

    issues: list[DetectedIssue]

    @property
    def has_blocking_issues(self) -> bool:
        """Check if any blocking issues were detected."""
        return any(issue.preset.severity == IssueSeverity.BLOCKING for issue in self.issues)


def _check_windows() -> DetectedIssue | None:
    """Check if running on Windows."""
    if platform.system() == "Windows":
        return DetectedIssue(preset=ISSUE_PRESETS[IssueType.WINDOWS_OS])
    return None


def _check_tmux() -> DetectedIssue | None:
    """Check if tmux is available."""
    if shutil.which("tmux") is None:
        return DetectedIssue(preset=ISSUE_PRESETS[IssueType.TMUX_MISSING])
    return None


def _check_agent(
    agent_command: str,
    agent_name: str,
    install_command: str | None,
) -> DetectedIssue | None:
    """Check if the configured agent is available."""
    # Parse command to get the executable
    try:
        parts = shlex.split(agent_command)
        executable = parts[0] if parts else agent_command
    except ValueError:
        executable = agent_command

    if shutil.which(executable) is None:
        # Create a customized preset with agent-specific details
        preset = IssuePreset(
            type=IssueType.AGENT_MISSING,
            severity=IssueSeverity.BLOCKING,
            icon="[!]",
            title="Default Agent Not Installed",
            message=f"The default agent ({agent_name}) was not found in PATH.",
            hint=(
                f"Install: {install_command}"
                if install_command
                else f"Ensure '{executable}' is available in PATH"
            ),
        )
        return DetectedIssue(preset=preset, details=agent_name)
    return None


def detect_issues(
    *,
    check_lock: bool = False,
    lock_acquired: bool = True,
    agent_config: AgentConfig | None = None,
    agent_name: str = "Claude Code",
    agent_install_command: str | None = None,
) -> PreflightResult:
    """Run all pre-flight checks and return detected issues.

    Args:
        check_lock: Whether to check instance lock status.
        lock_acquired: If check_lock is True, whether the lock was acquired.
        agent_config: Optional agent configuration to check.
        agent_name: Display name of the agent to check.
        agent_install_command: Installation command for the agent.

    Returns:
        PreflightResult containing all detected issues.
    """
    issues: list[DetectedIssue] = []

    # 1. Windows check (exit early - nothing else matters)
    windows_issue = _check_windows()
    if windows_issue:
        return PreflightResult(issues=[windows_issue])

    # 2. Instance lock check
    if check_lock and not lock_acquired:
        issues.append(DetectedIssue(preset=ISSUE_PRESETS[IssueType.INSTANCE_LOCKED]))

    # 3. tmux check
    tmux_issue = _check_tmux()
    if tmux_issue:
        issues.append(tmux_issue)

    # 4. Agent check
    if agent_config:
        from kagan.config import get_os_value

        run_command = get_os_value(agent_config.interactive_command)
        if run_command:
            agent_issue = _check_agent(
                agent_command=run_command,
                agent_name=agent_name,
                install_command=agent_install_command,
            )
            if agent_issue:
                issues.append(agent_issue)

    return PreflightResult(issues=issues)


class IssueCard(Static):
    """Widget displaying a single issue."""

    def __init__(self, issue: DetectedIssue) -> None:
        super().__init__()
        self._issue = issue

    def compose(self) -> ComposeResult:
        preset = self._issue.preset
        yield Static(f"{preset.icon} {preset.title}", classes="issue-card-title")
        yield Static(preset.message, classes="issue-card-message")
        yield Static(f"Hint: {preset.hint}", classes="issue-card-hint")
        if preset.url:
            yield Static(f"More info: {preset.url}", classes="issue-card-url")


class TroubleshootingApp(App):
    """Standalone app shown when pre-flight checks fail."""

    TITLE = "KAGAN"
    CSS_PATH = str(Path(__file__).resolve().parents[2] / "styles" / "kagan.tcss")

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        Binding("enter", "quit", "Quit"),
    ]

    def __init__(self, issues: list[DetectedIssue]) -> None:
        super().__init__()
        self._issues = issues
        self.register_theme(KAGAN_THEME)
        self.theme = "kagan"

    def compose(self) -> ComposeResult:
        blocking_count = sum(
            1 for issue in self._issues if issue.preset.severity == IssueSeverity.BLOCKING
        )

        with Container(id="troubleshoot-container"):
            with Middle():
                with Center():
                    with Static(id="troubleshoot-card"):
                        yield Static(KAGAN_LOGO, id="troubleshoot-logo")
                        yield Static("Startup Issues Detected", id="troubleshoot-title")
                        plural = "s" if blocking_count != 1 else ""
                        yield Static(
                            f"{blocking_count} blocking issue{plural} found",
                            id="troubleshoot-count",
                        )
                        with VerticalScroll(id="troubleshoot-issues"):
                            for issue in self._issues:
                                with Container(classes="issue-card"):
                                    yield IssueCard(issue)
                        yield Static(
                            "Resolve issues and restart Kagan",
                            id="troubleshoot-resolve-hint",
                        )
                        yield Static("Press q to exit", id="troubleshoot-exit-hint")
        yield Footer()
