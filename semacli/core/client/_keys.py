"""Access-key endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Key
from ._base import BaseClient

# Secret payload key -> access key ``type`` (Semaphore db.AccessKeyType).
_SECRET_TYPES = {"ssh": "ssh", "login_password": "login_password", "string": "string"}


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

    def create_key(  # noqa: PLR0913  # one parameter per payload field (API wrapper)
        self,
        project_id: int,
        *,
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

    def update_key(
        self,
        project_id: int,
        key_id: int,
        **fields: Any,  # noqa: ANN401  # JSON payload values
    ) -> None:
        """PUT /api/project/{pid}/keys/{kid} — read-modify-write (ken #1170).

        The server only rewrites the secret when ``override_secret`` is set,
        so a new ``ssh`` / ``login_password`` / ``string`` payload turns it
        on (and pins the matching ``type``). Otherwise the masked secret
        fields echoed by GET are ignored server-side.
        """
        secret = {k: fields[k] for k in _SECRET_TYPES if fields.get(k) is not None}
        if secret:
            fields |= {"override_secret": True, "type": _SECRET_TYPES[next(iter(secret))]}
        self._put_merged(
            f"project/{project_id}/keys/{key_id}",
            fields,
            {"id": key_id, "project_id": project_id},
            drop=frozenset({"empty"}),
        )

    def delete_key(self, project_id: int, key_id: int) -> None:
        """DELETE /api/project/{pid}/keys/{kid}."""
        self._request(f"project/{project_id}/keys/{key_id}", method="DELETE")
