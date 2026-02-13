---
title: MCP tools reference
description: Consolidated tool catalog, pagination contract, and scope rules
icon: material/tools
---

# MCP tools reference

This document defines the consolidated MCP toolset for Kagan.
It is a breaking, non-backward-compatible contract.

## Annotation model

| Annotation    | Meaning                            |
| ------------- | ---------------------------------- |
| `read-only`   | Reads state only                   |
| `mutating`    | Modifies state                     |
| `mixed`       | Action-dependent read/write modes  |
| `destructive` | Irreversible/high-impact operation |

## Tool catalog

### Core task workflow

| Tool                | Annotation    | Purpose |
| ------------------- | ------------- | ------- |
| `task_get(...)`     | `read-only`   | Read bounded task snapshot (`summary`) or full bounded context (`context`) |
| `task_list(...)`    | `read-only`   | Paginated task listing |
| `task_stream(...)`  | `read-only`   | Paginated large task data (`notes` or `logs`) |
| `task_wait(...)`    | `read-only`   | Long-poll task status changes |
| `task_create(...)`  | `mutating`    | Create a task |
| `task_patch(...)`   | `mutating`    | Apply partial task changes, transitions, or note append |
| `task_delete(...)`  | `destructive` | Delete a task |

### Automation jobs

| Tool             | Annotation  | Purpose |
| ---------------- | ----------- | ------- |
| `job_start(...)` | `mutating`  | Submit async automation action for a task |
| `job_poll(...)`  | `read-only` | Read job state; optionally wait and/or page events |
| `job_cancel(...)` | `mutating`  | Cancel a submitted job |

### PAIR session lifecycle

| Tool                  | Annotation | Purpose |
| --------------------- | ---------- | ------- |
| `session_manage(...)` | mixed      | `open`, `read`, or `close` PAIR session state |

### Project, review, and admin

| Tool                 | Annotation    | Purpose |
| -------------------- | ------------- | ------- |
| `project_list(...)`  | `read-only`   | Paginated project listing |
| `project_open(...)`  | `mutating`    | Open/switch project |
| `repo_list(...)`     | `read-only`   | Paginated repo listing by project |
| `review_apply(...)`  | `destructive` | Apply review action (`approve`, `reject`, `merge`, `rebase`) |
| `audit_list(...)`    | `read-only`   | Paginated audit events |
| `settings_get()`     | `read-only`   | Read allowlisted settings |
| `settings_set(...)`  | `mutating`    | Update allowlisted settings |
| `plan_submit(...)`   | `mutating`    | Submit planner proposal payload |

## Pagination Contract

Kagan uses cursor pagination for every unbounded read.

### Request

| Field    | Type     | Description |
| -------- | -------- | ----------- |
| `cursor` | `string` | Opaque position token returned by previous page |
| `limit`  | `int`    | Maximum items/chunks per page |

### Response

| Field         | Type              | Description |
| ------------- | ----------------- | ----------- |
| `items`       | `list[object]`    | Returned page payload |
| `next_cursor` | `string \| null`  | `null` means end of sequence |

Cursor tokens are opaque and server-owned. Clients must not parse them.

## `task_stream` API

`task_stream` is the only API for large task fields.
`task_get` never returns unbounded blobs.

### Parameters

| Parameter | Type | Description |
| --------- | ---- | ----------- |
| `task_id` | `string` | Target task |
| `stream`  | `string` | `notes` or `logs` |
| `cursor`  | `string \| null` | Pagination cursor |
| `limit`   | `int` | Page size |

## `task_patch` API

`task_patch` is the single task mutation endpoint for incremental updates.

### Parameters

| Parameter     | Type | Description |
| ------------- | ---- | ----------- |
| `task_id`     | `string` | Target task |
| `set`         | `object \| null` | Partial field updates (title, description, status, priority, task_type, etc.) |
| `transition`  | `string \| null` | `request_review`, `set_status`, or `set_task_type` |
| `append_note` | `string \| null` | Text appended to task notes stream |

## `task_wait` long-poll API

`task_wait` blocks until a task changes or timeout is reached.

### Parameters

| Parameter         | Type           | Default               | Description |
| ----------------- | -------------- | --------------------- | ----------- |
| `task_id`         | `string`       | required              | Task to watch |
| `timeout_seconds` | `float|string` | server default (900s) | Maximum wait duration |
| `wait_for_status` | `list|string`  | `null`                | Optional status filter |
| `from_updated_at` | `string`       | `null`                | Race-safe resume cursor |

### Response codes

| Code                   | Meaning |
| ---------------------- | ------- |
| `TASK_CHANGED`         | Status or task state changed |
| `ALREADY_AT_STATUS`    | Task already matches filter |
| `CHANGED_SINCE_CURSOR` | Task changed after supplied cursor |
| `WAIT_TIMEOUT`         | Timeout reached |
| `WAIT_INTERRUPTED`     | Wait cancelled/interrupted |
| `TASK_DELETED`         | Task deleted while waiting |
| `INVALID_TIMEOUT`      | Invalid timeout value |
| `INVALID_PARAMS`       | Invalid parameter payload |

## Scope and isolation

- Task mutations are enforced against task-scoped sessions (`task:<task_id>`).
- PAIR workers use task-scoped MCP sessions with capability lane `pair_worker`.
- AUTO workers use task-scoped MCP sessions resolved from runtime permission policy.
- Scoped task sessions cannot mutate other task IDs.
- Global MCP access does not override task-scoped worker isolation.

### Timeout configuration

Default and max timeouts are server-side configurable via settings:

- `general.tasks_wait_default_timeout_seconds`
- `general.tasks_wait_max_timeout_seconds`

## Task field semantics

- `status` is Kanban state: `BACKLOG`, `IN_PROGRESS`, `REVIEW`, `DONE`.
- `task_type` is execution mode: `AUTO`, `PAIR`.
- `acceptance_criteria` accepts either a single string or a list of strings.

## Common recovery codes

| Code                   | Meaning                                         | Typical action                      |
| ---------------------- | ----------------------------------------------- | ----------------------------------- |
| `START_PENDING`        | Job accepted, pending scheduler admission       | Poll with `job_poll(wait=false)`    |
| `DISCONNECTED`         | Core unavailable                                | Start/restart core, retry           |
| `AUTH_STALE_TOKEN`     | MCP token is stale after core restart           | Reconnect MCP client                |
| `WAIT_TIMEOUT`         | `task_wait` timed out without a change          | Retry with same or adjusted timeout |
| `WAIT_INTERRUPTED`     | `task_wait` was interrupted/cancelled           | Retry with `from_updated_at` cursor |

## Capability profiles

Higher profiles include lower-level permissions.

| Profile       | Scope                                                                  |
| ------------- | ---------------------------------------------------------------------- |
| `viewer`      | Read-only operations                                                   |
| `planner`     | `viewer` + `plan_submit`                                               |
| `pair_worker` | `planner` + task mutation, automation, and PAIR session lifecycle      |
| `operator`    | `pair_worker` + create/update/move + non-destructive review operations |
| `maintainer`  | `operator` + destructive/admin operations                              |

## Identity lanes

| Identity      | Notes                                         |
| ------------- | --------------------------------------------- |
| `kagan`       | Default safe lane                             |
| `kagan_admin` | Explicit elevated lane for trusted automation |
