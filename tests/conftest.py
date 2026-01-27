"""Pytest fixtures for Kagan tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kagan.app import KaganApp
from kagan.database.manager import StateManager


@pytest.fixture
async def state_manager():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = StateManager(db_path)
        await manager.initialize()
        yield manager
        await manager.close()


@pytest.fixture
def app() -> KaganApp:
    """Create app with in-memory database."""
    return KaganApp(db_path=":memory:")


@pytest.fixture
def mock_agent_manager():
    """Create a mock agent manager for testing."""
    from tests.mock_agent import MockAgentManager

    return MockAgentManager()


@pytest.fixture
def app_with_mock_agents(mock_agent_manager):
    """Create app with mock agent manager injected."""
    app = KaganApp(db_path=":memory:")
    app._agent_manager = mock_agent_manager
    return app


@pytest.fixture
def quick_complete_behavior():
    """Agent that completes immediately."""
    from tests.mock_agent import MockAgentBehavior

    return MockAgentBehavior(
        signals={1: "complete"},
        response_templates={1: "Done!\n<complete/>"},
        response_delay=0.01,
    )


@pytest.fixture
def blocked_behavior():
    """Agent that gets blocked."""
    from tests.mock_agent import MockAgentBehavior

    return MockAgentBehavior(
        signals={1: "blocked"},
        response_templates={1: "Need help!\n<blocked reason='missing config'/>"},
        response_delay=0.01,
    )


@pytest.fixture
def multi_iteration_behavior():
    """Agent that takes 3 iterations to complete."""
    from tests.mock_agent import MockAgentBehavior

    return MockAgentBehavior(
        signals={1: "continue", 2: "continue", 3: "complete"},
        response_templates={
            1: "Starting work...\n<continue/>",
            2: "Making progress...\n<continue/>",
            3: "All done!\n<complete/>",
        },
        response_delay=0.01,
    )
