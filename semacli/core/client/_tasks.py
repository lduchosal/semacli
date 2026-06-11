"""Task endpoints (run, output, history).

Note on the POST /tasks body shape: it matches Semaphore's `db.Task` +
`AnsibleTaskParams` — ansible-flavoured flags (limit/tags/skip_tags/
dry_run/diff/debug/debug_level) belong under a nested `params` object.
Sending them at the top level — as semacli did before ken #782 — was
silently dropped by the server's `db.Task` json.Unmarshal because the
struct only carries a deprecated top-level `Limit` string.
"""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Task
from ._base import BaseClient, _split_csv


def _csv_params(limit: str | None, tags: str | None, skip_tags: str | None) -> dict[str, Any]:
    """Normalise comma-separated cli inputs to the []string the server expects."""
    params: dict[str, Any] = {}
    if limit:
        params["limit"] = _split_csv(limit)
    if tags:
        params["tags"] = _split_csv(tags)
    if skip_tags:
        params["skip_tags"] = _split_csv(skip_tags)
    return params


class TasksMixin(BaseClient):
    """Run, inspect and stop tasks."""

    def run_task(  # noqa: PLR0913  # one parameter per payload field (API wrapper)
        self,
        project_id: int,
        template_id: int,
        playbook: str | None = None,
        environment: str | None = None,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
        debug: int = 0,
        *,
        dry_run: bool = False,
        diff: bool = False,
    ) -> Task:
        """POST /api/project/{pid}/tasks — launch a task from a template.

        `debug` is an ansible verbosity level (0=off, 1=-v ... 4=-vvvv);
        we emit both `debug: true` (toggle) and `debug_level: <n>` (int)
        because that is what `AnsibleTaskParams` expects. Comma-separated
        cli inputs (`--limit a,b`) are normalised to `[]string` — see the
        module docstring for the body-shape rationale (ken #782).
        """
        body: dict[str, Any] = {"template_id": template_id}
        if playbook is not None:
            body["playbook"] = playbook
        if environment is not None:
            body["environment"] = environment

        params = _csv_params(limit, tags, skip_tags)
        if dry_run:
            params["dry_run"] = True
        if diff:
            params["diff"] = True
        if debug:
            params["debug"] = True
            params["debug_level"] = debug
        if params:
            body["params"] = params

        data = self._request(f"project/{project_id}/tasks", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /tasks"
            raise SemaphoreAPIError(msg)
        return Task.model_validate(data)

    def get_task(self, project_id: int, task_id: int) -> Task:
        """GET /api/project/{pid}/tasks/{tid}."""
        data = self._request(f"project/{project_id}/tasks/{task_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /tasks/{tid}"
            raise SemaphoreAPIError(msg)
        return Task.model_validate(data)

    def get_task_output(self, project_id: int, task_id: int) -> list[dict[str, Any]]:
        """GET /api/project/{pid}/tasks/{tid}/output — list of {time, output}."""
        data = self._request(f"project/{project_id}/tasks/{task_id}/output")
        if not isinstance(data, list):
            return []
        return data

    def get_task_raw_output(self, project_id: int, task_id: int) -> str:
        """GET /api/project/{pid}/tasks/{tid}/raw_output."""
        data = self._request(f"project/{project_id}/tasks/{task_id}/raw_output")
        if isinstance(data, str):
            return data
        return ""

    def list_tasks(self, project_id: int) -> list[Task]:
        """GET /api/project/{pid}/tasks — task history."""
        data = self._request(f"project/{project_id}/tasks")
        if not isinstance(data, list):
            msg = "Unexpected response for /tasks"
            raise SemaphoreAPIError(msg)
        return [Task.model_validate(t) for t in data]

    def stop_task(self, project_id: int, task_id: int) -> None:
        """POST /api/project/{pid}/tasks/{tid}/stop."""
        self._request(f"project/{project_id}/tasks/{task_id}/stop", method="POST", body={})
