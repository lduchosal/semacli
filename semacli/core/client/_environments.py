"""Environment endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Environment
from ._base import BaseClient


class EnvironmentsMixin(BaseClient):
    """CRUD on environments."""

    def list_environments(self, project_id: int) -> list[Environment]:
        """GET /api/project/{pid}/environment."""
        data = self._request(f"project/{project_id}/environment")
        if not isinstance(data, list):
            msg = "Unexpected response for /environment"
            raise SemaphoreAPIError(msg)
        return [Environment.model_validate(e) for e in data]

    def get_environment(self, project_id: int, env_id: int) -> Environment:
        """GET /api/project/{pid}/environment/{eid}."""
        data = self._request(f"project/{project_id}/environment/{env_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /environment/{eid}"
            raise SemaphoreAPIError(msg)
        return Environment.model_validate(data)

    def create_environment(
        self,
        project_id: int,
        name: str,
        json_vars: str = "{}",
        password: str = "",
    ) -> Environment:
        """POST /api/project/{pid}/environment."""
        body: dict[str, Any] = {
            "name": name,
            "json": json_vars,
            "project_id": project_id,
        }
        if password:
            body["password"] = password
        data = self._request(f"project/{project_id}/environment", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /environment"
            raise SemaphoreAPIError(msg)
        return Environment.model_validate(data)

    def update_environment(
        self,
        project_id: int,
        env_id: int,
        **fields: str | int | bool | None,
    ) -> None:
        """PUT /api/project/{pid}/environment/{eid} — read-modify-write (ken #1170).

        ``secrets`` is dropped: on PUT it is a list of create/update/delete
        operations, so echoing the GET list back would be replayed as ops.
        """
        self._put_merged(
            f"project/{project_id}/environment/{env_id}",
            fields,
            {"id": env_id, "project_id": project_id},
            drop=frozenset({"secrets"}),
        )

    def delete_environment(self, project_id: int, env_id: int) -> None:
        """DELETE /api/project/{pid}/environment/{eid}."""
        self._request(f"project/{project_id}/environment/{env_id}", method="DELETE")
