# AUTO/PAIR Mode Refinements - Implementation Report

> Completed: January 28, 2026

## Overview

This document captures the implementation of AUTO/PAIR ticket workflow refinements with multi-agent support. The changes fix critical behavior gaps, generalize PAIR mode to support multiple AI agents, and improve cleanup/reconciliation.

**Key principle:** Make the right thing easy, the wrong thing hard (but not impossible).

---

## Code Quality Standards

All code follows these principles (from AGENTS.md):

- **Simple**: Minimal abstractions, obvious intent
- **Elegant**: Clean APIs, consistent patterns
- **Laconic**: ~150-250 LOC per module
- **Modern**: Python 3.12+ with type hints everywhere

**Validation:**
```bash
uv run poe fix       # Auto-fix + format
uv run poe typecheck # pyrefly type checking
uv run poe check     # lint + typecheck + test
```

---

## Issues Addressed

### Issue 1: AUTO Tickets Allowed tmux Session Opening
`action_open_session()` opened tmux for ANY ticket. AUTO tickets run via ACP - tmux is meaningless.

### Issue 2: PAIR Mode Hardcoded to "claude"
In `sessions/manager.py`, the agent launch was hardcoded:
```python
await run_tmux("send-keys", "-t", session_name, "claude", "Enter")
```

### Issue 3: No Distinction Between ACP and Interactive Commands
`AgentConfig.run_command` was only for ACP automation. PAIR mode needed an `interactive_command` for CLI launches.

### Issue 4: Missing Session/Worktree Cleanup
- Merge/Complete: No cleanup of session + worktree
- Delete: No comprehensive resource cleanup

### Issue 5: Separate MCP Binary
`kagan-mcp` was a separate entry point, complicating distribution.

---

## Implementation Batches

### Batch 0: Unified CLI with Click ✅

**Files modified:**
- `pyproject.toml` - Added `click>=8.0.0`, changed entry point to `kagan = "kagan.__main__:cli"`
- `src/kagan/__main__.py` - Rewritten with Click

**Changes:**
```python
@click.group(invoke_without_command=True)
def cli(ctx, version):
    """AI-powered Kanban TUI for autonomous development workflows."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(tui)

@cli.command()
def tui(db, config):
    """Run the Kanban TUI (default command)."""

@cli.command()
def mcp():
    """Run the MCP server (STDIO transport)."""
```

**Usage:**
```bash
kagan        # Run TUI (default)
kagan tui    # Run TUI explicitly
kagan mcp    # Run MCP server
```

---

### Batch 1: Fix Enter Key Behavior ✅

**Files modified:**
- `src/kagan/ui/screens/kanban.py`

**Changes:**
Refactored `action_open_session()` to dispatch based on ticket type:

```python
async def action_open_session(self) -> None:
    ticket_type = TicketType(raw_type) if isinstance(raw_type, str) else raw_type
    if ticket_type == TicketType.AUTO:
        await self._open_auto_session(ticket)
    else:
        await self._open_pair_session(ticket)
```

- **AUTO tickets**: Shows `AgentOutputModal` or starts agent
- **PAIR tickets**: Opens tmux session

---

### Batch 2: Multi-Agent Support ✅

**Files modified:**
- `src/kagan/config.py` - Added `interactive_command` to `AgentConfig`
- `src/kagan/data/builtin_agents.py` - Updated all agents with both commands

**AgentConfig changes:**
```python
class AgentConfig(BaseModel):
    run_command: dict[str, str]        # ACP command for AUTO mode
    interactive_command: dict[str, str] # CLI command for PAIR mode
```

**Builtin agents updated:**
| Agent | ACP Command | Interactive Command |
|-------|-------------|---------------------|
| Claude | `claude-code-acp` | `claude` |
| OpenCode | `opencode acp` | `opencode` |
| Codex | `npx @zed-industries/codex-acp` | `codex` |
| Gemini | `gemini --experimental-acp` | `gemini` |
| Goose | `goose acp` | `goose` |

---

### Batch 3: Generalize SessionManager ✅

**Files modified:**
- `src/kagan/sessions/manager.py` - Uses ticket's agent config
- `src/kagan/app.py` - Passes config to SessionManager
- `tests/test_sessions.py` - Updated for new signature

**Key change:**
```python
def _get_agent_config(self, ticket: Ticket) -> AgentConfig:
    # Priority 1: ticket's agent_backend
    if ticket.agent_backend:
        if builtin := get_builtin_agent(ticket.agent_backend):
            return builtin.config
    # Priority 2: config's default_worker_agent
    # Priority 3: fallback
```

