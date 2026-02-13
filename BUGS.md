# Kagan Operational Bugs Observed During GH Initiative Orchestration

Date: 2026-02-13
Project: `kagan` (`c0cb25a3`)
Context: Creating and executing `.github/context/github-plugin-v1` GH tasks purely via Kagan MCP tools.
Naming note: All entries below use consolidated MCP names (`task_*`, `job_*`, `session_manage`).

## 1) `task_create` contract/type mismatch for `acceptance_criteria` [RESOLVED]

- Observed behavior:
  - `task_create` rejected string input for `acceptance_criteria` with validation error:
    - "Input should be a valid list"
- Why this is anomalous:
  - Tool/interface docs in this environment advertised `acceptance_criteria` as a scalar string.
  - Runtime requires a list.
- Impact:
  - Initial bulk task creation failed; orchestration required retry with list payloads.
- Suggested fix:
  - Align tool schema/docs and runtime validation to the same type.
- Resolution:
  - `acceptance_criteria` now accepts either a single string or a list of strings in MCP and core request handlers.
  - Tool signatures and docs were updated to reflect accepted input forms.

## 2) `task_wait` appears non-functional (opaque empty error) [RESOLVED]

- Observed behavior:
  - Multiple calls to `task_wait` returned:
    - `Error executing tool task_wait: `
  - No code/message/hint payload.
- Inputs attempted:
  - `wait_for_status` as JSON string, CSV string, and list.
  - `timeout_seconds` as string and integer.
- Impact:
  - Could not use intended long-poll mechanism for task status progression.
  - Forced fallback to manual polling through `task_list`.
- Suggested fix:
  - Return typed validation and server errors with non-empty message/code.
  - Verify request decoding for `wait_for_status` and `timeout_seconds`.
- Resolution:
  - `task_wait` now accepts numeric-string `timeout_seconds` and `wait_for_status` as list, CSV string, or JSON-list string.
  - Bridge errors now guarantee non-empty fallback messages when core returns blank error text.

## 3) `task_get` can fail with chunk/separator errors [RESOLVED]

- Observed behavior:
  - `task_get` (summary/full) intermittently failed with:
    - "Separator is not found, and chunk exceed the limit"
    - "Separator is found, but chunk is longer than limit"
- Impact:
  - Direct task introspection became unreliable while task execution was active.
  - Required fallback to `task_list` and `task_get(mode=context)`.
- Suggested fix:
  - Harden chunking/stream framing in `task_get` response path.
  - Truncate or paginate large fields (logs/scratchpad) safely with structured metadata.
- Resolution:
  - Added truncation for large `description` and `acceptance_criteria` fields.
  - Added response-size budgeting with a final safety valve to keep payloads transport-safe.

## 4) `task_list(include_scratchpad=true)` did not return scratchpad content [RESOLVED]

- Observed behavior:
  - `task_list` with `include_scratchpad=true` still returned `scratchpad: null` for active task.
  - `task_get(mode=context)` for same task showed non-empty scratchpad.
- Impact:
  - Inconsistent observability between task-list and task-context APIs.
- Suggested fix:
  - Ensure `include_scratchpad` is honored consistently in `task_list`.
- Resolution:
  - `tasks.list` handler now reads `include_scratchpad` and populates per-task scratchpad content.

## 5) `task_get` summary/full payload paths still exceed MCP transport chunk limits [RESOLVED]

- Observed behavior:
  - `task_get` still fails on `mode=summary` and `mode=full` with separator/chunk errors, e.g.:
    - "Separator is not found, and chunk exceed the limit"
    - "Separator is found, but chunk is longer than limit"
  - Reproduced post-reinstall on latest consolidated tool surface with:
    - `task_get(task_id=39c01113, mode=full, include_logs=true, include_scratchpad=true)`
    - `task_get(task_id=39c01113, mode=summary, include_scratchpad=true)`
    - `task_get(task_id=7be6b6b8, mode=summary)`
    - `task_get(task_id=7be6b6b8, mode=full, include_logs=true, include_scratchpad=true)`
- Contrasting successful path:
  - `task_get(task_id=7be6b6b8, mode=context)` succeeds in the same session.
- Current contrasting behavior:
  - `task_wait` now returns structured timeout/status responses (no empty opaque error).
  - `task_list(include_scratchpad=true)` now returns scratchpad text.
- Impact:
  - Summary/full task introspection remains unreliable.
  - Orchestration has to rely on `task_list`, `task_get(mode=context)`, and `job_poll(events=true, ...)` as workaround paths.
- Suggested fix:
  - Bound scratchpad/log fetches at the core request-handler level so oversized blobs never reach MCP response framing.
  - Keep bridge-side payload budgeting and add graceful overflow fallback for optional fields.
- Resolution:
  - Added core-side bounded fetch controls for `tasks.scratchpad` and `tasks.logs`:
    - `content_char_limit`
    - `total_char_limit` (logs)
  - Updated bridge `task_get` to request bounded scratchpad/log payloads before response assembly.
  - Added overflow-aware fallback for optional fields:
    - `scratchpad` falls back to bounded placeholder with `scratchpad_truncated=true`
    - `logs` falls back to `[]` with `logs_truncated=true`
    - Transport-overflow errors no longer fail the entire `task_get` call.
  - Tightened full-mode response budget and kept final safety-valve trimming.
  - Added regression tests for bounded fetch params and transport-overflow degradation behavior.

## 6) MCP docs still referenced legacy tool names in setup/troubleshooting [RESOLVED]

- Observed behavior:
  - MCP setup and troubleshooting pages were out of sync with the consolidated tool contract.
- Impact:
  - Users could run invalid verification/recovery calls against the consolidated tool contract docs.
- Resolution:
  - Updated docs to consolidated names:
    - `task_list` for connectivity verification
    - `job_start` / `job_poll(wait=false)` for `START_PENDING` recovery
  - Updated pages:
    - `docs/guides/mcp-setup.md`
    - `docs/guides/editor-mcp-setup.md`
    - `docs/troubleshooting.md`
    - `docs/reference/mcp-tools.md`

## 7) Legacy wrapper names (`tasks_*`, `jobs_*`) still exposed in client tool surface [RESOLVED]

- Observed behavior:
  - Documentation used consolidated names, but some client call surfaces still exposed legacy wrapper names.
- Impact:
  - Inconsistent operator experience and confusion about the canonical MCP contract.
- Suggested fix:
  - Remove legacy wrappers entirely and keep one obvious tool surface.
- Resolution:
  - Removed legacy MCP wrapper tool names from the exposed tool surface.
  - Updated MCP contract/smoke tests to use only consolidated names.
  - Updated agent prompts and docs to consistently reference consolidated tools only.
