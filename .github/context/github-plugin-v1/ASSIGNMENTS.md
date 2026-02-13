# Assignments

## Workstream 1: Core Plugin + Sync
- Owner: Codex
- Scope:
  - official `kagan_github` plugin registration
  - gh preflight/connect flow
  - issue sync projection + mapping
- Deliverables:
  - plugin module in `src/kagan/core/plugins/official/github/`
  - tests for sync and mapping behavior

## Workstream 2: TUI UX
- Owner: Codex
- Scope:
  - connected-repo indicator
  - sync/reconcile actions
  - REVIEW gate requiring PR link
  - lease/lock holder visibility and takeover action
- Deliverables:
  - kanban UI/controller updates
  - smoke tests for core user paths

## Workstream 3: MCP Admin Surface
- Owner: Codex
- Scope:
  - `kagan_github_*` MCP operations
  - admin-safe errors and remediation hints
- Deliverables:
  - MCP registrar/tool mapping
  - contract tests for key operations

## Workstream 4: Collaboration Policy
- Owner: Codex
- Scope:
  - label/comment-based lease enforcement
  - AUTO/PAIR sync mode label/default policy
- Deliverables:
  - policy implementation + tests
  - user-facing docs for policy behavior

## Workstream 5: Quality Gate Pass
- Owner: Codex
- Scope:
  - apply `PERSONA-QUALITY-GATES.md` checks to implementation and docs
  - ensure no over-engineered infrastructure is introduced for V1
- Deliverables:
  - concise validation notes in runbook/release docs
  - explicit known-limitations section for alpha users

## Human Review Checkpoints
- Approve scope freeze before WS2 starts.
- Approve command names before MCP exposure.
- Approve final UX text before merge.
