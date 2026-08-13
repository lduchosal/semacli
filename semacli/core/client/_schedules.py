"""Schedule endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Schedule
from ._base import BaseClient, _split_csv


def _ansible_params(limit: str | None, tags: str | None, skip_tags: str | None) -> dict[str, Any]:
    """Normalise comma lists to the []string the server's task params expect."""
    params: dict[str, Any] = {}
    if limit:
        params["limit"] = _split_csv(limit)
    if tags:
        params["tags"] = _split_csv(tags)
    if skip_tags:
        params["skip_tags"] = _split_csv(skip_tags)
    return params


def _task_params(  # noqa: PLR0913, PLR0917  # one parameter per schedule task-param field
    message: str | None,
    inventory_id: int | None,
    cli_args: str | None,
    limit: str | None,
    tags: str | None,
    skip_tags: str | None,
) -> dict[str, Any]:
    """Build the schedule's nested ``task_params`` (Semaphore db.TaskParams).

    ``inventory_id`` / ``message`` / ``arguments`` sit at this level;
    ansible ``--limit/--tags/--skip-tags`` go in the nested ``params``.
    Returns ``{}`` when nothing is set, so callers can omit the key.
    """
    tp: dict[str, Any] = {}
    if message is not None:
        tp["message"] = message
    if inventory_id is not None:
        tp["inventory_id"] = inventory_id
    if cli_args is not None:
        tp["arguments"] = cli_args
    params = _ansible_params(limit, tags, skip_tags)
    if params:
        tp["params"] = params
    return tp


class SchedulesMixin(BaseClient):
    """CRUD on schedules."""

    def list_schedules(self, project_id: int) -> list[Schedule]:
        """GET /api/project/{pid}/schedules."""
        data = self._request(f"project/{project_id}/schedules")
        if not isinstance(data, list):
            msg = "Unexpected response for /schedules"
            raise SemaphoreAPIError(msg)
        return [Schedule.model_validate(s) for s in data]

    def get_schedule(self, project_id: int, sched_id: int) -> Schedule:
        """GET /api/project/{pid}/schedules/{sid}."""
        data = self._request(f"project/{project_id}/schedules/{sched_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /schedules/{sid}"
            raise SemaphoreAPIError(msg)
        return Schedule.model_validate(data)

    def create_schedule(  # noqa: PLR0913  # one parameter per payload field (API wrapper)
        self,
        project_id: int,
        template_id: int,
        cron_format: str,
        name: str = "",
        *,
        active: bool = True,
        schedule_type: str | None = None,
        run_at: str | None = None,
        delete_after_run: bool = False,
        message: str | None = None,
        inventory_id: int | None = None,
        cli_args: str | None = None,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
    ) -> Schedule:
        """POST /api/project/{pid}/schedules.

        ``schedule_type``/``run_at`` select a one-shot run-at trigger;
        ``delete_after_run`` self-removes after firing; the ansible overrides
        ride in a nested ``task_params`` (Semaphore ``db.TaskParams``, ken
        #907). Unset fields are omitted, preserving the legacy body shape.
        """
        body: dict[str, Any] = {
            "template_id": template_id,
            "cron_format": cron_format,
            "name": name,
            "project_id": project_id,
            "active": active,
        }
        if schedule_type is not None:
            body["type"] = schedule_type
        if run_at is not None:
            body["run_at"] = run_at
        if delete_after_run:
            body["delete_after_run"] = True
        tp = _task_params(message, inventory_id, cli_args, limit, tags, skip_tags)
        if tp:
            body["task_params"] = tp

        data = self._request(f"project/{project_id}/schedules", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /schedules"
            raise SemaphoreAPIError(msg)
        return Schedule.model_validate(data)

    def update_schedule(  # noqa: PLR0913  # one parameter per payload field (API wrapper)
        self,
        project_id: int,
        sched_id: int,
        *,
        name: str | None = None,
        cron_format: str | None = None,
        active: bool | None = None,
        schedule_type: str | None = None,
        run_at: str | None = None,
        delete_after_run: bool | None = None,
        message: str | None = None,
        inventory_id: int | None = None,
        cli_args: str | None = None,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
    ) -> None:
        """PUT /api/project/{pid}/schedules/{sid}.

        Pass-through: only the fields you supply are sent. The new
        overrides ride in a nested ``task_params`` exactly as for create.
        """
        body: dict[str, Any] = {"id": sched_id, "project_id": project_id}
        if name is not None:
            body["name"] = name
        if cron_format is not None:
            body["cron_format"] = cron_format
        if active is not None:
            body["active"] = active
        if schedule_type is not None:
            body["type"] = schedule_type
        if run_at is not None:
            body["run_at"] = run_at
        if delete_after_run is not None:
            body["delete_after_run"] = delete_after_run
        tp = _task_params(message, inventory_id, cli_args, limit, tags, skip_tags)
        if tp:
            body["task_params"] = tp
        self._request(
            f"project/{project_id}/schedules/{sched_id}",
            method="PUT",
            body=body,
        )

    def delete_schedule(self, project_id: int, sched_id: int) -> None:
        """DELETE /api/project/{pid}/schedules/{sid}."""
        self._request(f"project/{project_id}/schedules/{sched_id}", method="DELETE")
