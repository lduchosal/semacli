"""Semaphore HTTP API client."""

import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import SemaphoreConfig
from .exceptions import AuthenticationError, NotFoundError, SemaphoreAPIError
from .models import (
    Environment,
    Inventory,
    Key,
    Project,
    Repository,
    Schedule,
    Task,
    Template,
)


def _build_insecure_ssl_context() -> ssl.SSLContext:
    """Return an SSL context with verification disabled.

    Opt-in path: only called when the user sets verify_ssl=false in their
    config. The two assignments below are deliberate — see SEC ken #638
    and sonar-project.properties for the scoped S4830 suppression.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class SemaphoreClient:
    """HTTP client for Semaphore UI REST API."""

    def __init__(self, config: SemaphoreConfig, verbose: int = 0) -> None:
        self.config = config
        self.verbose = verbose
        self._opener: urllib.request.OpenerDirector | None = None
        self._warn_insecure()

    def _warn_insecure(self) -> None:
        if not self.config.verify_ssl:
            print(
                "WARNING: TLS certificate verification is DISABLED "
                "(verify_ssl=false). Traffic is vulnerable to MITM.",
                file=sys.stderr,
            )
        if self.config.url.startswith("http://"):
            print(
                "WARNING: connecting over plain HTTP. Credentials and data "
                "travel in clear text.",
                file=sys.stderr,
            )

    def _get_opener(self) -> urllib.request.OpenerDirector:
        """Get or create HTTP opener with SSL handling."""
        if self._opener is None:
            handlers: list[urllib.request.BaseHandler] = []
            if not self.config.verify_ssl:
                handlers.append(
                    urllib.request.HTTPSHandler(context=_build_insecure_ssl_context())
                )
            self._opener = urllib.request.build_opener(*handlers)
        return self._opener

    def _build_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> urllib.request.Request:
        url = f"{self.config.url}/api/{endpoint.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        if self.verbose >= 2:
            print(f"DEBUG: {method} {url}")

        data: bytes | None = None
        request = urllib.request.Request(url, method=method)

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request.add_header("Content-Type", "application/json")
            request.data = data

        if require_auth:
            if not self.config.bearer_token:
                raise AuthenticationError("No bearer_token configured")
            request.add_header("Authorization", f"Bearer {self.config.bearer_token}")

        request.add_header("Accept", "application/json")
        return request

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> Any:
        """Make HTTP request to Semaphore API and return parsed JSON (or raw text)."""
        request = self._build_request(endpoint, method, params, body, require_auth)

        try:
            response = self._get_opener().open(request, timeout=self.config.timeout)
            content = response.read().decode("utf-8")

            if self.verbose >= 3:
                print(f"DEBUG: Response: {content[:500]}")

            if not content:
                return None
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content

        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise AuthenticationError(f"HTTP {e.code}: {e.reason}") from e
            if e.code == 404:
                raise NotFoundError(f"HTTP 404: {endpoint}") from e
            raise SemaphoreAPIError(f"HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise SemaphoreAPIError(f"Connection error: {e.reason}") from e

    def ping(self) -> str:
        """GET /api/ping — does not require authentication."""
        result = self._request("ping", require_auth=False)
        if isinstance(result, str):
            return result.strip()
        return str(result)

    def get_projects(self) -> list[Project]:
        """GET /api/projects — list all projects visible to the token."""
        data = self._request("projects")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response format for /projects")
        return [self._parse_project(item) for item in data]

    def get_templates(self, project_id: int) -> list[Template]:
        """GET /api/project/{pid}/templates."""
        data = self._request(f"project/{project_id}/templates")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /templates")
        return [self._parse_template(t) for t in data]

    def get_template(self, project_id: int, template_id: int) -> Template:
        """GET /api/project/{pid}/templates/{tid}."""
        data = self._request(f"project/{project_id}/templates/{template_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /templates/{tid}")
        return self._parse_template(data)

    def run_task(
        self,
        project_id: int,
        template_id: int,
        playbook: str | None = None,
        environment: str | None = None,
        limit: str | None = None,
        debug: bool = False,
        dry_run: bool = False,
    ) -> Task:
        """POST /api/project/{pid}/tasks — launch a task from a template."""
        body: dict[str, Any] = {"template_id": template_id}
        if playbook is not None:
            body["playbook"] = playbook
        if environment is not None:
            body["environment"] = environment
        if limit is not None:
            body["limit"] = limit
        if debug:
            body["debug"] = True
        if dry_run:
            body["dry_run"] = True

        data = self._request(
            f"project/{project_id}/tasks", method="POST", body=body
        )
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /tasks")
        return self._parse_task(data)

    def get_task(self, project_id: int, task_id: int) -> Task:
        """GET /api/project/{pid}/tasks/{tid}."""
        data = self._request(f"project/{project_id}/tasks/{task_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /tasks/{tid}")
        return self._parse_task(data)

    def get_task_output(
        self, project_id: int, task_id: int
    ) -> list[dict[str, Any]]:
        """GET /api/project/{pid}/tasks/{tid}/output — list of {time, output}."""
        data = self._request(f"project/{project_id}/tasks/{task_id}/output")
        if not isinstance(data, list):
            return []
        return data

    def get_task_raw_output(self, project_id: int, task_id: int) -> str:
        """GET /api/project/{pid}/tasks/{tid}/raw_output."""
        data = self._request(f"project/{project_id}/tasks/{task_id}/raw_output")
        if isinstance(data, str):
            return data
        return ""

    def list_tasks(self, project_id: int) -> list[Task]:
        """GET /api/project/{pid}/tasks — task history."""
        data = self._request(f"project/{project_id}/tasks")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /tasks")
        return [self._parse_task(t) for t in data]

    def stop_task(self, project_id: int, task_id: int) -> None:
        """POST /api/project/{pid}/tasks/{tid}/stop."""
        self._request(
            f"project/{project_id}/tasks/{task_id}/stop", method="POST", body={}
        )

    # ── inventories ──────────────────────────────────────────────────────
    def list_inventories(self, project_id: int) -> list[Inventory]:
        """GET /api/project/{pid}/inventory."""
        data = self._request(f"project/{project_id}/inventory")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /inventory")
        return [self._parse_inventory(i) for i in data]

    def get_inventory(self, project_id: int, inventory_id: int) -> Inventory:
        """GET /api/project/{pid}/inventory/{iid}."""
        data = self._request(f"project/{project_id}/inventory/{inventory_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /inventory/{iid}")
        return self._parse_inventory(data)

    def create_inventory(
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
        data = self._request(
            f"project/{project_id}/inventory", method="POST", body=body
        )
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /inventory")
        return self._parse_inventory(data)

    def update_inventory(
        self,
        project_id: int,
        inventory_id: int,
        **fields: Any,
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
        self._request(
            f"project/{project_id}/inventory/{inventory_id}", method="DELETE"
        )

    # ── environments ─────────────────────────────────────────────────────
    def list_environments(self, project_id: int) -> list[Environment]:
        """GET /api/project/{pid}/environment."""
        data = self._request(f"project/{project_id}/environment")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /environment")
        return [self._parse_environment(e) for e in data]

    def get_environment(self, project_id: int, env_id: int) -> Environment:
        """GET /api/project/{pid}/environment/{eid}."""
        data = self._request(f"project/{project_id}/environment/{env_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /environment/{eid}")
        return self._parse_environment(data)

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
        data = self._request(
            f"project/{project_id}/environment", method="POST", body=body
        )
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /environment")
        return self._parse_environment(data)

    def update_environment(
        self,
        project_id: int,
        env_id: int,
        **fields: Any,
    ) -> None:
        """PUT /api/project/{pid}/environment/{eid}."""
        body = {k: v for k, v in fields.items() if v is not None}
        body["id"] = env_id
        body["project_id"] = project_id
        self._request(
            f"project/{project_id}/environment/{env_id}",
            method="PUT",
            body=body,
        )

    def delete_environment(self, project_id: int, env_id: int) -> None:
        """DELETE /api/project/{pid}/environment/{eid}."""
        self._request(
            f"project/{project_id}/environment/{env_id}", method="DELETE"
        )

    # ── repositories ─────────────────────────────────────────────────────
    def list_repositories(self, project_id: int) -> list[Repository]:
        """GET /api/project/{pid}/repositories."""
        data = self._request(f"project/{project_id}/repositories")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /repositories")
        return [self._parse_repository(r) for r in data]

    def get_repository(self, project_id: int, repo_id: int) -> Repository:
        """GET /api/project/{pid}/repositories/{rid}."""
        data = self._request(f"project/{project_id}/repositories/{repo_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /repositories/{rid}")
        return self._parse_repository(data)

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
        data = self._request(
            f"project/{project_id}/repositories", method="POST", body=body
        )
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /repositories")
        return self._parse_repository(data)

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
        self._request(
            f"project/{project_id}/repositories/{repo_id}", method="DELETE"
        )

    # ── keys ─────────────────────────────────────────────────────────────
    def list_keys(self, project_id: int) -> list[Key]:
        """GET /api/project/{pid}/keys."""
        data = self._request(f"project/{project_id}/keys")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /keys")
        return [self._parse_key(k) for k in data]

    def get_key(self, project_id: int, key_id: int) -> Key:
        """GET /api/project/{pid}/keys/{kid}."""
        data = self._request(f"project/{project_id}/keys/{key_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /keys/{kid}")
        return self._parse_key(data)

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
        data = self._request(
            f"project/{project_id}/keys", method="POST", body=body
        )
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /keys")
        return self._parse_key(data)

    def update_key(
        self, project_id: int, key_id: int, **fields: Any
    ) -> None:
        """PUT /api/project/{pid}/keys/{kid}."""
        body = {k: v for k, v in fields.items() if v is not None}
        body["id"] = key_id
        body["project_id"] = project_id
        self._request(
            f"project/{project_id}/keys/{key_id}", method="PUT", body=body
        )

    def delete_key(self, project_id: int, key_id: int) -> None:
        """DELETE /api/project/{pid}/keys/{kid}."""
        self._request(
            f"project/{project_id}/keys/{key_id}", method="DELETE"
        )

    # ── schedules ────────────────────────────────────────────────────────
    def list_schedules(self, project_id: int) -> list[Schedule]:
        """GET /api/project/{pid}/schedules."""
        data = self._request(f"project/{project_id}/schedules")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /schedules")
        return [self._parse_schedule(s) for s in data]

    def get_schedule(self, project_id: int, sched_id: int) -> Schedule:
        """GET /api/project/{pid}/schedules/{sid}."""
        data = self._request(f"project/{project_id}/schedules/{sched_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /schedules/{sid}")
        return self._parse_schedule(data)

    def create_schedule(
        self,
        project_id: int,
        template_id: int,
        cron_format: str,
        name: str = "",
        active: bool = True,
    ) -> Schedule:
        """POST /api/project/{pid}/schedules."""
        body = {
            "template_id": template_id,
            "cron_format": cron_format,
            "name": name,
            "project_id": project_id,
            "active": active,
        }
        data = self._request(
            f"project/{project_id}/schedules", method="POST", body=body
        )
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /schedules")
        return self._parse_schedule(data)

    def update_schedule(
        self, project_id: int, sched_id: int, **fields: Any
    ) -> None:
        """PUT /api/project/{pid}/schedules/{sid}."""
        body = {k: v for k, v in fields.items() if v is not None}
        body["id"] = sched_id
        body["project_id"] = project_id
        self._request(
            f"project/{project_id}/schedules/{sched_id}",
            method="PUT",
            body=body,
        )

    def delete_schedule(self, project_id: int, sched_id: int) -> None:
        """DELETE /api/project/{pid}/schedules/{sid}."""
        self._request(
            f"project/{project_id}/schedules/{sched_id}", method="DELETE"
        )

    @staticmethod
    def _parse_project(data: dict[str, Any]) -> Project:
        return Project(
            id=int(data.get("id", 0)),
            name=str(data.get("name", "")),
            created=str(data.get("created", "")),
            alert=bool(data.get("alert", False)),
            alert_chat=str(data.get("alert_chat", "")),
            max_parallel_tasks=int(data.get("max_parallel_tasks", 0)),
        )

    @staticmethod
    def _parse_template(data: dict[str, Any]) -> Template:
        return Template(
            id=int(data.get("id", 0)),
            project_id=int(data.get("project_id", 0)),
            name=str(data.get("name", "")),
            playbook=str(data.get("playbook", "")),
            inventory_id=int(data.get("inventory_id", 0)),
            repository_id=int(data.get("repository_id", 0)),
            environment_id=int(data.get("environment_id", 0)),
            description=str(data.get("description", "")),
        )

    @staticmethod
    def _parse_task(data: dict[str, Any]) -> Task:
        return Task(
            id=int(data.get("id", 0)),
            template_id=int(data.get("template_id", 0)),
            status=str(data.get("status", "")),
            debug=bool(data.get("debug", False)),
            dry_run=bool(data.get("dry_run", False)),
            playbook=str(data.get("playbook", "")),
            environment=str(data.get("environment", "")),
            created=str(data.get("created", "")),
            start=str(data.get("start", "")),
            end=str(data.get("end", "")),
        )

    @staticmethod
    def _parse_inventory(data: dict[str, Any]) -> Inventory:
        return Inventory(
            id=int(data.get("id", 0)),
            project_id=int(data.get("project_id", 0)),
            name=str(data.get("name", "")),
            type=str(data.get("type", "")),
            content=str(data.get("inventory", "")),
            ssh_key_id=int(data.get("ssh_key_id", 0)),
            become_key_id=int(data.get("become_key_id", 0)),
        )

    @staticmethod
    def _parse_environment(data: dict[str, Any]) -> Environment:
        return Environment(
            id=int(data.get("id", 0)),
            project_id=int(data.get("project_id", 0)),
            name=str(data.get("name", "")),
            password=str(data.get("password", "")),
            json=str(data.get("json", "")),
        )

    @staticmethod
    def _parse_repository(data: dict[str, Any]) -> Repository:
        return Repository(
            id=int(data.get("id", 0)),
            project_id=int(data.get("project_id", 0)),
            name=str(data.get("name", "")),
            git_url=str(data.get("git_url", "")),
            git_branch=str(data.get("git_branch", "")),
            ssh_key_id=int(data.get("ssh_key_id", 0)),
        )

    @staticmethod
    def _parse_key(data: dict[str, Any]) -> Key:
        return Key(
            id=int(data.get("id", 0)),
            project_id=int(data.get("project_id", 0)),
            name=str(data.get("name", "")),
            type=str(data.get("type", "")),
        )

    @staticmethod
    def _parse_schedule(data: dict[str, Any]) -> Schedule:
        return Schedule(
            id=int(data.get("id", 0)),
            project_id=int(data.get("project_id", 0)),
            template_id=int(data.get("template_id", 0)),
            cron_format=str(data.get("cron_format", "")),
            name=str(data.get("name", "")),
            active=bool(data.get("active", True)),
        )
