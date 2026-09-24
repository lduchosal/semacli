"""Template endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Template
from ..overrides import permissive_task_params
from ._base import BaseClient

# Server-computed fields echoed by GET that must never be PUT back.
_READ_ONLY_FIELDS = frozenset({"tasks", "last_task", "permissions"})


def _sync_environment_ids(body: dict[str, Any], environment_id: int) -> None:
    """Keep the multi-env list in step with the single ``environment_id``.

    Recent Semaphore returns both ``environment_id`` and
    ``environment_ids``; patching only the first would leave the PUT
    carrying the previous environment in the list.
    """
    if "environment_ids" in body:
        body["environment_ids"] = [environment_id]


class TemplatesMixin(BaseClient):
    """CRUD on task templates."""

    def get_templates(self, project_id: int) -> list[Template]:
        """GET /api/project/{pid}/templates."""
        data = self._request(f"project/{project_id}/templates")
        if not isinstance(data, list):
            msg = "Unexpected response for /templates"
            raise SemaphoreAPIError(msg)
        return [Template.model_validate(t) for t in data]

    def get_templates_raw(self, project_id: int) -> list[dict[str, Any]]:
        """GET the template list as raw server payloads.

        `template sync` diffs against what the server actually stores,
        including the fields the pydantic model does not declare.
        """
        data = self._request(f"project/{project_id}/templates")
        if not isinstance(data, list):
            msg = "Unexpected response for /templates"
            raise SemaphoreAPIError(msg)
        return data

    def get_template(self, project_id: int, template_id: int) -> Template:
        """GET /api/project/{pid}/templates/{tid}."""
        return Template.model_validate(self.get_template_raw(project_id, template_id))

    def get_template_raw(self, project_id: int, template_id: int) -> dict[str, Any]:
        """GET one template as the raw server payload.

        The pydantic model is ``extra="ignore"``: round-tripping a
        template through it would drop every field semacli does not
        declare. Read-modify-write updates and `template sync` diffs
        work on this untouched dict instead.
        """
        data = self._request(f"project/{project_id}/templates/{template_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /templates/{tid}"
            raise SemaphoreAPIError(msg)
        return data

    def create_template(  # noqa: PLR0913, PLR0917  # one parameter per payload field (API wrapper)
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
        *,
        view_id: int | None = None,
        task_params: dict[str, bool] | None = None,
        allow_override_args: bool = True,
        survey_vars: list[dict[str, Any]] | None = None,
    ) -> Template:
        """POST /api/project/{pid}/templates.

        ``app`` is mandatory server-side (HTTP 400 ``Invalid app id``,
        ken #812), and ``task_params`` defaults to permissive: without
        it every toggle is false and the server then SILENTLY DROPS
        per-run --limit/--tags/--debug (ken #826).
        """
        body: dict[str, Any] = {
            "project_id": project_id,
            "name": name,
            "playbook": playbook,
            "inventory_id": inventory_id,
            "repository_id": repository_id,
            "app": app,
            "allow_override_args_in_task": allow_override_args,
            "task_params": task_params if task_params is not None else permissive_task_params(),
        }
        optional = {
            "environment_id": environment_id,
            "description": description or None,
            "arguments": arguments or None,
            "view_id": view_id,
            "survey_vars": survey_vars,
        }
        body.update({k: v for k, v in optional.items() if v is not None})
        data = self._request(f"project/{project_id}/templates", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /templates"
            raise SemaphoreAPIError(msg)
        return Template.model_validate(data)

    def update_template(
        self,
        project_id: int,
        template_id: int,
        **fields: Any,  # noqa: ANN401  # JSON payload values
    ) -> dict[str, Any]:
        """PUT /api/project/{pid}/templates/{tid} — read-modify-write.

        Semaphore's PUT replaces the whole row: a partial body drops
        ``app`` (HTTP 400 ``Invalid app id``) and silently wipes
        ``task_params`` / ``view_id`` / ``survey_vars`` — turning an
        innocent rename into a template that ignores --limit. So the
        current payload is fetched first and only the fields passed here
        are patched onto it; ``task_params`` is merged key by key.
        Returns the body that was sent.
        """
        body = {
            k: v
            for k, v in self.get_template_raw(project_id, template_id).items()
            if k not in _READ_ONLY_FIELDS
        }
        patch = {k: v for k, v in fields.items() if v is not None}
        task_params = patch.pop("task_params", None)
        if task_params:
            current = body.get("task_params") or {}
            body["task_params"] = {**current, **task_params}
        body.update(patch)
        if "environment_id" in patch:
            _sync_environment_ids(body, patch["environment_id"])
        body["id"] = template_id
        body["project_id"] = project_id
        self._request(f"project/{project_id}/templates/{template_id}", method="PUT", body=body)
        return body

    def delete_template(self, project_id: int, template_id: int) -> None:
        """DELETE /api/project/{pid}/templates/{tid}."""
        self._request(f"project/{project_id}/templates/{template_id}", method="DELETE")
