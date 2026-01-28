# Kagan Cleanup Plan (Delegable Batches)

## Completion Status

| Batch | Description | Status |
|-------|-------------|--------|
| 1 | Dead Code + Unused Artifacts | ✅ Complete |
| 2 | Prompt + Template Consolidation | ✅ Complete |
| 3 | Status Ordering + Enum Normalization | ✅ Complete |
| 4 | Magic Constants to Named Constants | ✅ Complete |
| 5 | CSS Rule Compliance | ✅ Complete |
| 6 | Agent Config Resolution Unification | ✅ Complete |
| 7 | Test Suite Slimming | ✅ Complete |
| 8 | Documentation + Alignment | ✅ Complete |

**Note:** Knowledge feature was removed per MVP decision (Batch 1).

---

## Goals
- Reduce maintenance cost and duplication.
- Remove dead/unused code and tests.
- Centralize constants and workflow rules.
- Align tests with user-facing behavior so regressions are caught without manual TUI runs.

## Constraints
- Follow AGENTS.md rules (CSS only in `kagan.tcss`, async DB access only via `StateManager`, etc.).
- Keep changes small, batchable, and independently reviewable.
- Prefer refactors that reduce future change friction.

---

## Batch 1 — Dead Code + Unused Artifacts (Subagent A)
**Focus:** Remove code paths that are unused or out of scope for the current product.

**Tasks**
- Remove the unused Knowledge feature stack:
  - `src/kagan/database/knowledge.py`
  - `KnowledgeBase` usage in `src/kagan/app.py`
  - `StateManager.add_knowledge/search_knowledge` in `src/kagan/database/manager.py`
  - Knowledge tables + FTS in `src/kagan/database/schema.sql`
  - Tests in `tests/test_knowledge.py`
- Remove unused constants / symbols:
  - `PLANNER_SESSION_ID`, `PLANNER_PREAMBLE`, `PLANNER_SYSTEM_PROMPT` in `src/kagan/agents/planner.py`
  - `ModalAction.EDIT` in `src/kagan/ui/modals/actions.py`
  - `_status_log_max_height` in `src/kagan/ui/widgets/streaming_output.py`
- Audit repo root for stray files:
  - Confirm removal/ignore of `site/`, `snapshot_report.html`, `bla2.txt` if not required.

**Deliverables**
- PR with deletions + updated imports.
- Updated schema + migration note (if needed).

**Acceptance Criteria**
- No references to removed code remain.
- Tests updated/removed accordingly.

---

## Batch 2 — Prompt + Template Consolidation (Subagent B)
**Focus:** One source of truth for planner/iteration prompts; avoid mismatched defaults.

**Tasks**
- Make `PromptLoader` defaults match the actual planner parsing requirements (multi-ticket `<plan>` output).
- Remove duplicated prompt templates between `src/kagan/agents/prompt.py` and `src/kagan/agents/prompt_loader.py`.
- Ensure `dump_default_prompts()` writes the correct templates (planner + iteration as needed).
- Align tests in `tests/test_prompt_loader.py` and `tests/test_planner.py` to the new behavior.

**Acceptance Criteria**
- Planner prompt defaults and tests agree on format.
- No duplicate fallback template definitions.

---

## Batch 3 — Status Ordering + Enum Normalization (Subagent C)
**Focus:** De-duplicate status ordering and enum conversion logic.

**Tasks**
- Centralize status ordering in one place (e.g., `kagan.constants` or a helper).
- Update:
  - `TicketStatus.next_status/prev_status`
  - SQL ordering in `src/kagan/database/queries.py`
  - Any status-based UI ordering
- Introduce normalization helpers for ticket enums (priority/type/status) to eliminate repeated `isinstance(..., str/int)` blocks.

**Acceptance Criteria**
- One ordering source is used across model, UI, and queries.
- Enum conversion duplication significantly reduced.

---

## Batch 4 — Magic Constants to Named Constants (Subagent D)
**Focus:** Replace scattered UI numbers with named constants.

**Tasks**
- Create `src/kagan/ui/constants.py` (or extend `kagan/constants.py`) and move numeric UI constants:
  - Truncation lengths in `TicketCard`
  - Modal title truncation lengths
  - Screen size mins
  - Scheduler/command defaults (e.g., default check command)
