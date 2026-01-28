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
- [ ] First boot journey (welcome → config → planner/kanban)
- [ ] Ticket lifecycle (create → progress → review → done)
- [ ] PAIR mode session workflow
- [ ] Delete with resource cleanup

### Interaction Tests (test_interactions.py)
- [ ] Navigation: h, j, k, l
- [ ] Ticket ops: n (new), e (edit), v (view), x (delete)
- [ ] Movement: ], [ (forward/backward)
- [ ] Type toggle: t
- [ ] Screen navigation: c (chat), escape

## Files to Keep (Unit Tests)
- test_database.py - StateManager CRUD
- test_models.py - Pydantic validation
- test_lock.py - Instance lock
- test_knowledge.py - Knowledge base
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
