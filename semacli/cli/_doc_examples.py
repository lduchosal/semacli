"""Curated examples + REST endpoints + return-type hints for ``semacli docs``.

This is the **single source of truth for examples**. Each key is the
space-joined command path (matching what ``semacli docs list`` prints).
Click introspection covers actions, params, and types — this fixture
covers what introspection cannot reach: realistic CLI invocations,
expected output, the underlying REST endpoint, and the pydantic model
shaping the response.

When you add a new command, add an entry here. ``tests/unit/test_docs.py``
fails if an example references a command that does not exist in the
Click tree, so the doc cannot drift silently.
"""

from typing import Any

EXAMPLES: dict[str, dict[str, Any]] = {
    "templates": {
        "endpoint": "GET /api/project/{project_id}/templates",
        "returns": "list[Template]",
        "model": "Template",
        "example_call": "semacli templates",
        "example_output_text": (
            "  42  deploy-web          (deploy.yml)\n"
            "  43  backup-db           (backup.yml)\n"
            "  44  rotate-keys         (keys.yml)\n"
            "\n"
            "Total: 3 template(s)"
        ),
        "example_output_json": (
            "[\n"
            '  {"id": 42, "project_id": 1, "name": "deploy-web", '
            '"playbook": "deploy.yml", "inventory_id": 3, '
            '"repository_id": 1, "environment_id": 2, "description": ""},\n'
            '  {"id": 43, "project_id": 1, "name": "backup-db", '
            '"playbook": "backup.yml", "inventory_id": 3, '
            '"repository_id": 1, "environment_id": 2, "description": ""}\n'
            "]"
        ),
    },
    "tasks raw-output": {
        "endpoint": "GET /api/project/{project_id}/tasks/{task_id}/raw_output",
        "returns": "str (text) | {output: str} (--json)",
        "model": None,
        "example_call": "semacli tasks raw-output 1234",
        "example_output_text": (
            "PLAY [all] *********************************************************\n"
            "TASK [Gathering Facts] *********************************************\n"
            "ok: [host1]\n"
            "TASK [deploy] ******************************************************\n"
            "changed: [host1]\n"
            "PLAY RECAP *********************************************************\n"
            "host1 : ok=2 changed=1 unreachable=0 failed=0"
        ),
        "example_output_json": '{"output": "PLAY [all] ***\\nTASK [...]..."}',
    },
}