- Replace the hard-coded “4 columns” with `len(COLUMN_ORDER)`.

**Acceptance Criteria**
- All UI magic numbers are centralized and named.
- No hard-coded column count.

---

## Batch 5 — CSS Rule Compliance (Subagent E)
**Focus:** Enforce “CSS in .tcss only”.

**Tasks**
- Move `DEFAULT_CSS` from `src/kagan/ui/widgets/streaming_output.py` into `src/kagan/styles/kagan.tcss`.
- Remove `DEFAULT_CSS` from the Python class.

**Acceptance Criteria**
- `rg -n "DEFAULT_CSS" src/kagan` returns no results.

---

## Batch 6 — Agent Config Resolution Unification (Subagent F)
**Focus:** Centralize agent config selection logic.

**Tasks**
- Create a single resolver (e.g., `kagan/agents/config.py`) used by:
  - `Scheduler._get_agent_config`
  - `SessionManager._get_agent_config`
  - `KanbanScreen.action_open_review`
- Ensure fallback order is consistent across all usage.

**Acceptance Criteria**
- No duplicated agent resolution logic.
- Clear priority order documented and tested.

---

## Batch 7 — Test Suite Slimming (Subagent G)
**Focus:** Remove redundant/overly internal tests and keep user-facing flows covered.

### Redundant / overly internal tests (candidates to remove or consolidate)
- `tests/test_models.py`:
  - Most checks are internal and overlapped by DB + UI flows. Keep only validation edge cases if needed.
- `tests/test_database.py`:
  - Many CRUD permutations can be collapsed into 2–3 tests (create, update, move, scratchpad limit).
  - The “new fields” section is repetitive; replace with one round-trip test.
- `tests/test_worktree.py`:
  - `TestWorktreeManagerRepoRoot` and slugify detail tests are low-level; keep 1–2 behavior tests or replace with E2E flow.
- `tests/test_scheduler.py`:
  - Extensive mock agent cases are heavy and internal; keep minimal coverage for AUTO vs PAIR and completion -> REVIEW/DONE.
- `tests/test_mcp_tools.py`:
  - `_check_uncommitted_changes` granularity is internal; replace with 1–2 tests through `request_review` only.
- `tests/test_troubleshooting.py`:
  - Many UI presence checks are repetitive; keep 1 detection test + 1 UI render test.
- `tests/test_signals.py`:
  - Dozens of format variations are internal; keep 3–4 representative cases.
- `tests/test_planner.py`:
  - Drop `PLANNER_SESSION_ID` check and some XML parsing variants; keep 2–3 high-value parse cases.
- `tests/test_interactions.py`:
  - Multiple keybinding tests overlap with `test_e2e_smoke.py`; keep only a lean set of high-signal keybindings.

### Lean test suite target (user-facing focus)
- **E2E smoke** (`tests/test_e2e_smoke.py`): keep as primary UI regression coverage.
- **Interactions**: keep a trimmed subset verifying core shortcuts (create ticket, move forward/back, open planner).
- **Planner**: one UI test for creating tickets from plan + one parser test for multi-ticket.
- **Scheduler**: one test ensuring AUTO tickets in IN_PROGRESS progress to REVIEW with mocked signals.
- **MCP**: one test for `request_review` success + one for uncommitted block.
- **Troubleshooting**: one detection test + one UI render test.

### Deliverables
- A new slimmed test plan document inside `cleanup.md` or `tests/README.md`.
- PR removing redundant tests and adjusting fixtures to reduce runtime.

**Acceptance Criteria**
- Test runtime reduced meaningfully.
- Critical user flows covered without manual TUI testing.

---

## Batch 8 — Documentation + Alignment (Subagent H)
**Focus:** Keep docs aligned with the refactors.

**Tasks**
- Update `AGENTS.md` or other docs if any removed module is mentioned.
- Add a short “Testing Strategy” note describing the lean suite and its focus.

**Acceptance Criteria**
- Docs accurately describe remaining architecture and tests.

---

## Suggested Order / Dependencies
1) Batch 1 (dead code removal) before any test cleanup.
2) Batch 2 (prompt consolidation) before test updates to prompt behavior.
3) Batch 3/4/5 can be parallelized.
4) Batch 7 depends on earlier removals to avoid rework.
5) Batch 8 last.
