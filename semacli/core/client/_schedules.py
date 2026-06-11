"""Schedule endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Schedule
from ._base import BaseClient


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

    def create_schedule(
        self,
        project_id: int,
        template_id: int,
        cron_format: str,
        name: str = "",
        *,
        active: bool = True,
    ) -> Schedule:
        """POST /api/project/{pid}/schedules."""
        body = {
            "template_id": template_id,
            "cron_format": cron_format,
            "name": name,
            "project_id": project_id,
            "active": active,
        }
        data = self._request(f"project/{project_id}/schedules", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /schedules"
            raise SemaphoreAPIError(msg)
        return Schedule.model_validate(data)

    def update_schedule(self, project_id: int, sched_id: int, **fields: Any) -> None:
        """PUT /api/project/{pid}/schedules/{sid}."""
        body = {k: v for k, v in fields.items() if v is not None}
        body["id"] = sched_id
        body["project_id"] = project_id
        self._request(
            f"project/{project_id}/schedules/{sched_id}",
            method="PUT",
            body=body,
        )

    def delete_schedule(self, project_id: int, sched_id: int) -> None:
        """DELETE /api/project/{pid}/schedules/{sid}."""
        self._request(f"project/{project_id}/schedules/{sched_id}", method="DELETE")
