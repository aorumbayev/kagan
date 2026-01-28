"""Session manager for tmux-backed ticket workflows."""

from __future__ import annotations

import contextlib
import subprocess
from typing import TYPE_CHECKING

from kagan.config import AgentConfig, get_os_value
from kagan.sessions.context import build_context
from kagan.sessions.tmux import TmuxError, run_tmux

if TYPE_CHECKING:
    from pathlib import Path

    from kagan.config import KaganConfig
    from kagan.database.manager import StateManager
    from kagan.database.models import Ticket


class SessionManager:
    """Manages tmux sessions for tickets."""

    def __init__(self, project_root: Path, state: StateManager, config: KaganConfig) -> None:
        self._root = project_root
        self._state = state
        self._config = config

    async def create_session(self, ticket: Ticket, worktree_path: Path) -> str:
        """Create tmux session with full context injection."""
        session_name = f"kagan-{ticket.id}"

        await run_tmux(
            "new-session",
            "-d",
            "-s",
            session_name,
            "-c",
            str(worktree_path),
            "-e",
            f"KAGAN_TICKET_ID={ticket.id}",
            "-e",
            f"KAGAN_TICKET_TITLE={ticket.title}",
            "-e",
            f"KAGAN_WORKTREE_PATH={worktree_path}",
            "-e",
            f"KAGAN_PROJECT_ROOT={self._root}",
        )

        await self._write_context_files(ticket, worktree_path)
        await self._state.mark_session_active(ticket.id, True)

        # Auto-launch the agent's interactive CLI in the session
        agent_config = self._get_agent_config(ticket)
        interactive_cmd = get_os_value(agent_config.interactive_command)
        if interactive_cmd:
            await run_tmux("send-keys", "-t", session_name, interactive_cmd, "Enter")

        return session_name

    def _get_agent_config(self, ticket: Ticket) -> AgentConfig:
        """Get agent config for ticket, with fallback to default."""
        from kagan.config import get_fallback_agent_config
        from kagan.data.builtin_agents import get_builtin_agent

        # Priority 1: ticket's agent_backend
        if ticket.agent_backend:
            if builtin := get_builtin_agent(ticket.agent_backend):
                return builtin.config

        # Priority 2: config's default_worker_agent
        default_agent = self._config.general.default_worker_agent
        if builtin := get_builtin_agent(default_agent):
            return builtin.config

        # Priority 3: fallback
        return get_fallback_agent_config()

    def attach_session(self, ticket_id: str) -> None:
        """Attach to session (blocks until detach, then returns to TUI)."""
        subprocess.run(["tmux", "attach-session", "-t", f"kagan-{ticket_id}"])

    async def session_exists(self, ticket_id: str) -> bool:
        """Check if session exists."""
        try:
            output = await run_tmux("list-sessions", "-F", "#{session_name}")
            return f"kagan-{ticket_id}" in output.split("\n")
        except TmuxError:
            # No tmux server running = no sessions exist
            return False

    async def kill_session(self, ticket_id: str) -> None:
        """Kill session and mark inactive."""
        with contextlib.suppress(TmuxError):
            await run_tmux("kill-session", "-t", f"kagan-{ticket_id}")
        await self._state.mark_session_active(ticket_id, False)

    async def _write_context_files(self, ticket: Ticket, worktree_path: Path) -> None:
        """Create context and configuration files in worktree."""
        wt_kagan = worktree_path / ".kagan"
        wt_kagan.mkdir(exist_ok=True)
        (wt_kagan / "CONTEXT.md").write_text(build_context(ticket))

        claude_dir = worktree_path / ".claude"
        claude_dir.mkdir(exist_ok=True)
        (claude_dir / "settings.local.json").write_text(
            '{"mcpServers": {"kagan": {"command": "kagan", "args": ["mcp"]}}}'
        )

        agents_md = self._root / "AGENTS.md"
        wt_agents = worktree_path / "AGENTS.md"
        if agents_md.exists() and not wt_agents.exists():
            wt_agents.symlink_to(agents_md)
