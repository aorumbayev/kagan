"""Tests for SessionManager with mock tmux."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from kagan.config import KaganConfig
from kagan.database.models import TicketCreate
from kagan.sessions.manager import SessionManager


@pytest.fixture
def mock_tmux(monkeypatch):
    """Intercept tmux subprocess calls."""
    sessions: dict[str, dict[str, object]] = {}

    async def fake_run_tmux(*args: str) -> str:
        command = args[0]
        if command == "new-session":
            name = args[args.index("-s") + 1]
            cwd = args[args.index("-c") + 1]
            env: dict[str, str] = {}
            for idx, value in enumerate(args):
                if value == "-e" and idx + 1 < len(args):
                    key, _, env_value = args[idx + 1].partition("=")
                    env[key] = env_value
            sessions[name] = {"cwd": cwd, "env": env, "sent_keys": []}
            return ""
        if command == "send-keys":
            name = args[args.index("-t") + 1]
            # Capture the text sent (args after -t name, excluding "Enter")
            key_text = args[args.index("-t") + 2]
            if name in sessions:
                sessions[name]["sent_keys"].append(key_text)
            return ""
        if command == "list-sessions":
            return "\n".join(sorted(sessions.keys()))
        if command == "kill-session":
            name = args[args.index("-t") + 1]
            sessions.pop(name, None)
            return ""
        return ""

    monkeypatch.setattr("kagan.sessions.manager.run_tmux", fake_run_tmux)
    return sessions


class TestSessionManager:
    """Session manager behavior tests."""

    async def test_create_session_writes_context(self, state_manager, mock_tmux, tmp_path: Path):
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()
        (project_root / "AGENTS.md").write_text("Agents")

        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Add login",
                description="Implement OAuth",
                acceptance_criteria=["Tests pass"],
                check_command="pytest tests/",
            )
        )
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        session_name = await manager.create_session(ticket, worktree_path)

        assert session_name in mock_tmux
        env = mock_tmux[session_name]["env"]
        assert env["KAGAN_TICKET_ID"] == ticket.id
        assert env["KAGAN_TICKET_TITLE"] == ticket.title
        assert env["KAGAN_WORKTREE_PATH"] == str(worktree_path)
        assert env["KAGAN_PROJECT_ROOT"] == str(project_root)

        context_path = worktree_path / ".kagan-context" / "CONTEXT.md"
        assert context_path.exists()
        context = context_path.read_text()
        assert ticket.id in context
        assert "Tests pass" in context

        # Check .mcp.json is created (works for both Claude Code and OpenCode)
        mcp_config_path = worktree_path / ".mcp.json"
        assert mcp_config_path.exists()
        import json

        mcp_config = json.loads(mcp_config_path.read_text())
        assert "mcpServers" in mcp_config
        assert "kagan" in mcp_config["mcpServers"]
        assert mcp_config["mcpServers"]["kagan"]["command"] == "kagan"
        assert mcp_config["mcpServers"]["kagan"]["args"] == ["mcp"]

        agents_link = worktree_path / "AGENTS.md"
        assert agents_link.exists()

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.session_active is True

    async def test_create_session_sends_startup_prompt(
        self, state_manager, mock_tmux, tmp_path: Path
    ):
        """Test that startup prompt is embedded in launch command."""
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        ticket = await state_manager.create_ticket(
            TicketCreate(title="Test task", description="Do something useful")
        )
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)

        # Check that send-keys was called with launch command containing prompt
        session_name = f"kagan-{ticket.id}"
        assert session_name in mock_tmux
        sent_keys = mock_tmux[session_name].get("sent_keys", [])
        # Should have single launch command with embedded prompt
        assert len(sent_keys) >= 1
        launch_cmd = sent_keys[0]  # Launch command includes the prompt
        assert ticket.id in launch_cmd
        assert "Test task" in launch_cmd
        assert "kagan_get_context" in launch_cmd
        # Should start with claude (default agent)
        assert launch_cmd.startswith("claude ")

    async def test_session_exists_and_kill(self, state_manager, mock_tmux, tmp_path: Path):
        project_root = tmp_path / "project"
        worktree_path = tmp_path / "worktree"
        project_root.mkdir()
        worktree_path.mkdir()

        ticket = await state_manager.create_ticket(TicketCreate(title="Work"))
        config = KaganConfig()
        manager = SessionManager(project_root, state_manager, config)

        await manager.create_session(ticket, worktree_path)
        assert await manager.session_exists(ticket.id) is True

        await manager.kill_session(ticket.id)
        assert await manager.session_exists(ticket.id) is False

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.session_active is False
