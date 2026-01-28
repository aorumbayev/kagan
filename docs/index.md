# ᘚᘛ KAGAN

AI-powered Kanban TUI for autonomous development workflows.

## Quick start

```bash
uv run kagan
```

## Start here

- Read the [User Guide](user-guide.md) for a full walkthrough of workflows and automation.
- Check [Configuration](config.md) for agent setup and scheduler options.

## Key bindings

The footer always shows available keybindings for the current context. Keys that don't apply to the current state appear grayed out.

### Navigation

| Key | Action |
| --- | ------ |
| <kbd>h</kbd> / <kbd>←</kbd> | Move focus left |
| <kbd>l</kbd> / <kbd>→</kbd> | Move focus right |
| <kbd>j</kbd> / <kbd>↓</kbd> | Move focus down |
| <kbd>k</kbd> / <kbd>↑</kbd> | Move focus up |

### Ticket Actions

| Key | Action |
| --- | ------ |
| <kbd>n</kbd> | New ticket |
| <kbd>e</kbd> | Edit ticket |
| <kbd>d</kbd> | Delete ticket |
| <kbd>v</kbd> | View ticket details |
| <kbd>t</kbd> | Toggle PAIR/AUTO mode |
| <kbd>[</kbd> / <kbd>Shift+←</kbd> | Move ticket backward |
| <kbd>]</kbd> / <kbd>Shift+→</kbd> | Move ticket forward |
| <kbd>Enter</kbd> | Open session (tmux for PAIR, modal for AUTO) |

### Review Actions (REVIEW status only)

| Key | Action |
| --- | ------ |
| <kbd>r</kbd> | Open review modal |
| <kbd>m</kbd> | Merge to main branch |
| <kbd>D</kbd> | View diff |
| <kbd>s</kbd> | Re-run acceptance checks |
| <kbd>w</kbd> | Watch agent output (AUTO only) |

### Global

| Key | Action |
| --- | ------ |
| <kbd>c</kbd> | Open planner chat |
| <kbd>?</kbd> | Command palette |
| <kbd>Esc</kbd> | Deselect / Close modal |
| <kbd>q</kbd> | Quit |

## Ticket Modes

Kagan supports two work modes per ticket:

- **PAIR** 👤: You work alongside AI in a tmux session. Press <kbd>Enter</kbd> to open the session.
- **AUTO** ⚡: The scheduler runs agents automatically. Press <kbd>Enter</kbd> to watch progress.

Toggle between modes with <kbd>t</kbd>.

## What it is

Kagan is a Textual-based Kanban board for coordinating autonomous development work. It keeps local state, supports agent-driven execution, and focuses on fast keyboard workflows with an always-visible footer showing context-aware keybindings.
