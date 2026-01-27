"""Welcome screen for first-boot setup."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.containers import Center, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Label, Select

from kagan.agents.prompt_loader import dump_default_prompts
from kagan.data.builtin_agents import BUILTIN_AGENTS, list_builtin_agents
from kagan.git_utils import get_current_branch, has_git_repo, list_local_branches

if TYPE_CHECKING:
    from textual.app import ComposeResult

# Large block letter ASCII art logo
KAGAN_LOGO = """\
ᘚᘛ  ██╗  ██╗ █████╗  ██████╗  █████╗ ███╗   ██╗  ᘚᘛ
ᘚᘛ  ██║ ██╔╝██╔══██╗██╔════╝ ██╔══██╗████╗  ██║  ᘚᘛ
ᘚᘛ  █████╔╝ ███████║██║  ███╗███████║██╔██╗ ██║  ᘚᘛ
ᘚᘛ  ██╔═██╗ ██╔══██║██║   ██║██╔══██║██║╚██╗██║  ᘚᘛ
ᘚᘛ  ██║  ██╗██║  ██║╚██████╔╝██║  ██║██║ ╚████║  ᘚᘛ
ᘚᘛ  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝  ᘚᘛ"""

DEFAULT_BASE_BRANCHES = ("main", "master", "develop", "trunk")


class WelcomeScreen(Screen):
    """First-boot welcome and configuration screen."""

    BINDINGS = [
        ("escape", "skip", "Continue"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.simple_mode = True
        self._agents = list_builtin_agents()
        self._repo_root = Path.cwd()
        self._has_git_repo = has_git_repo(self._repo_root)
        self._branches = list_local_branches(self._repo_root) if self._has_git_repo else []
        self._default_base_branch = self._get_default_base_branch(self._branches)
        self._branch_options = self._build_branch_options(
            self._branches,
            self._default_base_branch,
        )

    def _build_branch_options(self, branches: list[str], default_branch: str) -> list[str]:
        options: list[str] = []
        for name in (default_branch, *branches, *DEFAULT_BASE_BRANCHES):
            if name not in options:
                options.append(name)
        return options

    def _get_default_base_branch(self, branches: list[str]) -> str:
        if self._has_git_repo:
            current = get_current_branch(self._repo_root)
            if current:
                return current
            for candidate in DEFAULT_BASE_BRANCHES:
                if candidate in branches:
                    return candidate
            if branches:
                return branches[0]
        return "main"

    def compose(self) -> ComposeResult:
        """Compose the welcome screen layout."""
        # Build Select options from agents
        agent_options = [
            (f"{a.config.name} ({a.author})", a.config.short_name) for a in self._agents
        ]
        base_branch_options = [(name, name) for name in self._branch_options]

        with Vertical(id="welcome-container"):
            # Large ASCII art logo
            yield Label(KAGAN_LOGO, id="logo")
            yield Label("Welcome! Let's set up your workspace.", id="subtitle")

            # Mode toggle - centered tab-based toggle using buttons
            with Center(id="mode-toggle"):
                with Horizontal(id="mode-tabs"):
                    yield Button("Simple", id="mode-simple", classes="mode-tab -active")
                    yield Button("Granular", id="mode-granular", classes="mode-tab")

            # Simple mode: single dropdown (using IDs for toggling)
            yield Label(
                "Select your AI coding assistant:",
                classes="section-label",
                id="simple-label",
            )
            yield Select(agent_options, value="claude", id="agent-select")

            # Granular mode: three dropdowns (hidden by default)
            yield Label(
                "Worker Agent (implements tickets):",
                classes="section-label hidden",
                id="worker-label",
            )
            yield Select(agent_options, value="claude", id="worker-select", classes="hidden")

            yield Label(
                "Review Agent (reviews completed work):",
                classes="section-label hidden",
                id="review-label",
            )
            yield Select(agent_options, value="claude", id="review-select", classes="hidden")

            yield Label(
                "Requirements Agent (generates tickets):",
                classes="section-label hidden",
                id="requirements-label",
            )
            yield Select(agent_options, value="claude", id="requirements-select", classes="hidden")

            # Base branch selection
            yield Label(
                "Base branch for worktrees:",
                classes="section-label",
                id="base-branch-label",
            )
            yield Select(
                base_branch_options,
                value=self._default_base_branch,
                id="base-branch-select",
            )

            if not self._has_git_repo:
                yield Label(
                    "No git repo detected. A fresh git repo will be initialized\n"
                    "because Kagan requires git worktrees.",
                    id="git-init-hint",
                    classes="info-label",
                )

            # Auto-start checkbox (enabled by default)
            yield Checkbox(
                "Enable auto-start (agents begin working automatically)",
                id="auto-start",
                value=True,
            )

            # Continue button
            with Center(id="buttons"):
                yield Button("Continue", variant="primary", id="continue-btn")

            # Footer with key bindings
            yield Footer()

    def _on_mode_tab_pressed(self, button_id: str) -> None:
        """Toggle between simple and granular modes."""
        self.simple_mode = button_id == "mode-simple"

        # Update tab button states
        simple_btn = self.query_one("#mode-simple", Button)
        granular_btn = self.query_one("#mode-granular", Button)
        simple_btn.set_class(self.simple_mode, "-active")
        granular_btn.set_class(not self.simple_mode, "-active")

        # Toggle simple mode elements
        self.query_one("#simple-label").set_class(not self.simple_mode, "hidden")
        self.query_one("#agent-select").set_class(not self.simple_mode, "hidden")

        # Toggle granular mode elements
        self.query_one("#worker-label").set_class(self.simple_mode, "hidden")
        self.query_one("#worker-select").set_class(self.simple_mode, "hidden")
        self.query_one("#review-label").set_class(self.simple_mode, "hidden")
        self.query_one("#review-select").set_class(self.simple_mode, "hidden")
        self.query_one("#requirements-label").set_class(self.simple_mode, "hidden")
        self.query_one("#requirements-select").set_class(self.simple_mode, "hidden")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "continue-btn":
            self._save_and_continue()
        elif event.button.id in ("mode-simple", "mode-granular"):
            self._on_mode_tab_pressed(event.button.id)

    def action_skip(self) -> None:
        """Skip setup, use defaults (escape key)."""
        self._save_and_continue()

    def _save_and_continue(self) -> None:
        """Save configuration and continue."""
        auto_start = self.query_one("#auto-start", Checkbox).value
        base_branch_select = self.query_one("#base-branch-select", Select)
        base_branch = str(base_branch_select.value) if base_branch_select.value else "main"

        if self.simple_mode:
            select = self.query_one("#agent-select", Select)
            agent = str(select.value) if select.value else "claude"
            worker = review = requirements = agent
        else:
            worker_sel = self.query_one("#worker-select", Select)
            review_sel = self.query_one("#review-select", Select)
            req_sel = self.query_one("#requirements-select", Select)
            worker = str(worker_sel.value) if worker_sel.value else "claude"
            review = str(review_sel.value) if review_sel.value else "claude"
            requirements = str(req_sel.value) if req_sel.value else "claude"

        self._write_config(worker, review, requirements, auto_start, base_branch)
        self.app.pop_screen()
        self.app.call_later(self._notify_setup_complete)

    def _notify_setup_complete(self) -> None:
        """Notify app that setup is complete and it should continue mounting."""
        if hasattr(self.app, "_continue_after_welcome"):
            self.app._continue_after_welcome()

    def _write_config(
        self,
        worker: str,
        review: str,
        requirements: str,
        auto_start: bool,
        base_branch: str,
    ) -> None:
        """Write config.toml file with correct ACP run commands."""
        kagan_dir = Path(".kagan")
        kagan_dir.mkdir(exist_ok=True)

        # Build agent sections from BUILTIN_AGENTS with correct ACP commands
        agent_sections = []
        for key, agent in BUILTIN_AGENTS.items():
            cfg = agent.config
            run_cmd = cfg.run_command.get("*", key)
            agent_sections.append(f'''[agents.{key}]
identity = "{cfg.identity}"
name = "{cfg.name}"
short_name = "{cfg.short_name}"
run_command."*" = "{run_cmd}"
active = true''')

        config_content = f'''# Kagan Configuration
# Generated by first-boot setup

[general]
auto_start = {str(auto_start).lower()}
default_base_branch = "{base_branch}"
default_worker_agent = "{worker}"
default_review_agent = "{review}"
default_requirements_agent = "{requirements}"

{chr(10).join(agent_sections)}
'''

        (kagan_dir / "config.toml").write_text(config_content)

        # Dump default prompt templates for user customization
        dump_default_prompts(kagan_dir / "prompts")
