from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from kagan.config import AgentConfig, KaganConfig
from kagan.services.sessions import SessionService

if TYPE_CHECKING:
    from kagan.services.tasks import TaskService
    from kagan.services.workspaces import WorkspaceService


def _build_service() -> SessionService:
    return SessionService(
        project_root=Path("."),
        task_service=cast("TaskService", object()),
        workspace_service=cast("WorkspaceService", object()),
        config=KaganConfig(),
    )


def _agent(short_name: str, interactive_command: str = "agent-cli") -> AgentConfig:
    return AgentConfig(
        identity=f"{short_name}.example.com",
        name=short_name.title(),
        short_name=short_name,
        run_command={"*": "agent-acp"},
        interactive_command={"*": interactive_command},
        active=True,
        model_env_var="",
    )


@pytest.mark.parametrize(
    ("short_name", "expected"),
    [
        ("codex", "agent-cli 'hello world'"),
        ("gemini", "agent-cli 'hello world'"),
        ("kimi", "agent-cli --prompt 'hello world'"),
        ("copilot", "agent-cli"),
    ],
)
def test_build_launch_command_prompt_style(short_name: str, expected: str) -> None:
    service = _build_service()

    cmd = service._build_launch_command(_agent(short_name), "hello world")

    assert cmd == expected


def test_build_launch_command_opencode_uses_prompt_flag_and_model() -> None:
    service = _build_service()

    cmd = service._build_launch_command(_agent("opencode"), "hello world", model="gpt-5")

    assert cmd == "agent-cli --model gpt-5 --prompt 'hello world'"


def test_build_launch_command_claude_uses_positional_prompt_and_model() -> None:
    service = _build_service()

    cmd = service._build_launch_command(_agent("claude"), "hello world", model="sonnet")

    assert cmd == "agent-cli --model sonnet 'hello world'"
