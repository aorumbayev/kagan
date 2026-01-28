# Bugs and Issues Tracker

> E2E Testing Session: January 28, 2026

## Status Key
- 🔴 Critical - Blocks core workflow
- 🟡 Medium - Workaround exists
- 🟢 Fixed - Verified working

---

## Discovered Bugs

### BUG-001: 🟢 AUTO Mode - AgentOutputModal Does Not Appear (FIXED)

**Severity:** Critical - Blocks AUTO mode workflow

**Date Discovered:** 2026-01-28
**Date Fixed:** 2026-01-28

**Root Cause:**
The `auto_start` config option defaults to `False` in `.kagan/config.toml`. When `auto_start=false`, the scheduler's `tick()` method returns early without spawning agents. The UI didn't communicate this clearly.

**Fix Applied:**
Modified `KanbanScreen._open_auto_session()` to check if `auto_start` is enabled and show a helpful message if not:
```python
if not config.general.auto_start:
    self.notify(
        "AUTO mode requires auto_start=true in .kagan/config.toml",
        severity="warning",
    )
    return
```

**User Action Required:**
To use AUTO mode, edit `.kagan/config.toml` and set `auto_start = true`

---

### BUG-002: 🟢 Planner Screen Shows Raw Markup (FIXED)

**Severity:** Medium

**Date Discovered:** 2026-01-28
**Date Fixed:** 2026-01-28

**Root Cause:**
Rich markup like `[green]text[/green]` was being written to a `Markdown` widget which doesn't support Rich markup syntax - it only supports Markdown.

**Fix Applied:**
Converted all Rich markup in `planner.py` and `agent_output.py` to Markdown-compatible formatting:
- `[green]Agent ready[/green]` → `**Agent ready** ✓`
- `[bold cyan]> title[/bold cyan]` → `**> title**`
- `[red]Error: msg[/red]` → `**Error:** msg`

---

## Testing Checklist

### PAIR Mode Full Flow
- [ ] Create PAIR ticket with description
- [ ] Press Enter → tmux session opens
- [ ] Agent launches with ticket context/prompt
- [ ] Agent asks user to confirm before starting work
- [ ] User gives task (create hello world py script)
- [ ] Agent uses MCP `kagan_request_review` to move to REVIEW
- [ ] User detaches (Ctrl+b d) → returns to board
- [ ] Ticket appears in REVIEW column
- [ ] User moves to DONE → merge confirmation shown
- [ ] After merge, ticket in DONE, branch merged

### AUTO Mode Full Flow
- [x] Create AUTO ticket with description
- [x] Press Enter on BACKLOG → moves to IN_PROGRESS ✅
- [ ] Press Enter again → Shows AgentOutputModal with logs ❌ **BUG-001**
- [ ] Agent runs and auto-moves to REVIEW
- [ ] User validates and moves to DONE
- [ ] After merge, ticket in DONE, branch merged

---

## E2E Test Session Log - AUTO Mode (2026-01-28)

### Test Environment
- Test directory: `/tmp/kagan-auto-test`
- Terminal size: 120x40
- TUI MCP server used for automation

### Steps Completed Successfully
1. ✅ Welcome screen appeared with Kagan logo
2. ✅ Clicked "Start Using Kagan" button
3. ✅ Navigated to Planner screen (showing raw markup bug)
4. ✅ Pressed Escape to go to Kanban board
5. ✅ Board showed 4 columns: BACKLOG, IN PROGRESS, REVIEW, DONE
6. ✅ Pressed 'n' to create new ticket
7. ✅ New Ticket form appeared with Type dropdown
8. ✅ Selected "⚡ Auto (ACP)" from Type dropdown
9. ✅ Clicked title input field
10. ✅ Entered title: "Create hello world script"
11. ✅ Saved ticket with Ctrl+s
12. ✅ Ticket appeared in BACKLOG with ⚡ icon and ID #8a7b
13. ✅ Pressed Enter → ticket moved to IN_PROGRESS
14. ❌ Pressed Enter again → **NOTHING HAPPENED** (BUG-001)

