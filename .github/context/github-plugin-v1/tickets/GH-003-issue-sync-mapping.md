# GH-003 - Issue Sync and Mapping Projection

Status: Done
Owner: Codex
Depends On: GH-002

## Outcome
GitHub issues are synchronized into Kagan task projections.

## Scope
- Add incremental sync operation and checkpoint tracking.
- Upsert task projection from issue metadata.
- Maintain issue-to-task mapping and repair hooks.
- Resolve task mode from labels/default policy during sync.

## Acceptance Criteria
- Sync is idempotent.
- Re-running sync without remote changes produces no task churn.
- Mapping recovery path exists for drift.

## Verification
- Unit tests for insert/update/reopen/close flows.

## Implementation Summary

### Files Added
- `src/kagan/core/plugins/official/github/sync.py` - Sync state, mapping, and mode resolution logic

### Files Modified
- `src/kagan/core/plugins/official/github/contract.py` - Added `GITHUB_METHOD_SYNC_ISSUES` operation
- `src/kagan/core/plugins/official/github/plugin.py` - Registered sync_issues handler
- `src/kagan/core/plugins/official/github/gh_adapter.py` - Added `GhIssue`, `run_gh_issue_list()`, `parse_gh_issue_list()`
- `src/kagan/core/plugins/official/github/runtime.py` - Implemented `handle_sync_issues()` handler

### Test File Added
- `tests/core/unit/test_github_issue_sync.py` - 30 unit tests covering:
  - Label-based task type resolution (AUTO/PAIR)
  - Issue state to task status mapping
  - Task title/description formatting
  - Checkpoint serialization/loading
  - Issue-to-task mapping persistence
  - gh issue list JSON parsing
  - Insert flow (new issues create tasks)
  - Update flow (modified issues update tasks)
  - Close flow (closed issues move tasks to DONE)
  - Reopen flow (reopened issues move tasks back to BACKLOG)
  - Idempotency (re-running sync without changes = no churn)
  - Mode resolution from labels

### Key Design Decisions
1. **Checkpoint storage**: Uses `Repo.scripts` JSON storage for `kagan.github.sync_checkpoint`
2. **Issue mapping**: Uses `Repo.scripts` for `kagan.github.issue_mapping` with bidirectional lookup
3. **Mode resolution**: Labels `kagan:auto` and `kagan:pair` control TaskType; defaults to PAIR
4. **Task title format**: `[GH-{number}] {title}` for clear attribution
5. **Drift recovery**: If mapped task is deleted, sync recreates it with updated mapping
