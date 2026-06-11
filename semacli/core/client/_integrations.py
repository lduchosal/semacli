"""Integration and integration-matcher endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Integration, IntegrationMatcher
from ._base import BaseClient


class IntegrationsMixin(BaseClient):
    """CRUD on integrations and their matchers."""

    def list_integrations(self, project_id: int) -> list[Integration]:
        """GET /api/project/{pid}/integrations."""
        data = self._request(f"project/{project_id}/integrations")
        if not isinstance(data, list):
            msg = "Unexpected response for /project/{pid}/integrations"
            raise SemaphoreAPIError(msg)
        return [Integration.model_validate(i) for i in data]

    def get_integration(self, project_id: int, integration_id: int) -> Integration:
        """GET /api/project/{pid}/integrations/{iid}."""
        data = self._request(f"project/{project_id}/integrations/{integration_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /integrations/{iid}"
            raise SemaphoreAPIError(msg)
        return Integration.model_validate(data)

    def create_integration(
        self,
        project_id: int,
        name: str,
        template_id: int,
        auth_method: str = "none",
        auth_header: str = "",
        auth_secret_id: int = 0,
    ) -> Integration:
        """POST /api/project/{pid}/integrations."""
        body: dict[str, Any] = {
            "project_id": project_id,
            "name": name,
            "template_id": template_id,
            "auth_method": auth_method,
        }
        if auth_header:
            body["auth_header"] = auth_header
        if auth_secret_id:
            body["auth_secret_id"] = auth_secret_id
        data = self._request(f"project/{project_id}/integrations", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /integrations"
            raise SemaphoreAPIError(msg)
        return Integration.model_validate(data)

    def update_integration(self, project_id: int, integration_id: int, **fields: Any) -> None:
        """PUT /api/project/{pid}/integrations/{iid}."""
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body["id"] = integration_id
        body["project_id"] = project_id
        self._request(
            f"project/{project_id}/integrations/{integration_id}",
            method="PUT",
            body=body,
        )

    def delete_integration(self, project_id: int, integration_id: int) -> None:
        """DELETE /api/project/{pid}/integrations/{iid}."""
        self._request(f"project/{project_id}/integrations/{integration_id}", method="DELETE")

    def list_integration_matchers(
        self, project_id: int, integration_id: int
    ) -> list[IntegrationMatcher]:
        """GET /api/project/{pid}/integrations/{iid}/matchers."""
        data = self._request(f"project/{project_id}/integrations/{integration_id}/matchers")
        if not isinstance(data, list):
            msg = "Unexpected response for /matchers"
            raise SemaphoreAPIError(msg)
        return [IntegrationMatcher.model_validate(m) for m in data]

    def add_integration_matcher(
        self,
        project_id: int,
        integration_id: int,
        name: str,
        match_type: str,
        method: str,
        key: str,
        value: str,
    ) -> IntegrationMatcher:
        """POST /api/project/{pid}/integrations/{iid}/matchers."""
        body: dict[str, Any] = {
            "integration_id": integration_id,
            "name": name,
            "match_type": match_type,
            "method": method,
            "key": key,
            "value": value,
        }
        data = self._request(
            f"project/{project_id}/integrations/{integration_id}/matchers",
            method="POST",
            body=body,
        )
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /matchers"
            raise SemaphoreAPIError(msg)
        return IntegrationMatcher.model_validate(data)

    def update_integration_matcher(
        self,
        project_id: int,
        integration_id: int,
        matcher_id: int,
        **fields: Any,
    ) -> None:
        """PUT /api/project/{pid}/integrations/{iid}/matchers/{mid}."""
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body["id"] = matcher_id
        body["integration_id"] = integration_id
        self._request(
            f"project/{project_id}/integrations/{integration_id}/matchers/{matcher_id}",
            method="PUT",
            body=body,
        )

    def remove_integration_matcher(
        self, project_id: int, integration_id: int, matcher_id: int
    ) -> None:
        """DELETE /api/project/{pid}/integrations/{iid}/matchers/{mid}."""
        self._request(
            f"project/{project_id}/integrations/{integration_id}/matchers/{matcher_id}",
            method="DELETE",
        )
