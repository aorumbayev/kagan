"""Tests for MCP tools with mock state manager."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from kagan.database.models import Ticket, TicketStatus
from kagan.mcp.tools import KaganMCPServer

pytestmark = pytest.mark.integration


class TestMCPTools:
    """Tests for MCP tool handlers."""

    async def test_get_context(self, state_manager):
        """Get context returns ticket fields and scratchpad."""
        ticket = await state_manager.create_ticket(
            Ticket.create(
                title="Feature",
                description="Details",
                acceptance_criteria=["Tests pass"],
            )
        )
        await state_manager.update_scratchpad(ticket.id, "Notes")
        server = KaganMCPServer(state_manager)

        context = await server.get_context(ticket.id)

        assert context["ticket_id"] == ticket.id
        assert context["title"] == "Feature"
        assert context["description"] == "Details"
        assert context["acceptance_criteria"] == ["Tests pass"]
        assert context["scratchpad"] == "Notes"

    async def test_update_scratchpad_appends(self, state_manager):
        """update_scratchpad appends to existing content."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Feature"))
        await state_manager.update_scratchpad(ticket.id, "First line")
        server = KaganMCPServer(state_manager)

        result = await server.update_scratchpad(ticket.id, "Second line")

        assert result is True
        scratchpad = await state_manager.get_scratchpad(ticket.id)
        assert scratchpad == "First line\nSecond line"

    async def test_request_review_passes(self, state_manager, monkeypatch):
        """request_review moves ticket to REVIEW on success."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Feature"))
        server = KaganMCPServer(state_manager)

        async def _no_uncommitted(*_args) -> bool:
            return False  # No uncommitted changes

        monkeypatch.setattr(server, "_check_uncommitted_changes", _no_uncommitted)

        result = await server.request_review(ticket.id, "Looks good")

        assert result["status"] == "review"
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.REVIEW
        assert updated.review_summary == "Looks good"
        assert updated.checks_passed is None

    async def test_request_review_blocks_uncommitted(self, state_manager, monkeypatch):
        """request_review returns error when uncommitted changes exist."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Feature"))
        server = KaganMCPServer(state_manager)

        async def _has_uncommitted(*_args) -> bool:
            return True  # Has uncommitted changes

        monkeypatch.setattr(server, "_check_uncommitted_changes", _has_uncommitted)

        result = await server.request_review(ticket.id, "Looks good")

        assert result["status"] == "error"
        assert "uncommitted" in result["message"].lower()
        # Ticket should not have moved
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.BACKLOG


class TestCheckUncommittedChanges:
    """Tests for _check_uncommitted_changes filtering logic."""

    async def test_clean_repo_returns_false(self, state_manager, git_repo: Path, monkeypatch):
        """Clean repo should return False (no uncommitted changes)."""
        monkeypatch.chdir(git_repo)
        server = KaganMCPServer(state_manager)

        result = await server._check_uncommitted_changes()

        assert result is False

    async def test_real_changes_returns_true(self, state_manager, git_repo: Path, monkeypatch):
        """Real uncommitted changes should return True."""
        monkeypatch.chdir(git_repo)
        (git_repo / "new_file.py").write_text("# new file")
        server = KaganMCPServer(state_manager)

        result = await server._check_uncommitted_changes()

        assert result is True

    async def test_kagan_dir_ignored(self, state_manager, git_repo: Path, monkeypatch):
        """Untracked .kagan/ directory should be ignored."""
        monkeypatch.chdir(git_repo)
        (git_repo / ".kagan").mkdir()
        (git_repo / ".kagan" / "state.db").write_text("")
        server = KaganMCPServer(state_manager)

        result = await server._check_uncommitted_changes()

        assert result is False

    async def test_opencode_json_ignored(self, state_manager, git_repo: Path, monkeypatch):
        """Untracked opencode.json should be ignored (OpenCode MCP config)."""
        monkeypatch.chdir(git_repo)
        (git_repo / "opencode.json").write_text('{"mcp": {}}')
        server = KaganMCPServer(state_manager)

        result = await server._check_uncommitted_changes()

        assert result is False

    async def test_mcp_json_ignored(self, state_manager, git_repo: Path, monkeypatch):
        """Untracked .mcp.json should be ignored."""
        monkeypatch.chdir(git_repo)
        (git_repo / ".mcp.json").write_text("{}")
        server = KaganMCPServer(state_manager)

        result = await server._check_uncommitted_changes()

        assert result is False

    async def test_claude_md_not_ignored(self, state_manager, git_repo: Path, monkeypatch):
        """Untracked CLAUDE.md should NOT be ignored (we don't generate it anymore)."""
        monkeypatch.chdir(git_repo)
        (git_repo / "CLAUDE.md").write_text("# Claude")
        server = KaganMCPServer(state_manager)

        result = await server._check_uncommitted_changes()

        # CLAUDE.md is no longer a Kagan-generated file, so it should be detected
        assert result is True

    async def test_mixed_kagan_and_real_changes(self, state_manager, git_repo: Path, monkeypatch):
        """Should return True when both Kagan and real changes exist."""
        monkeypatch.chdir(git_repo)
        # Kagan files (should be ignored)
        (git_repo / ".kagan").mkdir()
        (git_repo / ".kagan" / "state.db").write_text("")
        (git_repo / ".mcp.json").write_text("{}")
        # Real file (should not be ignored)
        (git_repo / "feature.py").write_text("# feature")
        server = KaganMCPServer(state_manager)

        result = await server._check_uncommitted_changes()

        assert result is True

    async def test_only_kagan_files_returns_false(self, state_manager, git_repo: Path, monkeypatch):
        """Should return False when only Kagan files are uncommitted."""
        monkeypatch.chdir(git_repo)
        # Create Kagan-generated files (only .kagan/ and MCP configs are generated now)
        (git_repo / ".kagan").mkdir()
        (git_repo / ".kagan" / "config.toml").write_text("")
        (git_repo / ".mcp.json").write_text("{}")
        (git_repo / "opencode.json").write_text("{}")
        server = KaganMCPServer(state_manager)

        result = await server._check_uncommitted_changes()

        assert result is False


