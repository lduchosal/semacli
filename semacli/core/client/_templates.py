"""Template endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Template
from ._base import BaseClient


class TemplatesMixin(BaseClient):
    """CRUD on task templates."""

    def get_templates(self, project_id: int) -> list[Template]:
        """GET /api/project/{pid}/templates."""
        data = self._request(f"project/{project_id}/templates")
        if not isinstance(data, list):
            msg = "Unexpected response for /templates"
            raise SemaphoreAPIError(msg)
        return [Template.model_validate(t) for t in data]

    def get_template(self, project_id: int, template_id: int) -> Template:
        """GET /api/project/{pid}/templates/{tid}."""
        data = self._request(f"project/{project_id}/templates/{template_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /templates/{tid}"
            raise SemaphoreAPIError(msg)
        return Template.model_validate(data)

    def create_template(
        self,
        project_id: int,
        name: str,
        playbook: str,
        inventory_id: int,
        repository_id: int,
        environment_id: int | None = None,
        description: str = "",
        arguments: str = "",
        app: str = "ansible",
    ) -> Template:
        """POST /api/project/{pid}/templates.

        Modern Semaphore requires the ``app`` field (the runner kind:
        ansible, terraform, bash, …) and rejects an absent/empty value
        with ``HTTP 400 Invalid app id`` (ken #812).

        ``task_params`` is sent permissive (all overrides allowed), like
        the UI does. Without it the server defaults every toggle to
        false and then SILENTLY DROPS per-run --limit/--tags/--debug —
        running the playbook on the full inventory (ken #826).
        """
        body: dict[str, Any] = {
            "project_id": project_id,
            "name": name,
            "playbook": playbook,
            "inventory_id": inventory_id,
            "repository_id": repository_id,
            "app": app,
            "allow_override_args_in_task": True,
            "task_params": {
                "allow_debug": True,
                "allow_override_inventory": True,
                "allow_override_limit": True,
                "allow_override_skip_tags": True,
                "allow_override_tags": True,
            },
        }
        if environment_id is not None:
            body["environment_id"] = environment_id
        if description:
            body["description"] = description
        if arguments:
            body["arguments"] = arguments
        data = self._request(f"project/{project_id}/templates", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /templates"
            raise SemaphoreAPIError(msg)
        return Template.model_validate(data)

    def update_template(self, project_id: int, template_id: int, **fields: Any) -> None:
        """PUT /api/project/{pid}/templates/{tid}."""
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body["id"] = template_id
        body["project_id"] = project_id
        self._request(f"project/{project_id}/templates/{template_id}", method="PUT", body=body)

    def delete_template(self, project_id: int, template_id: int) -> None:
        """DELETE /api/project/{pid}/templates/{tid}."""
        self._request(f"project/{project_id}/templates/{template_id}", method="DELETE")