### Test Blocked By
- BUG-001 prevents testing rest of AUTO mode workflow

---

## E2E Test Session Log - PAIR Mode (2026-01-28)

### Test Environment
- Test directory: `/tmp/kagan-pair-test`
- Terminal size: 120x40
- TUI MCP server used for automation
- Ticket ID created: `9affd871`

### Steps Completed Successfully
1. ✅ Fresh git repo created in `/tmp/kagan-pair-test`
2. ✅ Kagan launched via TUI MCP
3. ✅ Welcome screen appeared with Kagan logo
4. ✅ Clicked "Start Using Kagan" button
5. ✅ Navigated to Planner screen (BUG-002 observed - raw markup)
6. ✅ Pressed Escape to go to Kanban board
7. ✅ Board showed 4 empty columns
8. ✅ Pressed 'n' to create new ticket
9. ✅ **Confirmed: Type defaults to "👤 Pair (tmux)"**
10. ✅ Entered title: "Create hello world script"
11. ✅ Entered description: "Create a Python hello_world.py script that prints 'Hello, World!'"
12. ✅ Saved ticket with Ctrl+s
13. ✅ Ticket appeared in BACKLOG with 👤 icon
14. ✅ Pressed Enter → tmux session opened
15. ✅ Ticket automatically moved to IN_PROGRESS
16. ✅ Claude Code launched inside tmux (trust prompt appeared)
17. ✅ Confirmed trust → Claude Code welcome screen appeared
18. ✅ Detached from tmux (Ctrl+b d) → returned to Kanban board
19. ✅ Sessions: 1 shown in header
20. ✅ Ticket remained in IN_PROGRESS column

### Files Verified in Worktree
Location: `/tmp/kagan-pair-test/.kagan/worktrees/9affd871/`

**`.kagan/CONTEXT.md` (488 bytes):**
```markdown
# Ticket: 9affd871 - Create hello world script

## Description
Create a Python hello_world.py script that prints 'Hello, World!'

## Acceptance Criteria
- No specific criteria

## Rules
- You are in a git worktree, NOT the main repository
- Only modify files within this worktree
- Use `kagan_get_context` MCP tool to refresh ticket info
- Use `kagan_update_scratchpad` to save progress notes
- When complete: call `kagan_request_review` MCP tool

## Check Command
pytest && ruff check .
```

**`.claude/settings.local.json` (64 bytes):**
```json
{"mcpServers": {"kagan": {"command": "kagan", "args": ["mcp"]}}}
```

**NO `CLAUDE.md` at worktree root** ❌

---

### BUG-003: 🟢 PAIR Mode - Claude Code Receives No Automatic Task Context (FIXED)

**Severity:** Critical - Core PAIR workflow incomplete

**Date Discovered:** 2026-01-28
**Date Fixed:** 2026-01-28

**Root Cause:**
Kagan created `.kagan/CONTEXT.md` with ticket details but Claude Code only auto-reads `CLAUDE.md` at workspace root on startup. The context file existed but was never consumed.

**Fix Applied:**
Modified `SessionManager._write_context_files()` to also create `CLAUDE.md` at worktree root:

```python
# Create CLAUDE.md at worktree root with task instructions
claude_md = worktree_path / "CLAUDE.md"
if not claude_md.exists():
    claude_md.write_text(self._build_claude_md(ticket))
```

The generated `CLAUDE.md` includes:
- Task title and description
- Acceptance criteria
- Instructions to confirm with user before starting
- MCP tools available (`kagan_request_review`, etc.)
- Detach instructions (Ctrl+b d)

---

## Updated Testing Checklist

