from __future__ import annotations

import json

from kagan.agents.planner import parse_proposed_plan


def test_parse_proposed_plan_from_content_when_title_is_truncated() -> None:
    full_payload = {
        "status": "received",
        "task_count": 4,
        "todo_count": 0,
        "tasks": [
            {"title": "Initialize project", "type": "AUTO"},
            {"title": "Build API client", "type": "AUTO"},
            {"title": "Implement UI", "type": "PAIR"},
            {"title": "Wire configuration", "type": "AUTO"},
        ],
        "todos": [],
    }
    tool_calls = {
        "tc-plan": {
            "name": "propose_plan",
            "status": "completed",
            "title": 'propose_plan: {"tasks":[{"title":"Initi..."}]}',
            "content": [
                {
                    "type": "content",
                    "content": {
                        "type": "text",
                        "text": json.dumps(full_payload),
                    },
                }
            ],
        }
    }

    tasks, todos, error = parse_proposed_plan(tool_calls)

    assert error is None
    assert len(tasks) == 4
    assert tasks[0].title == "Initialize project"
    assert todos is None
