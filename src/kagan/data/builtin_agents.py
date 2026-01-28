"""Built-in agent definitions for Kagan."""

from __future__ import annotations

from dataclasses import dataclass

from kagan.config import AgentConfig


@dataclass
class BuiltinAgent:
    """Extended agent info with metadata for welcome screen."""

    config: AgentConfig
    author: str
    description: str
    install_command: str


# Built-in agents that ship with Kagan
# run_command: ACP protocol command for AUTO mode (programmatic)
# interactive_command: CLI command for PAIR mode (interactive tmux session)
BUILTIN_AGENTS: dict[str, BuiltinAgent] = {
    "claude": BuiltinAgent(
        config=AgentConfig(
            identity="claude.com",
            name="Claude Code",
            short_name="claude",
            run_command={"*": "claude-code-acp"},
            interactive_command={"*": "claude"},
            active=True,
        ),
        author="Anthropic",
        description="Agentic AI for coding tasks",
        install_command="curl -fsSL https://claude.ai/install.sh | bash",
    ),
    "opencode": BuiltinAgent(
        config=AgentConfig(
            identity="opencode.ai",
            name="OpenCode",
            short_name="opencode",
            run_command={"*": "opencode acp"},
            interactive_command={"*": "opencode"},
            active=True,
        ),
        author="SST",
        description="Multi-model CLI with TUI",
        install_command="npm i -g opencode-ai",
    ),
    "codex": BuiltinAgent(
        config=AgentConfig(
            identity="openai.com",
            name="Codex CLI",
            short_name="codex",
            run_command={"*": "npx @zed-industries/codex-acp"},
            interactive_command={"*": "codex"},
            active=True,
        ),
        author="OpenAI",
        description="Lightweight coding agent",
        install_command="npm install -g @openai/codex",
    ),
    "gemini": BuiltinAgent(
        config=AgentConfig(
            identity="geminicli.com",
            name="Gemini CLI",
            short_name="gemini",
            run_command={"*": "gemini --experimental-acp"},
            interactive_command={"*": "gemini"},
            active=True,
        ),
        author="Google",
        description="Query and edit large codebases",
        install_command="npm install -g @google/gemini-cli",
    ),
    "goose": BuiltinAgent(
        config=AgentConfig(
            identity="goose.ai",
            name="Goose",
            short_name="goose",
            run_command={"*": "goose acp"},
            interactive_command={"*": "goose"},
            active=True,
        ),
        author="Block",
        description="Extensible AI agent framework",
        install_command=(
            "curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh "
            "| bash"
        ),
    ),
}


def get_builtin_agent(name: str) -> BuiltinAgent | None:
    """Get a built-in agent by short name.

    Args:
        name: The short name of the agent (e.g., 'claude', 'opencode').

    Returns:
        The BuiltinAgent if found, None otherwise.
    """
    return BUILTIN_AGENTS.get(name)


def list_builtin_agents() -> list[BuiltinAgent]:
    """Get all built-in agents.

    Returns:
        A list of all BuiltinAgent objects.
    """
    return list(BUILTIN_AGENTS.values())