### PAIR Mode Full Flow
- [x] Create PAIR ticket with description ✅
- [x] Press Enter → tmux session opens ✅
- [x] Ticket moves to IN_PROGRESS automatically ✅
- [x] Claude Code launches in tmux ✅
- [ ] Agent launches with ticket context/prompt ❌ **BUG-003**
- [ ] Agent asks user to confirm before starting work ❌ (related to BUG-003)
- [ ] User gives task (create hello world py script) - Manual intervention needed
- [ ] Agent uses MCP `kagan_request_review` to move to REVIEW - Not tested
- [x] User detaches (Ctrl+b d) → returns to board ✅
- [ ] Ticket appears in REVIEW column - Not tested
- [ ] User moves to DONE → merge confirmation shown - Not tested
- [ ] After merge, ticket in DONE, branch merged - Not tested

### AUTO Mode Full Flow
- [x] Create AUTO ticket with description ✅
- [x] Press Enter on BACKLOG → moves to IN_PROGRESS ✅
- [ ] Press Enter again → Shows AgentOutputModal with logs ❌ **BUG-001**
- [ ] Agent runs and auto-moves to REVIEW - Blocked by BUG-001
- [ ] User validates and moves to DONE - Not tested
- [ ] After merge, ticket in DONE, branch merged - Not tested

---

## Summary of Bugs

| Bug ID | Mode | Issue | Status |
|--------|------|-------|--------|
| BUG-001 | AUTO | AgentOutputModal doesn't appear | 🟢 FIXED - Now shows helpful message about auto_start config |
| BUG-002 | Both | Raw Rich markup visible in Planner | 🟢 FIXED - Converted to Markdown |
| BUG-003 | PAIR | Claude Code receives no automatic context | 🟢 FIXED - CLAUDE.md now created in worktree |
| BUG-004 | PAIR | MCP tools not auto-connected | 🟡 EXPECTED - User must run `claude mcp add kagan` first |

---

## E2E Full Flow Test Results (2026-01-28)

### PAIR Mode Complete Flow ✅

| Step | Status |
|------|--------|
| Create ticket with description | ✅ |
| Press Enter → tmux opens | ✅ |
| Claude Code sees CLAUDE.md task | ✅ |
| Claude asks for confirmation | ✅ |
| Claude creates files in worktree | ✅ |
| Ticket moves BACKLOG → IN_PROGRESS | ✅ |
| Manual move to REVIEW (]) | ✅ |
| Move to DONE shows merge modal | ✅ |
| Merge cleans up worktree | ✅ (manual) |

### AUTO Mode Status ⚠️

AUTO mode requires `auto_start = true` in `.kagan/config.toml`. By default it's disabled per session-first design.

---

## Testing Rules

### TUI MCP Testing Workflow

When testing with TUI MCP (for AUTO and PAIR modes), **tickets must be created by directly injecting them into SQLite** to speed up testing flows. Do not use the UI ticket creation flow during automated testing.

**Example:**
```python
# In test fixtures or helpers
async def create_test_ticket(state_manager: StateManager, ticket_data: dict) -> Ticket:
    """Create ticket directly in database for fast test setup."""
    ticket = TicketCreate(**ticket_data)
    return await state_manager.create_ticket(ticket)
```

This avoids slow UI interactions and allows tests to focus on the core workflow being tested.

### Supported CLI Tools

**IMPORTANT:** The codebase must only support the following CLI tools:
- **A) OpenCode** (`opencode`)
- **B) Claude Code** (`claude`)

All other CLI tools (Codex, Gemini, Goose, etc.) are **removed** from support. The `BUILTIN_AGENTS` dictionary in `src/kagan/data/builtin_agents.py` should only contain `claude` and `opencode` entries.

### Testing Installation

**Before running any tests**, you must reinstall the latest version from the codebase:

```bash
pipx install . --force
```

This ensures that both `kagan` and `kagan-mcp` commands are available on the testing machine. The tool is not yet published to PyPI, so local installation is required.

**Note:** Always run `pipx install . --force` after making changes to ensure tests use the latest code.

---
