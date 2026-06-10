"""Projects, members, events and backup endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Project, ProjectEvent, ProjectMember
from ._base import BaseClient


class ProjectsMixin(BaseClient):
    """CRUD on projects plus member, event and backup sub-resources."""

    def get_projects(self) -> list[Project]:
        """GET /api/projects — list all projects visible to the token."""
        data = self._request("projects")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response format for /projects")
        return [Project.model_validate(item) for item in data]

    def get_project(self, project_id: int) -> Project:
        """GET /api/project/{pid}."""
        data = self._request(f"project/{project_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /project/{pid}")
        return Project.model_validate(data)

    def create_project(
        self,
        name: str,
        alert: bool = False,
        alert_chat: str = "",
        max_parallel_tasks: int = 0,
    ) -> Project:
        """POST /api/projects."""
        body: dict[str, Any] = {"name": name, "alert": alert}
        if alert_chat:
            body["alert_chat"] = alert_chat
        if max_parallel_tasks:
            body["max_parallel_tasks"] = max_parallel_tasks
        data = self._request("projects", method="POST", body=body)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /projects")
        return Project.model_validate(data)

    def update_project(self, project_id: int, **fields: Any) -> None:
        """PUT /api/project/{pid}."""
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body["id"] = project_id
        self._request(f"project/{project_id}", method="PUT", body=body)

    def delete_project(self, project_id: int) -> None:
        """DELETE /api/project/{pid}."""
        self._request(f"project/{project_id}", method="DELETE")

    def list_project_members(self, project_id: int) -> list[ProjectMember]:
        """GET /api/project/{pid}/users."""
        data = self._request(f"project/{project_id}/users")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /project/{pid}/users")
        return [ProjectMember.model_validate(item) for item in data]

    def add_project_member(self, project_id: int, user_id: int, role: str) -> None:
        """POST /api/project/{pid}/users."""
        body: dict[str, Any] = {
            "user_id": user_id,
            "role": role,
            "project_id": project_id,
        }
        self._request(f"project/{project_id}/users", method="POST", body=body)

    def update_project_member(self, project_id: int, user_id: int, role: str) -> None:
        """PUT /api/project/{pid}/users/{uid}."""
        body: dict[str, Any] = {
            "user_id": user_id,
            "role": role,
            "project_id": project_id,
        }
        self._request(f"project/{project_id}/users/{user_id}", method="PUT", body=body)

    def remove_project_member(self, project_id: int, user_id: int) -> None:
        """DELETE /api/project/{pid}/users/{uid}."""
        self._request(f"project/{project_id}/users/{user_id}", method="DELETE")

    def list_project_events(self, project_id: int) -> list[ProjectEvent]:
        """GET /api/project/{pid}/events."""
        data = self._request(f"project/{project_id}/events")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /events")
        return [ProjectEvent.model_validate(e) for e in data]

    def export_project_backup(self, project_id: int) -> dict[str, Any]:
        """GET /api/project/{pid}/backup — returns the full project as JSON."""
        data = self._request(f"project/{project_id}/backup")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /backup")
        return data
