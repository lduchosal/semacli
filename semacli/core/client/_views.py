"""View endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import View
from ._base import BaseClient


class ViewsMixin(BaseClient):
    """CRUD on board views."""

    def list_views(self, project_id: int) -> list[View]:
        """GET /api/project/{pid}/views."""
        data = self._request(f"project/{project_id}/views")
        if not isinstance(data, list):
            msg = "Unexpected response for /project/{pid}/views"
            raise SemaphoreAPIError(msg)
        return [View.model_validate(v) for v in data]

    def get_view(self, project_id: int, view_id: int) -> View:
        """GET /api/project/{pid}/views/{vid}."""
        data = self._request(f"project/{project_id}/views/{view_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /project/{pid}/views/{vid}"
            raise SemaphoreAPIError(msg)
        return View.model_validate(data)

    def create_view(self, project_id: int, title: str, position: int = 0) -> View:
        """POST /api/project/{pid}/views."""
        body: dict[str, Any] = {
            "project_id": project_id,
            "title": title,
            "position": position,
        }
        data = self._request(f"project/{project_id}/views", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /views"
            raise SemaphoreAPIError(msg)
        return View.model_validate(data)

    def update_view(self, project_id: int, view_id: int, **fields: str | int | bool | None) -> None:
        """PUT /api/project/{pid}/views/{vid}."""
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body["id"] = view_id
        body["project_id"] = project_id
        self._request(f"project/{project_id}/views/{view_id}", method="PUT", body=body)

    def delete_view(self, project_id: int, view_id: int) -> None:
        """DELETE /api/project/{pid}/views/{vid}."""
        self._request(f"project/{project_id}/views/{view_id}", method="DELETE")
