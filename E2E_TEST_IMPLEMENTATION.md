# E2E Test Suite Implementation Plan

> Status: COMPLETE
> Started: January 28, 2026
> Completed: January 28, 2026

## Overview

Implementing a lightweight, user-focused E2E test suite using the hybrid approach:
- Thin page helpers (not full Page Objects)
- Real components (DB, git, tmux) with only agent CLI mocking
- Critical user journey smoke tests
- Exhaustive keyboard interaction tests

## Phase 1: Cleanup - Remove Obsolete Tests

| File | Status | Notes |
|------|--------|-------|
| `tests/test_ui.py` | DONE | Replaced by test_interactions.py |
| `tests/test_kanban_flow.py` | DONE | Replaced by test_e2e_smoke.py |
| `tests/test_merge_flow.py` | DONE | Replaced by test_e2e_smoke.py |
| `tests/test_snapshots.py` | DONE | Removed (dynamic content issues) |
| `tests/__snapshots__/` | DONE | Directory removed |

## Phase 2: Create New Test Infrastructure

| File | Status | Description |
|------|--------|-------------|
| `tests/helpers/__init__.py` | DONE | Package init |
| `tests/helpers/pages.py` | DONE | Thin page helpers (15 functions) |
| `tests/conftest.py` | DONE | Updated with E2E fixtures |

## Phase 3: Create New E2E Tests

| File | Status | Description |
|------|--------|-------------|
| `tests/test_e2e_smoke.py` | DONE | Critical user journeys (4 test classes) |
| `tests/test_interactions.py` | DONE | Keyboard shortcut coverage (6 test classes) |

## Test Coverage Goals

### Smoke Tests (test_e2e_smoke.py)
- [x] First boot journey (welcome → config → planner/kanban)
- [x] Ticket lifecycle (create → progress → review → done)
- [x] PAIR mode session workflow
- [x] Fresh repo worktree creation
- [ ] Delete with resource cleanup

### Interaction Tests (test_interactions.py)
- [x] Navigation: h, j, k, l
- [x] Ticket ops: n (new), e (edit), v (view), x (delete)
- [x] Movement: ], [ (forward/backward)
- [x] Type toggle: t
- [x] Screen navigation: c (chat), escape

### Full E2E Journeys (via TUI MCP - manual validation)
- [x] PAIR Mode: ticket → session → work → review → merge → done
- [x] Context injection: CLAUDE.md created with task instructions
- [ ] AUTO Mode: ticket → agent execution → review → done (requires auto_start=true)

## Files to Keep (Unit Tests)
- test_database.py - StateManager CRUD
- test_models.py - Pydantic validation
- test_lock.py - Instance lock
- test_prompt_loader.py - Prompt loading
- test_mcp_tools.py - MCP tools
- test_signals.py - Signal mechanism
- test_scheduler.py - Scheduler logic
- test_worktree.py - Real git operations
- test_sessions.py - Session manager
- test_planner.py - Planner parsing

## Progress Log

### 2026-01-28
- Initial plan created
- Analysis of existing tests completed
- **Phase 1 Complete**: Removed 4 obsolete test files + snapshots directory
- **Phase 2 Complete**: Created helpers/pages.py and updated conftest.py
- **Phase 3 Complete**: Created test_e2e_smoke.py and test_interactions.py
- **Validation Complete**: All 150 tests pass in 20.06s
- Fixed pytest marker warning in pyproject.toml

## Final Test Summary

| Category | Tests |
|----------|-------|
| E2E Smoke Tests | 8 |
| Interaction Tests | 14 |
| Unit Tests (kept) | 129 |
| **Total** | **151** |

## Bug Fix: Fresh Repo Worktree Creation

**Bug:** When user runs kagan in empty folder, creates PAIR ticket, presses Enter:
- Error: "failed to create worktree, fatal invalid reference: main"

**Root Cause:** `init_git_repo()` only ran `git init -b main` without creating an initial commit.
Git worktrees require at least one commit to create branches from.

**Fix:** Updated `src/kagan/git_utils.py` to create initial commit with `.gitkeep` file.

**Test Added:** `TestFreshProjectWorktree::test_pair_ticket_worktree_creation_fresh_repo`

**Why E2E tests missed it:** The `e2e_project` fixture created a git repo WITH an initial commit,
but the real `init_git_repo()` didn't. Added new `e2e_fresh_project` fixture that simulates
a completely empty folder where kagan must initialize git itself.

---

## TUI MCP Full E2E Testing (2026-01-28)

### Testing Method
Used `user-tui-mcp` MCP server to automate the TUI for true E2E testing:
- `tui_launch`: Start kagan in temp folder
- `tui_snapshot`: Get current screen state
- `tui_press_key`: Simulate keyboard input
- `tui_click`: Click on UI elements
- `tui_send_text`: Type text

### PAIR Mode Full Flow - Verified ✅

| Step | Action | Result |
|------|--------|--------|
| 1 | Launch kagan in fresh folder | Welcome screen appears |
| 2 | Click "Start Using Kagan" | Git repo initialized, moves to Planner |
| 3 | Press Escape | Kanban board with 4 columns |
| 4 | Press 'n' | New Ticket modal opens |
| 5 | Enter title + description | Fields populated |
| 6 | Ctrl+S | Ticket created in BACKLOG |
| 7 | Press Enter | Worktree + tmux session created |
| 8 | Claude Code opens | Shows CLAUDE.md task automatically |
| 9 | Work on task | Claude creates files |
| 10 | Press ']' | Ticket moves to REVIEW |
| 11 | Press ']' on REVIEW | Merge confirmation modal |
| 12 | Confirm merge | Worktree merged, cleaned up, ticket in DONE |

### Context Injection Fix (BUG-003)

**Before fix:** Claude Code opened with generic welcome, no task context.

**After fix:** `CLAUDE.md` created at worktree root with:
```markdown
# Task: {ticket.title}

## Description
{ticket.description}

## Instructions
1. Review this task and confirm you understand it
2. Ask the user if they are ready to proceed before making changes
3. Work in this worktree directory only
4. When complete, call the `kagan_request_review` MCP tool to submit for review

## MCP Tools Available
- `kagan_get_context` - Refresh ticket details
- `kagan_update_scratchpad` - Save progress notes
- `kagan_request_review` - Submit work for review

## Detach Instructions
When finished working, the user can detach from this session:
- Press `Ctrl+b` then `d` to detach and return to the Kagan board
```

### AUTO Mode Status

AUTO mode is disabled by default (`auto_start = false` in config). When enabled:
1. Scheduler spawns agents for IN_PROGRESS AUTO tickets
2. Agent runs via ACP protocol
3. AgentOutputModal shows streaming output
4. Agent moves ticket to REVIEW when complete

To enable: Edit `.kagan/config.toml` and set `auto_start = true`

### Known Limitations

1. **MCP Connection**: User must run `claude mcp add kagan -- kagan mcp` to enable MCP tools
2. **TUI MCP Modal Keys**: Some modal confirmations don't respond to TUI MCP key simulation (works fine with real keyboard)

---
