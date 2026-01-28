# User Guide

Kagan is a keyboard-first Kanban TUI that can drive autonomous coding agents against your
repo. You stay in control: you decide when work starts, what gets reviewed, and when work
is merged.

## Prerequisites

- Python 3.12+
- `uv` installed
- A modern terminal (minimum size 80x20)
- Git repository (required for agent worktrees and review/merge)
- tmux (for PAIR mode sessions)
- An ACP-compatible agent CLI on your PATH (for example, `claude`) or a configured agent

## Install and run

From the repo root:

```bash
uv run kagan
```

Optional flags:

```bash
uv run kagan --version
uv run kagan --config /path/to/.kagan/config.toml
uv run kagan --db /path/to/.kagan/state.db
```

If you pass `--config` without `--db`, Kagan stores `state.db` alongside the config file.

## First run: what gets created

On first launch, Kagan shows a welcome screen where you can configure your default base branch and agent. After setup, Kagan stores local state under `.kagan/` in your project root:

- `.kagan/state.db` (SQLite database)
- `.kagan/config.toml` (configuration file)
- `.kagan/kagan.lock` (single-instance lock)
- `.kagan/worktrees/` (git worktrees per ticket)

## Main screen overview

The Kanban board has four columns, a header bar, and a dynamic footer:

- **Columns**: BACKLOG, IN_PROGRESS, REVIEW, DONE
- **Header**: logo, version, current git branch, active sessions count, ticket count
- **Footer**: context-aware keybindings (updates based on focused ticket and its state)
- **Cards**: type badge (👤/⚡), title, priority icon, short ID, created date

## Keyboard controls

The footer always displays available keybindings. Keys that don't apply to the current context appear grayed out.

### Navigation

| Key | Alternative | Action |
| --- | ----------- | ------ |
| `h` | `←` | Move focus left |
| `l` | `→` | Move focus right |
| `j` | `↓` | Move focus down |
| `k` | `↑` | Move focus up |

### Ticket Actions

| Key | Alternative | Action |
| --- | ----------- | ------ |
| `n` | | New ticket |
| `e` | | Edit ticket |
| `d` | | Delete ticket (with confirmation) |
| `v` | | View ticket details |
| `t` | | Toggle between PAIR 👤 and AUTO ⚡ mode |
| `[` | `Shift+←` | Move ticket to previous status |
| `]` | `Shift+→` | Move ticket to next status |
| `Enter` | | Open session (mode-dependent) |

### Review Actions (only for tickets in REVIEW status)

| Key | Action |
| --- | ------ |
| `r` | Open review modal with commits, diff stats, and AI review |
| `m` | Merge ticket branch to main and move to DONE |
| `D` | View full diff |
| `s` | Re-run acceptance checks |
| `w` | Watch agent output (AUTO tickets only) |

### Global

| Key | Action |
| --- | ------ |
| `c` | Open planner chat |
| `?` | Command palette |
| `Esc` | Deselect card / Close modal |
| `q` | Quit |

### Mouse

- Click a card to open details.
- Drag a card left/right to move it between columns.

## Ticket Modes: PAIR vs AUTO

Each ticket has a mode that determines how work is performed:

### PAIR Mode 👤

**For collaborative work with AI assistance.**

- Press `Enter` to open a tmux session in the ticket's worktree
- You work directly with an AI agent (like Claude Code) in the terminal
- Use Kagan's MCP tools to update context and request reviews
- Detach from tmux (`Ctrl+b d`) to return to Kagan
- Move ticket to REVIEW when ready

### AUTO Mode ⚡

**For fully autonomous agent execution.**

- Requires `auto_start = true` in config
- The scheduler automatically runs agents on IN_PROGRESS tickets
- Press `Enter` to watch live agent output
- Press `w` to watch progress on any AUTO ticket
- Agents signal completion with `<complete/>` to move to REVIEW

Toggle between modes with `t` on any ticket.

## Ticket lifecycle

1. **BACKLOG**: Idea captured, not started.
2. **IN_PROGRESS**: Work active.
   - PAIR: Open tmux session with `Enter`
   - AUTO: Scheduler runs agents automatically
3. **REVIEW**: Work completed, ready for review and merge.
4. **DONE**: Merged to the base branch and closed.

Move tickets with `[` / `]` or `Shift+Arrow`, or drag them between columns.

## Planner chat (create tickets from goals)

Open the planner chat with `c` and describe your goal. The planner agent analyzes your
request and generates structured tickets. You can:

- **Approve**: Create all proposed tickets
- **Refine**: Ask the planner to adjust the plan
- **Cancel**: Discard and return to the board

Keys in planner:
- `Esc` returns to the Kanban board
- `Ctrl+C` interrupts a running planner

## Review workflow

When a ticket reaches REVIEW:

1. Press `r` to open the review modal
2. View commits and diff statistics
3. Optionally press `g` to generate an AI code review
4. Press `a` to approve (merge and complete) or `r` to reject (return to IN_PROGRESS)

In the review modal:
| Key | Action |
| --- | ------ |
| `a` | Approve and merge |
| `r` | Reject (prompts for feedback on AUTO tickets) |
| `g` | Generate AI review |
| `Esc` | Close without action |

## Modal keybindings

### Ticket Details Modal

| Key | Action |
| --- | ------ |
| `e` | Toggle edit mode |
| `d` | Delete ticket |
| `f` | Expand description (full screen) |
| `Ctrl+S` | Save changes |
| `Esc` | Close / Cancel edit |

### Confirmation Modal

| Key | Action |
| --- | ------ |
| `y` | Confirm (Yes) |
| `n` | Cancel (No) |
| `Esc` | Cancel |

### Agent Output Modal (AUTO mode)

| Key | Action |
| --- | ------ |
| `c` | Cancel running agent |
| `Esc` | Close (agent continues in background) |

## Worktrees and branches

Kagan isolates work in Git worktrees:

- Worktrees live at `.kagan/worktrees/<ticket-id>`
- Branch names follow `kagan/<ticket-id>-<slug>`

You can manually inspect or edit changes in the worktree directory.

## Configuration quick start

Minimal config (created automatically on first run):

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
```

Key settings:

- `auto_start`: Enable AUTO mode scheduler (default: false)
- `default_base_branch`: Branch for worktrees and merges
- `default_worker_agent`: Which agent to use for work

See [Configuration](config.md) for full details.

## Troubleshooting

- **"Another instance running"**: Close the other Kagan window. If it crashed, remove
  `.kagan/kagan.lock` and restart.
- **Agent not found**: Ensure the configured `run_command` exists on PATH. The welcome
  screen will warn you if agents are missing.
- **tmux not found**: Install tmux for PAIR mode sessions.
- **Keys grayed out**: Some actions only apply to certain ticket states (e.g., merge
  only works on REVIEW tickets).
- **Merge conflicts**: Kagan will abort and return the ticket to IN_PROGRESS.
- **AUTO not running**: Ensure `auto_start = true` in config.
