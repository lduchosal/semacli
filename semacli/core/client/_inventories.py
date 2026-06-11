"""Inventory endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Inventory
from ._base import BaseClient


class InventoriesMixin(BaseClient):
    """CRUD on inventories."""

    def list_inventories(self, project_id: int) -> list[Inventory]:
        """GET /api/project/{pid}/inventory."""
        data = self._request(f"project/{project_id}/inventory")
        if not isinstance(data, list):
            msg = "Unexpected response for /inventory"
            raise SemaphoreAPIError(msg)
        return [Inventory.model_validate(i) for i in data]

    def get_inventory(self, project_id: int, inventory_id: int) -> Inventory:
        """GET /api/project/{pid}/inventory/{iid}."""
        data = self._request(f"project/{project_id}/inventory/{inventory_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /inventory/{iid}"
            raise SemaphoreAPIError(msg)
        return Inventory.model_validate(data)

    def create_inventory(  # noqa: PLR0913  # one parameter per payload field (API wrapper)
        self,
        project_id: int,
        name: str,
        type: str,
        content: str = "",
        ssh_key_id: int = 0,
        become_key_id: int = 0,
    ) -> Inventory:
        """POST /api/project/{pid}/inventory."""
        body: dict[str, Any] = {
            "name": name,
            "type": type,
            "inventory": content,
            "project_id": project_id,
        }
        if ssh_key_id:
            body["ssh_key_id"] = ssh_key_id
        if become_key_id:
            body["become_key_id"] = become_key_id
        data = self._request(f"project/{project_id}/inventory", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /inventory"
            raise SemaphoreAPIError(msg)
        return Inventory.model_validate(data)

    def update_inventory(
        self,
        project_id: int,
        inventory_id: int,
        **fields: str | int | bool | None,
    ) -> None:
        """PUT /api/project/{pid}/inventory/{iid}."""
        body = {k: v for k, v in fields.items() if v is not None}
        body["id"] = inventory_id
        body["project_id"] = project_id
        self._request(
            f"project/{project_id}/inventory/{inventory_id}",
            method="PUT",
            body=body,
        )

    def delete_inventory(self, project_id: int, inventory_id: int) -> None:
        """DELETE /api/project/{pid}/inventory/{iid}."""
        self._request(f"project/{project_id}/inventory/{inventory_id}", method="DELETE")
