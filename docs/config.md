# Configuration

Kagan reads configuration from `.kagan/config.toml`. On first run, Kagan creates this file
with sensible defaults via the welcome screen.

## Default paths

- State database: `.kagan/state.db`
- Config file: `.kagan/config.toml`
- Lock file: `.kagan/kagan.lock`
- Worktrees: `.kagan/worktrees/`
- Custom prompts: `.kagan/prompts/`

## General settings

```toml
[general]
# Enable AUTO mode scheduler (runs agents automatically)
auto_start = false

# Branch to use for worktrees and merges
default_base_branch = "main"

# Default agent for new tickets
default_worker_agent = "claude"
```

### Settings explained

| Setting | Default | Description |
| ------- | ------- | ----------- |
| `auto_start` | `false` | When `true`, the scheduler runs agents on AUTO tickets automatically |
| `default_base_branch` | `"main"` | Git branch for creating worktrees and merging completed work |
| `default_worker_agent` | `"claude"` | Which configured agent to use by default |

## Agents

Agents are ACP-compatible processes that Kagan can start. Configure at least one agent
with `active = true`.

```toml
[agents.claude]
identity = "anthropic.claude"
name = "Claude Code"
short_name = "claude"
active = true

[agents.claude.run_command]
"*" = "claude"
# OS-specific commands:
# linux = "claude"
# macos = "claude"
# windows = "claude.exe"
```

### Agent configuration options

| Field | Required | Description |
| ----- | -------- | ----------- |
| `identity` | Yes | Unique identifier for the agent |
| `name` | Yes | Display name shown in UI |
| `short_name` | Yes | Short name for compact display |
| `active` | No | Whether this agent is available (default: `true`) |
| `run_command` | Yes | Command to start the agent (supports OS-specific values) |

### Multiple agents

You can configure multiple agents and select them per-ticket:

```toml
[agents.claude]
identity = "anthropic.claude"
name = "Claude Code"
short_name = "claude"
active = true

[agents.claude.run_command]
"*" = "claude"

[agents.codex]
identity = "openai.codex"
name = "OpenAI Codex"
short_name = "codex"
active = true

[agents.codex.run_command]
"*" = "codex"
```

## Prompts

Kagan's AI agent prompts can be customized through TOML config or markdown files.

**Priority order:** User files > TOML inline > Built-in defaults

### Inline prompts (TOML)

```toml
[prompts]
worker_system_prompt = "You are a careful developer who writes clean code..."
reviewer_system_prompt = "Review code for correctness and style..."
planner_system_prompt = "Create detailed, actionable tickets..."
```

### File overrides

Place markdown files in `.kagan/prompts/` to override built-in templates:

```
.kagan/prompts/
├── worker.md      # Worker iteration template
├── reviewer.md    # Code review template
└── planner.md     # Planner system prompt
```

File overrides take priority over TOML inline prompts.

### Template variables

**Worker template** (`worker.md`):

| Variable | Description |
| -------- | ----------- |
| `{iteration}` | Current iteration number |
| `{max_iterations}` | Maximum allowed iterations |
| `{title}` | Ticket title |
| `{description}` | Ticket description |
| `{scratchpad}` | Previous progress notes |

**Reviewer template** (`reviewer.md`):

| Variable | Description |
| -------- | ----------- |
| `{title}` | Ticket title |
| `{ticket_id}` | Ticket ID |
| `{description}` | Ticket description |
| `{commits}` | List of commits |
| `{diff_summary}` | Summary of changes |

**Planner** (`planner.md`):
- No variables - customize the planner's personality and guidelines
- The XML output format is automatically appended and cannot be changed

## Session configuration

For PAIR mode tmux sessions:

```toml
[session]
# Startup prompt sent to the agent when session opens
startup_prompt = "You are working on ticket: {title}\n\nDescription:\n{description}"
```

### Session template variables

| Variable | Description |
| -------- | ----------- |
| `{title}` | Ticket title |
| `{description}` | Ticket description |
| `{ticket_id}` | Ticket ID |

## Example: Full configuration

```toml
[general]
auto_start = false
default_base_branch = "main"
default_worker_agent = "claude"

[agents.claude]
identity = "anthropic.claude"
name = "Claude Code"
short_name = "claude"
active = true

[agents.claude.run_command]
"*" = "claude"
macos = "claude"
linux = "claude"

[prompts]
planner_system_prompt = """
You are a senior software architect. When creating tickets:
- Break large features into small, focused tasks
- Include acceptance criteria
- Consider edge cases and error handling
"""

[session]
startup_prompt = """
You are working on: {title}

{description}

Use the Kagan MCP tools to:
- get_context: See ticket details and project info
- update_scratchpad: Save progress notes
- request_review: Signal completion
"""
```

## Minimal config

For manual-only workflows (no AUTO mode):

```toml
[general]
default_base_branch = "main"
default_worker_agent = "claude"

[agents.claude]
identity = "anthropic.claude"
name = "Claude Code"
short_name = "claude"
active = true

[agents.claude.run_command]
"*" = "claude"
```

## Environment variables

Kagan respects these environment variables (set in tmux sessions):

| Variable | Description |
| -------- | ----------- |
| `KAGAN_TICKET_ID` | Current ticket ID |
| `KAGAN_WORKTREE_PATH` | Path to ticket worktree |
