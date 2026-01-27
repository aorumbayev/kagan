# Configuration

Kagan reads optional configuration from `.kagan/config.toml`. If the file is missing,
defaults are used.

## Default paths

- State database: `.kagan/state.db`
- Config file: `.kagan/config.toml`
- Lock file: `.kagan/kagan.lock`
- Worktrees: `.kagan/worktrees/`
- Custom prompts: `.kagan/prompts/`
- Hat role prompts: `.kagan/prompts/roles/`

## General settings

```toml
[general]
max_concurrent_agents = 3
# Branch to use for worktrees and merges
default_base_branch = "main"
# Auto-run the scheduler loop
auto_start = false
# Max iterations per ticket in auto mode
max_iterations = 10
# Delay between iterations (seconds)
iteration_delay_seconds = 2.0
```

## Agents

Agents are ACP-compatible processes that Kagan can start. The first `active = true`
agent is used as the default.

```toml
[agents.claude]
identity = "anthropic.claude"
name = "Claude Code"
short_name = "claude"
protocol = "acp"
active = true

[agents.claude.run_command]
"*" = "claude"
# You can also provide OS-specific values:
# linux = "claude"
# macos = "claude"
# windows = "claude.exe"
```

## Prompts

Kagan's AI agent prompts can be customized through TOML config or markdown files.

On first setup (via the welcome screen), Kagan automatically creates `.kagan/prompts/`
with the default templates so you can customize them immediately.

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
- `{iteration}` - Current iteration number
- `{max_iterations}` - Maximum allowed iterations
- `{title}` - Ticket title
- `{description}` - Ticket description
- `{scratchpad}` - Previous progress notes
- `{hat_instructions}` - Role-specific instructions (from hat config)

**Reviewer template** (`reviewer.md`):
- `{title}` - Ticket title
- `{ticket_id}` - Ticket ID
- `{description}` - Ticket description
- `{commits}` - List of commits
- `{diff_summary}` - Summary of changes

**Planner** (`planner.md`):
- No variables - customize the planner's personality and guidelines
- **Note:** The XML output format (`<ticket>`, `<title>`, etc.) is automatically appended
  and cannot be changed - Kagan needs this format to parse tickets correctly

## Hats (optional role prompts)

Hats let you add role-specific instructions that are injected into worker prompts.
You can define instructions inline or reference a file.

### Inline system prompt

```toml
[hats.backend]
agent_command = "claude"
args = ["--model", "sonnet"]
system_prompt = "You are a backend engineer. Focus on API design and database optimization."
```

### File reference

```toml
[hats.frontend]
agent_command = "claude"
prompt_file = "frontend.md"  # Loads .kagan/prompts/roles/frontend.md
```

Place hat prompt files in `.kagan/prompts/roles/`:

```
.kagan/prompts/roles/
├── frontend.md
├── backend.md
└── devops.md
```

The `.md` extension is optional in the config - both `prompt_file = "frontend"` and
`prompt_file = "frontend.md"` work.

**Priority:** `prompt_file` takes precedence over `system_prompt` if both are set.

## Minimal config

```toml
[general]
max_concurrent_agents = 3
```