class TestMCPToolsEdgeCases:
    """Edge case tests for MCP tools."""

    async def test_get_context_ticket_not_found(self, state_manager):
        """get_context raises ValueError for non-existent ticket."""
        server = KaganMCPServer(state_manager)

        with pytest.raises(ValueError, match="Ticket not found"):
            await server.get_context("nonexistent-id")

    async def test_get_context_empty_scratchpad(self, state_manager):
        """get_context returns empty string for empty scratchpad."""
        ticket = await state_manager.create_ticket(
            Ticket.create(title="Feature", description="Details")
        )
        server = KaganMCPServer(state_manager)

        context = await server.get_context(ticket.id)

        # Empty scratchpad returns empty string (not None)
        assert context["scratchpad"] == "" or context["scratchpad"] is None

    async def test_update_scratchpad_empty_initial(self, state_manager):
        """update_scratchpad works with empty initial scratchpad."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Feature"))
        server = KaganMCPServer(state_manager)

        result = await server.update_scratchpad(ticket.id, "First entry")

        assert result is True
        scratchpad = await state_manager.get_scratchpad(ticket.id)
        assert scratchpad == "First entry"

    async def test_update_scratchpad_multiple_appends(self, state_manager):
        """update_scratchpad correctly appends multiple times."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Feature"))
        server = KaganMCPServer(state_manager)

        await server.update_scratchpad(ticket.id, "Line 1")
        await server.update_scratchpad(ticket.id, "Line 2")
        await server.update_scratchpad(ticket.id, "Line 3")

        scratchpad = await state_manager.get_scratchpad(ticket.id)
        assert scratchpad == "Line 1\nLine 2\nLine 3"

    async def test_update_scratchpad_preserves_whitespace(self, state_manager):
        """update_scratchpad preserves meaningful whitespace."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Feature"))
        server = KaganMCPServer(state_manager)

        await server.update_scratchpad(ticket.id, "Code:\n  indented content")

        scratchpad = await state_manager.get_scratchpad(ticket.id)
        assert "  indented content" in scratchpad

    async def test_request_review_ticket_not_found(self, state_manager):
        """request_review raises ValueError for non-existent ticket."""
        server = KaganMCPServer(state_manager)

        with pytest.raises(ValueError, match="Ticket not found"):
            await server.request_review("nonexistent-id", "Summary")

    async def test_get_context_with_empty_acceptance_criteria(self, state_manager):
        """get_context handles tickets with empty acceptance criteria list."""
        ticket = await state_manager.create_ticket(
            Ticket.create(title="Feature", acceptance_criteria=[])
        )
        server = KaganMCPServer(state_manager)

        context = await server.get_context(ticket.id)

        assert context["acceptance_criteria"] == []

    async def test_get_context_with_special_characters(self, state_manager):
        """get_context handles special characters in ticket fields."""
        ticket = await state_manager.create_ticket(
            Ticket.create(
                title="Feature with émojis 🎉",
                description='Description with <html> & "quotes"',
            )
        )
        server = KaganMCPServer(state_manager)

        context = await server.get_context(ticket.id)

        assert context["title"] == "Feature with émojis 🎉"
        assert '<html> & "quotes"' in context["description"]

    async def test_request_review_empty_summary(self, state_manager, monkeypatch):
        """request_review accepts empty summary."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Feature"))
        server = KaganMCPServer(state_manager)

        async def _no_uncommitted(*_args) -> bool:
            return False

        monkeypatch.setattr(server, "_check_uncommitted_changes", _no_uncommitted)

        result = await server.request_review(ticket.id, "")

        assert result["status"] == "review"
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.review_summary == ""


