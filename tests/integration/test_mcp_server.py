"""Tests for MCP server module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

from kagan.mcp.server import (
    _create_mcp_server,
    _get_server,
    _get_state_manager,
    find_kagan_dir,
    main,
)

pytestmark = pytest.mark.integration


class TestFindKaganDir:
    """Tests for find_kagan_dir function."""

    def test_finds_kagan_dir_in_current(self, tmp_path: Path) -> None:
        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()
        result = find_kagan_dir(tmp_path)
        assert result == kagan_dir

    def test_finds_kagan_dir_in_parent(self, tmp_path: Path) -> None:
        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()
        child = tmp_path / "subdir" / "nested"
        child.mkdir(parents=True)
        result = find_kagan_dir(child)
        assert result == kagan_dir

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        result = find_kagan_dir(tmp_path)
        assert result is None

    def test_resolves_symlinks(self, tmp_path: Path) -> None:
        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()
        result = find_kagan_dir(tmp_path)
        assert result is not None
        assert result.is_absolute()


class TestGetStateManager:
    """Tests for _get_state_manager function."""

    @pytest.fixture(autouse=True)
    def reset_globals(self) -> Generator[None, None, None]:
        import kagan.mcp.server as server_module

        server_module._state_manager = None
        server_module._server = None
        server_module._kagan_dir = None
        yield
        server_module._state_manager = None
        server_module._server = None
        server_module._kagan_dir = None

    async def test_creates_state_manager_from_kagan_dir(self, tmp_path: Path) -> None:
        import kagan.mcp.server as server_module

        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()
        server_module._kagan_dir = kagan_dir

        manager = await _get_state_manager()
        assert manager is not None
        await manager.close()

    async def test_raises_when_no_kagan_dir(self, mocker) -> None:
        mocker.patch("kagan.mcp.server.find_kagan_dir", return_value=None)
        with pytest.raises(RuntimeError, match="Not in a Kagan-managed project"):
            await _get_state_manager()

    async def test_returns_cached_manager(self, tmp_path: Path) -> None:
        import kagan.mcp.server as server_module

        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()
        server_module._kagan_dir = kagan_dir

        manager1 = await _get_state_manager()
        manager2 = await _get_state_manager()
        assert manager1 is manager2
        await manager1.close()


class TestGetServer:
    """Tests for _get_server function."""

    @pytest.fixture(autouse=True)
    def reset_globals(self) -> Generator[None, None, None]:
        import kagan.mcp.server as server_module

        server_module._state_manager = None
        server_module._server = None
        server_module._kagan_dir = None
        yield
        server_module._state_manager = None
        server_module._server = None
        server_module._kagan_dir = None

    async def test_creates_server_instance(self, tmp_path: Path) -> None:
        import kagan.mcp.server as server_module

        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()
        server_module._kagan_dir = kagan_dir

        server = await _get_server()
        assert server is not None
        assert server_module._state_manager is not None
        await server_module._state_manager.close()

    async def test_returns_cached_server(self, tmp_path: Path) -> None:
        import kagan.mcp.server as server_module

        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()
        server_module._kagan_dir = kagan_dir

        server1 = await _get_server()
        server2 = await _get_server()
        assert server1 is server2
        assert server_module._state_manager is not None
        await server_module._state_manager.close()


class TestMCPTools:
    """Tests for MCP tool functions created via factory."""

    @pytest.fixture(autouse=True)
    def reset_globals(self) -> Generator[None, None, None]:
        import kagan.mcp.server as server_module

        server_module._state_manager = None
        server_module._server = None
        server_module._kagan_dir = None
        yield
        server_module._state_manager = None
        server_module._server = None
        server_module._kagan_dir = None

    def test_factory_creates_full_mode_tools(self) -> None:
        """Factory creates all 5 tools in full mode."""
        mcp = _create_mcp_server(readonly=False)
        tool_names = set(mcp._tool_manager._tools.keys())

        assert "get_context" in tool_names
        assert "update_scratchpad" in tool_names
        assert "request_review" in tool_names
        assert "get_parallel_tickets" in tool_names
        assert "get_agent_logs" in tool_names

    def test_factory_creates_readonly_mode_tools(self) -> None:
        """Factory creates only 2 tools in readonly mode."""
        mcp = _create_mcp_server(readonly=True)
        tool_names = set(mcp._tool_manager._tools.keys())

        assert "get_parallel_tickets" in tool_names
        assert "get_agent_logs" in tool_names
        assert "get_context" not in tool_names
        assert "update_scratchpad" not in tool_names
        assert "request_review" not in tool_names

    def test_full_mode_is_default(self) -> None:
        """Factory defaults to full mode (readonly=False)."""
        mcp = _create_mcp_server()
        assert len(mcp._tool_manager._tools) == 5


class TestMain:
    """Tests for main entry point."""

    def test_exits_when_no_kagan_dir(self, mocker) -> None:
        mocker.patch("kagan.mcp.server.find_kagan_dir", return_value=None)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert "Not in a Kagan-managed project" in str(exc_info.value)

    def test_runs_mcp_server_when_dir_found(self, tmp_path: Path, mocker) -> None:
        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()

        mock_mcp_instance = mocker.MagicMock()
        mocker.patch("kagan.mcp.server.find_kagan_dir", return_value=kagan_dir)
        mocker.patch("kagan.mcp.server._create_mcp_server", return_value=mock_mcp_instance)

        main()
        mock_mcp_instance.run.assert_called_once_with(transport="stdio")

    def test_main_accepts_readonly_parameter(self, tmp_path: Path, mocker) -> None:
        kagan_dir = tmp_path / ".kagan"
        kagan_dir.mkdir()

        mock_create = mocker.patch("kagan.mcp.server._create_mcp_server")
        mock_create.return_value.run = mocker.MagicMock()
        mocker.patch("kagan.mcp.server.find_kagan_dir", return_value=kagan_dir)

        main(readonly=True)
        mock_create.assert_called_once_with(readonly=True)
