"""Access-key endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Key
from ._base import BaseClient


class KeysMixin(BaseClient):
    """CRUD on access keys."""

    def list_keys(self, project_id: int) -> list[Key]:
        """GET /api/project/{pid}/keys."""
        data = self._request(f"project/{project_id}/keys")
        if not isinstance(data, list):
            msg = "Unexpected response for /keys"
            raise SemaphoreAPIError(msg)
        return [Key.model_validate(k) for k in data]

    def get_key(self, project_id: int, key_id: int) -> Key:
        """GET /api/project/{pid}/keys/{kid}."""
        data = self._request(f"project/{project_id}/keys/{key_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /keys/{kid}"
            raise SemaphoreAPIError(msg)
        return Key.model_validate(data)

    def create_key(
        self,
        project_id: int,
        name: str,
        type: str,
        login: str = "",
        password: str = "",
        passphrase: str = "",
        private_key: str = "",
    ) -> Key:
        """POST /api/project/{pid}/keys.

        type: 'ssh' | 'login_password' | 'none'
        """
        body: dict[str, Any] = {
            "name": name,
            "type": type,
            "project_id": project_id,
        }
        if type == "ssh":
            body["ssh"] = {
                "login": login,
                "passphrase": passphrase,
                "private_key": private_key,
            }
        elif type == "login_password":
            body["login_password"] = {"login": login, "password": password}
        elif type == "none" and password:
            # Semaphore stores secret-only keys (vault pw, become pw) in the
            # top-level `string` field.
            body["string"] = password
        data = self._request(f"project/{project_id}/keys", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /keys"
            raise SemaphoreAPIError(msg)
        return Key.model_validate(data)

    def update_key(self, project_id: int, key_id: int, **fields: Any) -> None:
        """PUT /api/project/{pid}/keys/{kid}."""
        body = {k: v for k, v in fields.items() if v is not None}
        body["id"] = key_id
        body["project_id"] = project_id
        self._request(f"project/{project_id}/keys/{key_id}", method="PUT", body=body)

    def delete_key(self, project_id: int, key_id: int) -> None:
        """DELETE /api/project/{pid}/keys/{kid}."""
        self._request(f"project/{project_id}/keys/{key_id}", method="DELETE")