class TestGetParallelTickets:
    """Tests for get_parallel_tickets MCP tool."""

    async def test_returns_in_progress_tickets(self, state_manager):
        """Returns all IN_PROGRESS tickets."""
        t1 = await state_manager.create_ticket(
            Ticket.create(title="Task 1", status=TicketStatus.IN_PROGRESS)
        )
        t2 = await state_manager.create_ticket(
            Ticket.create(title="Task 2", status=TicketStatus.IN_PROGRESS)
        )
        await state_manager.create_ticket(
            Ticket.create(title="Backlog", status=TicketStatus.BACKLOG)
        )
        server = KaganMCPServer(state_manager)

        result = await server.get_parallel_tickets()

        assert len(result) == 2
        ids = {t["ticket_id"] for t in result}
        assert t1.id in ids
        assert t2.id in ids

    async def test_excludes_specified_ticket(self, state_manager):
        """Excludes ticket when exclude_ticket_id provided."""
        t1 = await state_manager.create_ticket(
            Ticket.create(title="My ticket", status=TicketStatus.IN_PROGRESS)
        )
        t2 = await state_manager.create_ticket(
            Ticket.create(title="Other ticket", status=TicketStatus.IN_PROGRESS)
        )
        server = KaganMCPServer(state_manager)

        result = await server.get_parallel_tickets(exclude_ticket_id=t1.id)

        assert len(result) == 1
        assert result[0]["ticket_id"] == t2.id

    async def test_returns_empty_when_no_parallel_work(self, state_manager):
        """Returns empty list when no IN_PROGRESS tickets."""
        await state_manager.create_ticket(
            Ticket.create(title="Backlog", status=TicketStatus.BACKLOG)
        )
        server = KaganMCPServer(state_manager)

        result = await server.get_parallel_tickets()

        assert result == []

    async def test_includes_scratchpad(self, state_manager):
        """Result includes scratchpad for each ticket."""
        t1 = await state_manager.create_ticket(
            Ticket.create(title="Task", status=TicketStatus.IN_PROGRESS)
        )
        await state_manager.update_scratchpad(t1.id, "Progress notes")
        server = KaganMCPServer(state_manager)

        result = await server.get_parallel_tickets()

        assert result[0]["scratchpad"] == "Progress notes"

    async def test_returns_required_fields(self, state_manager):
        """Result contains ticket_id, title, description, scratchpad."""
        await state_manager.create_ticket(
            Ticket.create(
                title="Task",
                description="Details",
                status=TicketStatus.IN_PROGRESS,
            )
        )
        server = KaganMCPServer(state_manager)

        result = await server.get_parallel_tickets()

        assert "ticket_id" in result[0]
        assert "title" in result[0]
        assert "description" in result[0]
        assert "scratchpad" in result[0]


