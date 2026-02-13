# GitHub Plugin V1 Playbook

## Mission
Ship the first official bundled GitHub plugin that makes the Kanban board the best execution surface while keeping GitHub Issues as source of truth.

## Product Constraints
- Official plugin is bundled with Kagan (no install step).
- GitHub issues are canonical task identity/state input.
- Sync direction for issues is GitHub -> Kagan.
- PR actions are allowed from Kagan for review workflow.
- Transport is gh CLI only in V1.
- No webhooks in V1 (polling + manual sync only).
- Multi-developer collision prevention is required in V1.

## Engineering Principles
- Prefer minimal moving parts over extensible abstractions.
- Keep all state transitions explicit and testable.
- Keep UI obvious: one clear action per state.
- Build for contributor readability first.
- Add guardrails before automation.
- Enforce Zen of Python: explicit, simple, readable, one obvious way.

## Persona Lens (Alpha Translation)
- Dag (terminal infra): keep rendering/event changes minimal, avoid flicker regressions, and track terminal compatibility findings.
- Mira (CLI DX): keep command surface clear, help text actionable, and startup impact small.
- Tomas (Python runtime): prefer stdlib + typed boundaries, avoid dependency and abstraction bloat.
- Yuki (TUI architecture): keep keyboard-first UX, visible state transitions, and clear error/empty states.
- Rafael (CLI platform): keep plugin contracts explicit, isolate failures, and maintain stable tool semantics.

## MVP Quality Gates (Pragmatic)
- CLI startup: no measurable regression above +30ms for `kagan --help` in local baseline checks.
- CLI errors: all GitHub plugin command failures include machine-readable code and human remediation hint.
- TUI responsiveness: sync/reconcile actions must run asynchronously and keep input responsive.
- Terminal baseline: verify behavior in at least `Terminal.app`, `iTerm2`/`WezTerm`, and `tmux` before release notes.
- Dependency discipline: no new runtime dependency for GitHub plugin V1 unless justified in initiative docs.
- Contract stability: `kagan_github_*` method names and payload schema frozen within V1 once released.

## Architecture Shape (V1)
- `kagan_github` official plugin capability.
- `GhCliAdapter` for all GitHub calls.
- `IssueSyncService` for issue projection into tasks.
- `PrWorkflowService` for create/link/reconcile PR operations.
- `LeaseService` for issue lease acquire/renew/release semantics.
- `GitHubPolicy` rules for board transitions:
  - `REVIEW` requires linked open PR.
  - merged PR transitions task to `DONE`.
  - closed unmerged PR transitions task to `IN_PROGRESS`.

## Lease/Lock Model (V1)
- Default behavior: enabled (`enforced`) for GitHub-connected repos.
- Lock signal uses GitHub label: `kagan:locked`.
- Lock holder metadata uses one marker comment per issue:
  - `kagan-lock: owner=<gh_login> instance=<kagan_instance_id> lease_until=<iso8601>`
- Lease identity is `kagan_instance_id` (not GitHub login), so same user on multiple devices still contends safely.
- Acquire:
  - if no active lease: add label + upsert marker comment.
  - if lease held by current instance: renew lease.
  - if lease held by another active instance: block with clear holder info.
- Release:
  - when task leaves active work states or explicit unlock action.
- Recovery:
  - force-takeover action for maintainers/operators only.
  - stale lease reclaim when `lease_until` has elapsed.
- Opt-out:
  - maintainers may disable lease enforcement per repo, but default remains enforced.

## Task Mode Decision (AUTO vs PAIR) for Synced Issues
- Source of truth is GitHub label policy:
  - `kagan:mode:auto` -> `AUTO`
  - `kagan:mode:pair` -> `PAIR`
- If no mode label is present, use repo default sync mode.
- V1 default repo sync mode: `PAIR` (safe, predictable for alpha users).
- Maintainers can override repo default per project/repo settings.
- Label conflict rule: `kagan:mode:pair` wins over `kagan:mode:auto` and emits a sync warning.

## Execution Phases
1. Core plugin scaffold and repo connection checks.
2. Issue sync and mapping model.
3. Lease/lock model for multi-developer coordination.
4. TUI integration for connected repo UX.
5. PR create/link/reconcile workflow.
6. MCP admin tools and runbook docs.

## Definition of Done
- Connected repo can sync issues into board reliably.
- Lease/lock behavior prevents concurrent active work on the same issue by default.
- REVIEW gate enforces PR linkage.
- PR merge/close reconciliation updates board states correctly.
- Admin MCP surface exists for connect/sync/reconcile/repair.
- AUTO/PAIR mode for synced tasks follows deterministic label/default policy.
- Initiative quality gates are documented and validated in release notes/docs.
- Tests cover critical flows and failure paths.
