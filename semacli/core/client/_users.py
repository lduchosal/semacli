"""User endpoints: self, tokens, admin users, server info."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import ApiInfo, User, UserToken
from ._base import BaseClient


class UsersMixin(BaseClient):
    """Current user, API tokens, admin user management and server info."""

    def whoami(self) -> User:
        """GET /api/user."""
        data = self._request("user")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /user")
        return User.model_validate(data)

    def list_user_tokens(self) -> list[UserToken]:
        """GET /api/user/tokens."""
        data = self._request("user/tokens")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /user/tokens")
        return [UserToken.model_validate(item) for item in data]

    def create_user_token(self) -> UserToken:
        """POST /api/user/tokens — returns the freshly minted token id.

        The response is the only chance to read the secret; subsequent
        ``list_user_tokens`` calls expose only the metadata.
        """
        data = self._request("user/tokens", method="POST", body={})
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /user/tokens")
        return UserToken.model_validate(data)

    def delete_user_token(self, token_id: str) -> None:
        """DELETE /api/user/tokens/{tid}."""
        self._request(f"user/tokens/{token_id}", method="DELETE")

    def get_info(self) -> ApiInfo:
        """GET /api/info — server metadata (no auth required)."""
        data = self._request("info", require_auth=False)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /info")
        return ApiInfo.model_validate(data)

    def list_users(self) -> list[User]:
        """GET /api/users — admin only."""
        data = self._request("users")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /users")
        return [User.model_validate(item) for item in data]

    def get_user(self, user_id: int) -> User:
        """GET /api/users/{uid} — admin only."""
        data = self._request(f"users/{user_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /users/{uid}")
        return User.model_validate(data)

    def create_user(
        self,
        username: str,
        name: str,
        email: str,
        password: str,
        *,
        admin: bool = False,
    ) -> User:
        """POST /api/users — admin only."""
        body: dict[str, Any] = {
            "username": username,
            "name": name,
            "email": email,
            "password": password,
            "admin": admin,
        }
        data = self._request("users", method="POST", body=body)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /users")
        return User.model_validate(data)

    def update_user(self, user_id: int, **fields: Any) -> None:
        """PUT /api/users/{uid} — admin only."""
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body["id"] = user_id
        self._request(f"users/{user_id}", method="PUT", body=body)

    def delete_user(self, user_id: int) -> None:
        """DELETE /api/users/{uid} — admin only."""
        self._request(f"users/{user_id}", method="DELETE")

    def set_user_password(self, user_id: int, password: str) -> None:
        """POST /api/users/{uid}/password — admin only."""
        self._request(
            f"users/{user_id}/password",
            method="POST",
            body={"password": password},
        )
