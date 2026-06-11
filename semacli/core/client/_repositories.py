"""Repository endpoints."""

from typing import Any

from ..exceptions import SemaphoreAPIError
from ..models import Repository
from ._base import BaseClient


class RepositoriesMixin(BaseClient):
    """CRUD on repositories."""

    def list_repositories(self, project_id: int) -> list[Repository]:
        """GET /api/project/{pid}/repositories."""
        data = self._request(f"project/{project_id}/repositories")
        if not isinstance(data, list):
            msg = "Unexpected response for /repositories"
            raise SemaphoreAPIError(msg)
        return [Repository.model_validate(r) for r in data]

    def get_repository(self, project_id: int, repo_id: int) -> Repository:
        """GET /api/project/{pid}/repositories/{rid}."""
        data = self._request(f"project/{project_id}/repositories/{repo_id}")
        if not isinstance(data, dict):
            msg = "Unexpected response for /repositories/{rid}"
            raise SemaphoreAPIError(msg)
        return Repository.model_validate(data)

    def create_repository(
        self,
        project_id: int,
        name: str,
        git_url: str,
        git_branch: str,
        ssh_key_id: int,
    ) -> Repository:
        """POST /api/project/{pid}/repositories."""
        body = {
            "name": name,
            "git_url": git_url,
            "git_branch": git_branch,
            "ssh_key_id": ssh_key_id,
            "project_id": project_id,
        }
        data = self._request(f"project/{project_id}/repositories", method="POST", body=body)
        if not isinstance(data, dict):
            msg = "Unexpected response for POST /repositories"
            raise SemaphoreAPIError(msg)
        return Repository.model_validate(data)

    def update_repository(
        self,
        project_id: int,
        repo_id: int,
        **fields: Any,
    ) -> None:
        """PUT /api/project/{pid}/repositories/{rid}."""
        body = {k: v for k, v in fields.items() if v is not None}
        body["id"] = repo_id
        body["project_id"] = project_id
        self._request(
            f"project/{project_id}/repositories/{repo_id}",
            method="PUT",
            body=body,
        )

    def delete_repository(self, project_id: int, repo_id: int) -> None:
        """DELETE /api/project/{pid}/repositories/{rid}."""
        self._request(f"project/{project_id}/repositories/{repo_id}", method="DELETE")