**MCP config in worktrees:**
```json
{"mcpServers": {"kagan": {"command": "kagan", "args": ["mcp"]}}}
```

---

### Batch 4: Cleanup + Startup Reconciliation ✅

**Files modified:**
- `src/kagan/ui/screens/kanban.py` - Comprehensive delete cleanup
- `src/kagan/app.py` - Added `_reconcile_sessions()`

**Delete cleanup:**
```python
async def _on_delete_confirmed(self, confirmed):
    # Stop agent if running (AUTO tickets)
    if scheduler.is_running(ticket.id):
        await agent.stop()
    # Kill tmux session if exists
    await self.kagan_app.session_manager.kill_session(ticket.id)
    # Delete worktree if exists
    await worktree.delete(ticket.id, delete_branch=True)
    # Delete ticket from database
    await self.kagan_app.state_manager.delete_ticket(ticket.id)
```

**Startup reconciliation:**
```python
async def _reconcile_sessions(self) -> None:
    """Kill orphaned tmux sessions from previous runs."""
    kagan_sessions = [s for s in output.split("\n") if s.startswith("kagan-")]
    for session_name in kagan_sessions:
        if ticket_id not in valid_ticket_ids:
            await run_tmux("kill-session", "-t", session_name)
```

---

### Batch 5: REVIEW→DONE Merge Confirmation ✅

**Files modified:**
- `src/kagan/ui/screens/kanban.py`

**Changes:**
`]` key on REVIEW ticket shows merge confirmation modal:

```python
if status == TicketStatus.REVIEW and new_status == TicketStatus.DONE:
    self._pending_merge_ticket = card.ticket
    self.app.push_screen(
        ConfirmModal(title="Complete Ticket?", message=msg),
        callback=self._on_merge_confirmed,
    )
```

**On confirm:**
1. Merge worktree to main branch
2. Delete worktree
3. Kill tmux session
4. Move ticket to DONE (keeps ticket in DB)

---

## Test Results

```
================== 146 passed, 2 skipped, 1 warning in 23.60s ==================
```

- All lint checks pass (`ruff check`)
- All type checks pass (`pyrefly check`)
- All tests pass (`pytest`)

---

## Files Changed Summary

| File | Change |
|------|--------|
| `pyproject.toml` | Added click, unified entry point |
| `src/kagan/__main__.py` | Click CLI with subcommands |
| `src/kagan/config.py` | Added `interactive_command` to AgentConfig |
| `src/kagan/data/builtin_agents.py` | Updated all agents + added Goose |
| `src/kagan/sessions/manager.py` | Agent-agnostic session creation |
| `src/kagan/app.py` | Config injection + reconciliation |
| `src/kagan/ui/screens/kanban.py` | Enter dispatch, cleanup, merge modal |
| `tests/test_sessions.py` | Updated for new SessionManager signature |

---

## Usage Notes

### Running the TUI
```bash
kagan           # Default - launches TUI
kagan tui       # Explicit TUI command
```

### MCP Server for AI Agents
```bash
kagan mcp       # Runs MCP server (STDIO transport)
```

AI agents should configure MCP like:
```json
{
  "mcpServers": {
    "kagan": {"command": "kagan", "args": ["mcp"]}
  }
}
```

### Keyboard Shortcuts (Kanban Screen)
| Key | Action |
|-----|--------|
| `Enter` | Open session (tmux for PAIR, modal for AUTO) |
| `]` | Move forward (REVIEW→DONE shows merge modal) |
| `[` | Move backward |
| `d` | Delete ticket (with full cleanup) |
| `t` | Toggle ticket type (AUTO/PAIR) |
| `w` | Watch AUTO agent progress |

---

## Architecture Notes

### Two Execution Modes

**AUTO Mode:**
- Agent runs via ACP (Agent Communication Protocol)
- Scheduler manages agent lifecycle
- User watches progress via `AgentOutputModal`
- No tmux session needed

**PAIR Mode:**
- User works interactively in tmux session
- AI agent CLI launched automatically (configurable)
- MCP server provides context to agent
- User manually drives development

### Agent Selection Priority
1. `ticket.agent_backend` (per-ticket override)
2. `config.general.default_worker_agent` (project default)
3. Fallback to Claude

### Resource Lifecycle
- **Create**: Worktree + tmux session + context files
- **Delete**: Stop agent + kill session + delete worktree + remove ticket
- **Complete**: Merge + delete worktree + kill session + keep ticket in DONE