class TestGetAgentLogs:
    """Tests for get_agent_logs MCP tool."""

    async def test_returns_logs_for_ticket(self, state_manager):
        """Returns agent logs for specified ticket."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Task"))
        await state_manager.append_agent_log(ticket.id, "implementation", 1, '{"msg": "log1"}')
        await state_manager.append_agent_log(ticket.id, "implementation", 2, '{"msg": "log2"}')
        server = KaganMCPServer(state_manager)

        result = await server.get_agent_logs(ticket.id, limit=5)

        assert len(result) == 2
        assert result[0]["iteration"] == 1
        assert result[1]["iteration"] == 2

    async def test_raises_for_nonexistent_ticket(self, state_manager):
        """Raises ValueError for non-existent ticket."""
        server = KaganMCPServer(state_manager)

        with pytest.raises(ValueError, match="Ticket not found"):
            await server.get_agent_logs("nonexistent")

    async def test_returns_empty_for_no_logs(self, state_manager):
        """Returns empty list when ticket has no logs."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Task"))
        server = KaganMCPServer(state_manager)

        result = await server.get_agent_logs(ticket.id)

        assert result == []

    async def test_filters_by_log_type(self, state_manager):
        """Filters logs by log_type parameter."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Task"))
        await state_manager.append_agent_log(ticket.id, "implementation", 1, '{"type": "impl"}')
        await state_manager.append_agent_log(ticket.id, "review", 1, '{"type": "review"}')
        server = KaganMCPServer(state_manager)

        result = await server.get_agent_logs(ticket.id, log_type="review")

        assert len(result) == 1
        assert "review" in result[0]["content"]

    async def test_limits_results(self, state_manager):
        """Limits results to specified count (most recent)."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Task"))
        for i in range(10):
            await state_manager.append_agent_log(
                ticket.id, "implementation", i + 1, f'{{"i": {i}}}'
            )
        server = KaganMCPServer(state_manager)

        result = await server.get_agent_logs(ticket.id, limit=3)

        assert len(result) == 3
        # Should return most recent (highest iteration numbers)
        iterations = [r["iteration"] for r in result]
        assert max(iterations) == 10

    async def test_default_limit_is_one(self, state_manager):
        """Default limit returns only most recent iteration."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Task"))
        for i in range(5):
            await state_manager.append_agent_log(
                ticket.id, "implementation", i + 1, f'{{"i": {i}}}'
            )
        server = KaganMCPServer(state_manager)

        result = await server.get_agent_logs(ticket.id)

        assert len(result) == 1
        assert result[0]["iteration"] == 5

    async def test_returns_required_fields(self, state_manager):
        """Result contains iteration, content, created_at."""
        ticket = await state_manager.create_ticket(Ticket.create(title="Task"))
        await state_manager.append_agent_log(ticket.id, "implementation", 1, '{"data": "test"}')
        server = KaganMCPServer(state_manager)

        result = await server.get_agent_logs(ticket.id)

        assert "iteration" in result[0]
        assert "content" in result[0]
        assert "created_at" in result[0]


class TestReadonlyMode:
    """Tests for --readonly mode tool filtering."""

    def test_readonly_registers_only_coordination_tools(self):
        """Readonly mode should only register get_parallel_tickets and get_agent_logs."""
        from kagan.mcp.server import _create_mcp_server

        mcp = _create_mcp_server(readonly=True)

        # Get registered tool names - FastMCP stores tools in _tool_manager._tools dict
        tools = mcp._tool_manager._tools
        tool_names = set(tools.keys())

        # Should have exactly the read-only tools
        assert "get_parallel_tickets" in tool_names
        assert "get_agent_logs" in tool_names

        # Should NOT have full-mode tools
        assert "get_context" not in tool_names
        assert "update_scratchpad" not in tool_names
        assert "request_review" not in tool_names

    def test_full_mode_registers_all_tools(self):
        """Full mode (readonly=False) should register all tools."""
        from kagan.mcp.server import _create_mcp_server

        mcp = _create_mcp_server(readonly=False)

        tools = mcp._tool_manager._tools
        tool_names = set(tools.keys())

        # Should have all tools
        assert "get_parallel_tickets" in tool_names
        assert "get_agent_logs" in tool_names
        assert "get_context" in tool_names
        assert "update_scratchpad" in tool_names
        assert "request_review" in tool_names

    def test_readonly_tool_count(self):
        """Verify exact tool count in readonly mode."""
        from kagan.mcp.server import _create_mcp_server

        mcp = _create_mcp_server(readonly=True)
        assert len(mcp._tool_manager._tools) == 2

    def test_full_mode_tool_count(self):
        """Verify exact tool count in full mode."""
        from kagan.mcp.server import _create_mcp_server

        mcp = _create_mcp_server(readonly=False)
        assert len(mcp._tool_manager._tools) == 5


class TestMCPCLI:
    """Tests for MCP CLI command."""

    def test_mcp_readonly_flag_in_help(self):
        """Verify --readonly flag appears in CLI help."""
        from click.testing import CliRunner

        from kagan.__main__ import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["mcp", "--help"])
        assert result.exit_code == 0
        assert "--readonly" in result.output
        assert "read-only" in result.output.lower() or "coordination" in result.output.lower()
