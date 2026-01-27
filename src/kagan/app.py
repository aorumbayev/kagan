"""Main Kagan TUI application."""

from __future__ import annotations

import shlex
from pathlib import Path
from shutil import which

from textual.app import App
from textual.binding import Binding
from textual.timer import Timer

from kagan.agents import AgentManager, Scheduler, WorktreeManager
from kagan.config import KaganConfig, get_os_value
from kagan.constants import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH, DEFAULT_LOCK_PATH
from kagan.data.builtin_agents import get_builtin_agent
from kagan.database import KnowledgeBase, StateManager
from kagan.git_utils import has_git_repo, init_git_repo
from kagan.lock import InstanceLock, exit_if_already_running
from kagan.messages import TicketChanged
from kagan.theme import KAGAN_THEME
from kagan.ui.screens.agent_missing import AgentMissingScreen, MissingAgentInfo
from kagan.ui.screens.kanban import KanbanScreen


class KaganApp(App):
    """Kagan TUI Application - AI-powered Kanban board."""

    TITLE = "ᘚᘛ KAGAN"
    CSS_PATH = "styles/kagan.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "command_palette", "Help", show=True),
        Binding("ctrl+p", "command_palette", show=False),  # Hide from footer, still works
    ]

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        config_path: str = DEFAULT_CONFIG_PATH,
        lock_path: str | None = DEFAULT_LOCK_PATH,
    ):
        super().__init__()
        # Register the Kagan theme before anything else
        self.register_theme(KAGAN_THEME)
        self.theme = "kagan"

        self.db_path = Path(db_path)
        self.config_path = Path(config_path)
        self.lock_path = Path(lock_path) if lock_path else None
        self._state_manager: StateManager | None = None
        self._knowledge_base: KnowledgeBase | None = None
        self._agent_manager: AgentManager | None = None
        self._worktree_manager: WorktreeManager | None = None
        self._scheduler: Scheduler | None = None
        self._scheduler_timer: Timer | None = None
        self._instance_lock: InstanceLock | None = None
        self.config: KaganConfig = KaganConfig()

    @property
    def state_manager(self) -> StateManager:
        assert self._state_manager is not None
        return self._state_manager

    @property
    def knowledge_base(self) -> KnowledgeBase:
        assert self._knowledge_base is not None
        return self._knowledge_base

    @property
    def agent_manager(self) -> AgentManager:
        assert self._agent_manager is not None
        return self._agent_manager

    @property
    def worktree_manager(self) -> WorktreeManager:
        assert self._worktree_manager is not None
        return self._worktree_manager

    @property
    def scheduler(self) -> Scheduler:
        assert self._scheduler is not None
        return self._scheduler

    async def on_mount(self) -> None:
        """Initialize app on mount."""
        # Check for first boot (no config.toml file)
        # Note: .kagan folder may already exist (created by lock file),
        # so we check for config.toml specifically
        if not self.config_path.exists():
            from kagan.ui.screens.welcome import WelcomeScreen

            await self.push_screen(WelcomeScreen())
            return  # _continue_after_welcome will be called when welcome finishes

        await self._initialize_app()

    async def _initialize_app(self) -> None:
        """Initialize all app components."""
        self.config = KaganConfig.load(self.config_path)
        self.log("Config loaded", path=str(self.config_path))

        missing_agents = self._get_missing_agents()
        if missing_agents:
            await self.push_screen(AgentMissingScreen(missing_agents))
            return

        auto_start = self.config.general.auto_start
        max_agents = self.config.general.max_concurrent_agents
        self.log.debug("Config settings", auto_start=auto_start, max_agents=max_agents)

        project_root = self.config_path.parent.parent
        if not has_git_repo(project_root):
            base_branch = self.config.general.default_base_branch
            if init_git_repo(project_root, base_branch):
                self.log("Initialized git repository", base_branch=base_branch)
            else:
                self.log.warning("Failed to initialize git repository", path=str(project_root))

        self._state_manager = StateManager(self.db_path)
        await self._state_manager.initialize()
        self.log("Database initialized", path=str(self.db_path))

        self._knowledge_base = KnowledgeBase(self._state_manager.connection)

        self._agent_manager = AgentManager()
        # Project root is the parent of .kagan directory (where config lives)
        self._worktree_manager = WorktreeManager(repo_root=project_root)

        self._scheduler = Scheduler(
            state_manager=self._state_manager,
            agent_manager=self._agent_manager,
            worktree_manager=self._worktree_manager,
            config=self.config,
            on_ticket_changed=self._notify_ticket_changed_to_screen,
        )

        if self.config.general.auto_start:
            self.log("auto_start enabled, starting scheduler interval")
            self._scheduler_timer = self.set_interval(5.0, self._scheduler_tick)

        await self.push_screen(KanbanScreen())
        self.log("KanbanScreen pushed, app ready")

    def _continue_after_welcome(self) -> None:
        """Called when welcome screen completes to continue app initialization."""
        self.call_later(self._run_init_after_welcome)

    async def _run_init_after_welcome(self) -> None:
        """Run initialization after welcome screen."""
        await self._initialize_app()

    async def _scheduler_tick(self) -> None:
        """Called periodically to run scheduler tick."""
        await self.scheduler.tick()

    def _notify_ticket_changed_to_screen(self) -> None:
        """Called by scheduler when a ticket status changes.

        Posts TicketChanged message to the current screen for UI refresh.
        Note: This is a callback, NOT a Textual message handler. The name
        intentionally avoids the 'on_<message>' pattern to prevent Textual
        from treating it as a handler (which would cause infinite loops).
        """
        if self.screen:
            self.screen.post_message(TicketChanged())

    async def on_unmount(self) -> None:
        """Clean up on unmount."""
        await self.cleanup()

    async def cleanup(self) -> None:
        """Terminate all agents and close resources."""
        # Stop scheduler timer
        if self._scheduler_timer:
            self._scheduler_timer.stop()
            self._scheduler_timer = None
        if self._agent_manager:
            await self._agent_manager.terminate_all()
        if self._state_manager:
            await self._state_manager.close()
        if self._instance_lock:
            self._instance_lock.release()

    def _get_missing_agents(self) -> list[MissingAgentInfo]:
        selected = [
            self.config.general.default_worker_agent,
            self.config.general.default_review_agent,
            self.config.general.default_requirements_agent,
        ]

        missing: list[MissingAgentInfo] = []
        seen: set[str] = set()

        for agent_name in selected:
            if agent_name in seen:
                continue
            seen.add(agent_name)

            agent_config = self.config.get_agent(agent_name)
            if agent_config is None:
                continue

            run_command = get_os_value(agent_config.run_command)
            if not run_command:
                missing.append(
                    MissingAgentInfo(
                        name=agent_config.name,
                        short_name=agent_config.short_name,
                        run_command="",
                        install_command=None,
                    )
                )
                continue

            command_parts = shlex.split(run_command)
            if not command_parts or which(command_parts[0]) is None:
                builtin = get_builtin_agent(agent_name)
                missing.append(
                    MissingAgentInfo(
                        name=agent_config.name,
                        short_name=agent_config.short_name,
                        run_command=run_command,
                        install_command=builtin.install_command if builtin else None,
                    )
                )

        return missing


def run() -> None:
    """Run the Kagan application."""
    # Check for existing instance before starting
    instance_lock = exit_if_already_running()

    app = KaganApp()
    app._instance_lock = instance_lock
    try:
        app.run()
    finally:
        instance_lock.release()


if __name__ == "__main__":
    run()
