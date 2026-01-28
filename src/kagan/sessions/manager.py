"""Session manager for tmux-backed ticket workflows."""

from __future__ import annotations

import contextlib
import json
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

        # Auto-launch the agent's interactive CLI with the startup prompt
        agent_config = self._get_agent_config(ticket)
        startup_prompt = self._build_startup_prompt(ticket)
        launch_cmd = self._build_launch_command(agent_config, startup_prompt)
        if launch_cmd:
            await run_tmux("send-keys", "-t", session_name, launch_cmd, "Enter")

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

    def _build_launch_command(self, agent_config: AgentConfig, prompt: str) -> str | None:
        """Build CLI launch command with prompt for the agent."""
        import shlex

        base_cmd = get_os_value(agent_config.interactive_command)
        if not base_cmd:
            return None

        escaped_prompt = shlex.quote(prompt)

        # Agent-specific command formats
        if agent_config.short_name == "claude":
            # claude "prompt"
            return f"{base_cmd} {escaped_prompt}"
        elif agent_config.short_name == "opencode":
            # opencode --prompt "prompt"
            return f"{base_cmd} --prompt {escaped_prompt}"
        else:
            # Fallback: just run the base command (no auto-prompt)
            return base_cmd

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
        wt_kagan = worktree_path / ".kagan-context"
        wt_kagan.mkdir(exist_ok=True)
        (wt_kagan / "CONTEXT.md").write_text(build_context(ticket))

        # Create .mcp.json at worktree root (works for both Claude Code and OpenCode)
        self._write_mcp_config(worktree_path)

        # Create CLAUDE.md at worktree root with task instructions
        # Claude Code auto-reads this file on startup
        claude_md = worktree_path / "CLAUDE.md"
        if not claude_md.exists():
            claude_md.write_text(self._build_claude_md(ticket))

        agents_md = self._root / "AGENTS.md"
        wt_agents = worktree_path / "AGENTS.md"
        if agents_md.exists() and not wt_agents.exists():
            wt_agents.symlink_to(agents_md)

    def _write_mcp_config(self, worktree_path: Path) -> None:
        """Create .mcp.json at worktree root (works for both Claude Code and OpenCode)."""
        mcp_config = {
            "mcpServers": {
                "kagan": {
                    "command": "kagan",
                    "args": ["mcp"],
                }
            }
        }
        (worktree_path / ".mcp.json").write_text(json.dumps(mcp_config, indent=2))

    def _build_startup_prompt(self, ticket: Ticket) -> str:
        """Build startup prompt for pair mode."""
        desc = ticket.description or "No description provided."
        return f"""Hello! I'm starting a pair programming session for ticket **{ticket.id}**.

## Task Overview
**Title:** {ticket.title}

**Description:**
{desc}

## Setup Verification
Please confirm you have access to the Kagan MCP tools by calling the `kagan_get_context` tool.
Use ticket_id: `{ticket.id}`.

After confirming MCP access, please:
1. Summarize your understanding of this task
2. Ask me if I'm ready to proceed with the implementation

**Do not start making changes until I confirm I'm ready to proceed.**
"""

    def _build_claude_md(self, ticket: Ticket) -> str:
        """Build CLAUDE.md content for automatic context injection."""
        desc = ticket.description or "No description provided."
        criteria = "\n".join(f"- {c}" for c in ticket.acceptance_criteria) or "- None specified"
        return f"""# Task: {ticket.title}

## Description
{desc}

## Acceptance Criteria
{criteria}

## Instructions
1. Review this task and confirm you understand it
2. Ask the user if they are ready to proceed before making changes
3. Work in this worktree directory only
4. **CRITICAL: Before completion, commit ALL changes with semantic commit messages**
   - Use conventional commits: feat:, fix:, docs:, refactor:, test:, chore:
   - Example: `git commit -m "feat: add user authentication endpoint"`
5. When complete, call the `kagan_request_review` MCP tool to submit for review

## MCP Tools Available
- `kagan_get_context` - Refresh ticket details
- `kagan_update_scratchpad` - Save progress notes
- `kagan_request_review` - Submit work for review
  **IMPORTANT**: Commit your changes BEFORE calling this tool!

## Detach Instructions
When finished working, the user can detach from this session:
- Press `Ctrl+b` then `d` to detach and return to the Kagan board
"""
