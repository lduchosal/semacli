"""Semaphore HTTP API client."""

import json
import sys
from typing import Any

import requests
import truststore
import urllib3

from .config import SemaphoreConfig
from .exceptions import AuthenticationError, NotFoundError, SemaphoreAPIError
from .models import (
    ApiInfo,
    Environment,
    Integration,
    IntegrationMatcher,
    Inventory,
    Key,
    Project,
    ProjectEvent,
    ProjectMember,
    Repository,
    Schedule,
    Task,
    Template,
    User,
    UserToken,
    View,
)

_truststore_injected = False


def _inject_truststore_once() -> None:
    """Patch ssl.SSLContext to use the OS trust store, once per process.

    `truststore.inject_into_ssl` is idempotent in spirit but cheap to
    short-circuit, and the module-level guard makes intent obvious in
    tests (we can assert it was called exactly once across N clients).
    """
    global _truststore_injected
    if _truststore_injected:
        return
    truststore.inject_into_ssl()
    _truststore_injected = True


class SemaphoreClient:
    """HTTP client for Semaphore UI REST API.

    Transport: a single ``requests.Session`` per client instance. SSL is
    secure-by-default (``session.verify = True`` → certifi bundle that
    `requests` ships). Opt-in insecure mode flips ``verify`` off and
    silences the urllib3 ``InsecureRequestWarning`` once at session
    init (our own stderr warning, emitted by ``_warn_insecure``,
    replaces it).
    """

    def __init__(self, config: SemaphoreConfig, verbose: int = 0) -> None:
        self.config = config
        self.verbose = verbose
        self._session: requests.Session | None = None
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
                "WARNING: connecting over plain HTTP. Credentials and data travel in clear text.",
                file=sys.stderr,
            )

    def _get_session(self) -> requests.Session:
        """Get or create the underlying ``requests.Session``."""
        if self._session is None:
            if self.config.verify_ssl and self.config.use_system_ca:
                _inject_truststore_once()
            s = requests.Session()
            s.verify = bool(self.config.verify_ssl)
            if not self.config.verify_ssl:
                # The user already saw our own stderr warning at init —
                # suppress the per-request urllib3 follow-on noise.
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            self._session = s
        return self._session

    def _build_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> dict[str, Any]:
        """Return the kwargs ready to be passed to ``session.request(**kwargs)``.

        Exposed for tests that want to inspect URL/headers/body without
        a network call.
        """
        url = f"{self.config.url}/api/{endpoint.lstrip('/')}"
        headers: dict[str, str] = {"Accept": "application/json"}

        if require_auth:
            if not self.config.bearer_token:
                raise AuthenticationError("No bearer_token configured")
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"

        kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": self.config.timeout,
        }
        if params:
            kwargs["params"] = params
        if body is not None:
            kwargs["json"] = body

        if self.verbose >= 2:
            print(f"DEBUG: {method} {url}")
        return kwargs

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> Any:
        """Make HTTP request to Semaphore API and return parsed JSON (or raw text)."""
        kwargs = self._build_request(endpoint, method, params, body, require_auth)

        try:
            response = self._get_session().request(**kwargs)
        except requests.exceptions.RequestException as e:
            raise SemaphoreAPIError(f"Connection error: {e}") from e

        text = response.text
        status = response.status_code

        if self.verbose >= 3:
            print(f"DEBUG: Response: {text[:500]}")

        if 400 <= status < 600:
            reason = response.reason or ""
            # Include the server body in the message so the user sees the
            # actual reason Semaphore complained (truncated to keep the
            # exception printable).
            detail = text.strip()[:500]
            suffix = f" — {detail}" if detail else ""
            if status in (401, 403):
                raise AuthenticationError(f"HTTP {status}: {reason}{suffix}")
            if status == 404:
                raise NotFoundError(f"HTTP 404: {endpoint}{suffix}")
            raise SemaphoreAPIError(f"HTTP {status}: {reason}{suffix}")

        if not response.content:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

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
        return [Project.model_validate(item) for item in data]

    def get_templates(self, project_id: int) -> list[Template]:
        """GET /api/project/{pid}/templates."""
        data = self._request(f"project/{project_id}/templates")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /templates")
        return [Template.model_validate(t) for t in data]

    def get_template(self, project_id: int, template_id: int) -> Template:
        """GET /api/project/{pid}/templates/{tid}."""
        data = self._request(f"project/{project_id}/templates/{template_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /templates/{tid}")
        return Template.model_validate(data)

    def run_task(
        self,
        project_id: int,
        template_id: int,
        playbook: str | None = None,
        environment: str | None = None,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
        debug: int = 0,
        dry_run: bool = False,
        diff: bool = False,
    ) -> Task:
        """POST /api/project/{pid}/tasks — launch a task from a template.

        ``debug`` is an ansible verbosity level (0=off, 1=-v ... 4=-vvvv).
        The current Semaphore body field is a plain boolean; the level→API
        mapping will be revisited once VCR cassettes show what the server
        accepts (ken #739 Phase 2).
        """
        body: dict[str, Any] = {"template_id": template_id}
        if playbook is not None:
            body["playbook"] = playbook
        if environment is not None:
            body["environment"] = environment
        if limit is not None:
            body["limit"] = limit
        if tags is not None:
            body["tags"] = tags
        if skip_tags is not None:
            body["skip_tags"] = skip_tags
        if debug:
            body["debug"] = True
        if dry_run:
            body["dry_run"] = True
        if diff:
            body["diff"] = True

        data = self._request(f"project/{project_id}/tasks", method="POST", body=body)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /tasks")
        return Task.model_validate(data)

    def get_task(self, project_id: int, task_id: int) -> Task:
        """GET /api/project/{pid}/tasks/{tid}."""
        data = self._request(f"project/{project_id}/tasks/{task_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /tasks/{tid}")
        return Task.model_validate(data)

    def get_task_output(self, project_id: int, task_id: int) -> list[dict[str, Any]]:
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
        return [Task.model_validate(t) for t in data]

    def stop_task(self, project_id: int, task_id: int) -> None:
        """POST /api/project/{pid}/tasks/{tid}/stop."""
        self._request(f"project/{project_id}/tasks/{task_id}/stop", method="POST", body={})

    # ── inventories ──────────────────────────────────────────────────────
    def list_inventories(self, project_id: int) -> list[Inventory]:
        """GET /api/project/{pid}/inventory."""
        data = self._request(f"project/{project_id}/inventory")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /inventory")
        return [Inventory.model_validate(i) for i in data]

    def get_inventory(self, project_id: int, inventory_id: int) -> Inventory:
        """GET /api/project/{pid}/inventory/{iid}."""
        data = self._request(f"project/{project_id}/inventory/{inventory_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /inventory/{iid}")
        return Inventory.model_validate(data)

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
        data = self._request(f"project/{project_id}/inventory", method="POST", body=body)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /inventory")
        return Inventory.model_validate(data)

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
        self._request(f"project/{project_id}/inventory/{inventory_id}", method="DELETE")

    # ── environments ─────────────────────────────────────────────────────
    def list_environments(self, project_id: int) -> list[Environment]:
        """GET /api/project/{pid}/environment."""
        data = self._request(f"project/{project_id}/environment")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /environment")
        return [Environment.model_validate(e) for e in data]

    def get_environment(self, project_id: int, env_id: int) -> Environment:
        """GET /api/project/{pid}/environment/{eid}."""
        data = self._request(f"project/{project_id}/environment/{env_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /environment/{eid}")
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
            raise SemaphoreAPIError("Unexpected response for POST /environment")
        return Environment.model_validate(data)

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
        self._request(f"project/{project_id}/environment/{env_id}", method="DELETE")

    # ── repositories ─────────────────────────────────────────────────────
    def list_repositories(self, project_id: int) -> list[Repository]:
        """GET /api/project/{pid}/repositories."""
        data = self._request(f"project/{project_id}/repositories")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /repositories")
        return [Repository.model_validate(r) for r in data]

    def get_repository(self, project_id: int, repo_id: int) -> Repository:
        """GET /api/project/{pid}/repositories/{rid}."""
        data = self._request(f"project/{project_id}/repositories/{repo_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /repositories/{rid}")
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
            raise SemaphoreAPIError("Unexpected response for POST /repositories")
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

    # ── keys ─────────────────────────────────────────────────────────────
    def list_keys(self, project_id: int) -> list[Key]:
        """GET /api/project/{pid}/keys."""
        data = self._request(f"project/{project_id}/keys")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /keys")
        return [Key.model_validate(k) for k in data]

    def get_key(self, project_id: int, key_id: int) -> Key:
        """GET /api/project/{pid}/keys/{kid}."""
        data = self._request(f"project/{project_id}/keys/{key_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /keys/{kid}")
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
            raise SemaphoreAPIError("Unexpected response for POST /keys")
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

    # ── schedules ────────────────────────────────────────────────────────
    def list_schedules(self, project_id: int) -> list[Schedule]:
        """GET /api/project/{pid}/schedules."""
        data = self._request(f"project/{project_id}/schedules")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /schedules")
        return [Schedule.model_validate(s) for s in data]

    def get_schedule(self, project_id: int, sched_id: int) -> Schedule:
        """GET /api/project/{pid}/schedules/{sid}."""
        data = self._request(f"project/{project_id}/schedules/{sched_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /schedules/{sid}")
        return Schedule.model_validate(data)

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
        data = self._request(f"project/{project_id}/schedules", method="POST", body=body)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /schedules")
        return Schedule.model_validate(data)

    def update_schedule(self, project_id: int, sched_id: int, **fields: Any) -> None:
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
        self._request(f"project/{project_id}/schedules/{sched_id}", method="DELETE")

    # ---- Projects CRUD --------------------------------------------------

    def get_project(self, project_id: int) -> Project:
        """GET /api/project/{pid}."""
        data = self._request(f"project/{project_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /project/{pid}")
        return Project.model_validate(data)

    def create_project(
        self,
        name: str,
        alert: bool = False,
        alert_chat: str = "",
        max_parallel_tasks: int = 0,
    ) -> Project:
        """POST /api/projects."""
        body: dict[str, Any] = {"name": name, "alert": alert}
        if alert_chat:
            body["alert_chat"] = alert_chat
        if max_parallel_tasks:
            body["max_parallel_tasks"] = max_parallel_tasks
        data = self._request("projects", method="POST", body=body)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /projects")
        return Project.model_validate(data)

    def update_project(self, project_id: int, **fields: Any) -> None:
        """PUT /api/project/{pid}."""
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body["id"] = project_id
        self._request(f"project/{project_id}", method="PUT", body=body)

    def delete_project(self, project_id: int) -> None:
        """DELETE /api/project/{pid}."""
        self._request(f"project/{project_id}", method="DELETE")

    # ---- Templates CRUD -------------------------------------------------

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
    ) -> Template:
        """POST /api/project/{pid}/templates."""
        body: dict[str, Any] = {
            "project_id": project_id,
            "name": name,
            "playbook": playbook,
            "inventory_id": inventory_id,
            "repository_id": repository_id,
        }
        if environment_id is not None:
            body["environment_id"] = environment_id
        if description:
            body["description"] = description
        if arguments:
            body["arguments"] = arguments
        data = self._request(f"project/{project_id}/templates", method="POST", body=body)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /templates")
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

    # ---- User (self) ----------------------------------------------------

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

    # ---- API info -------------------------------------------------------

    def get_info(self) -> ApiInfo:
        """GET /api/info — server metadata (no auth required)."""
        data = self._request("info", require_auth=False)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /info")
        return ApiInfo.model_validate(data)

    # ---- Project members ------------------------------------------------

    def list_project_members(self, project_id: int) -> list[ProjectMember]:
        """GET /api/project/{pid}/users."""
        data = self._request(f"project/{project_id}/users")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /project/{pid}/users")
        return [ProjectMember.model_validate(item) for item in data]

    def add_project_member(self, project_id: int, user_id: int, role: str) -> None:
        """POST /api/project/{pid}/users."""
        body: dict[str, Any] = {
            "user_id": user_id,
            "role": role,
            "project_id": project_id,
        }
        self._request(f"project/{project_id}/users", method="POST", body=body)

    def update_project_member(self, project_id: int, user_id: int, role: str) -> None:
        """PUT /api/project/{pid}/users/{uid}."""
        body: dict[str, Any] = {
            "user_id": user_id,
            "role": role,
            "project_id": project_id,
        }
        self._request(f"project/{project_id}/users/{user_id}", method="PUT", body=body)

    def remove_project_member(self, project_id: int, user_id: int) -> None:
        """DELETE /api/project/{pid}/users/{uid}."""
        self._request(f"project/{project_id}/users/{user_id}", method="DELETE")

    # ---- Admin users ----------------------------------------------------

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

    # ---- Views ----------------------------------------------------------

    def list_views(self, project_id: int) -> list[View]:
        """GET /api/project/{pid}/views."""
        data = self._request(f"project/{project_id}/views")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /project/{pid}/views")
        return [View.model_validate(v) for v in data]

    def get_view(self, project_id: int, view_id: int) -> View:
        """GET /api/project/{pid}/views/{vid}."""
        data = self._request(f"project/{project_id}/views/{view_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /project/{pid}/views/{vid}")
        return View.model_validate(data)

    def create_view(self, project_id: int, title: str, position: int = 0) -> View:
        """POST /api/project/{pid}/views."""
        body: dict[str, Any] = {
            "project_id": project_id,
            "title": title,
            "position": position,
        }
        data = self._request(f"project/{project_id}/views", method="POST", body=body)
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for POST /views")
        return View.model_validate(data)

    def update_view(self, project_id: int, view_id: int, **fields: Any) -> None:
        """PUT /api/project/{pid}/views/{vid}."""
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        body["id"] = view_id
        body["project_id"] = project_id
        self._request(f"project/{project_id}/views/{view_id}", method="PUT", body=body)

    def delete_view(self, project_id: int, view_id: int) -> None:
        """DELETE /api/project/{pid}/views/{vid}."""
        self._request(f"project/{project_id}/views/{view_id}", method="DELETE")

    # ---- Integrations ---------------------------------------------------

    def list_integrations(self, project_id: int) -> list[Integration]:
        """GET /api/project/{pid}/integrations."""
        data = self._request(f"project/{project_id}/integrations")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /project/{pid}/integrations")
        return [Integration.model_validate(i) for i in data]

    def get_integration(self, project_id: int, integration_id: int) -> Integration:
        """GET /api/project/{pid}/integrations/{iid}."""
        data = self._request(f"project/{project_id}/integrations/{integration_id}")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /integrations/{iid}")
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
            raise SemaphoreAPIError("Unexpected response for POST /integrations")
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

    # ---- Integration matchers -------------------------------------------

    def list_integration_matchers(
        self, project_id: int, integration_id: int
    ) -> list[IntegrationMatcher]:
        """GET /api/project/{pid}/integrations/{iid}/matchers."""
        data = self._request(f"project/{project_id}/integrations/{integration_id}/matchers")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /matchers")
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
            raise SemaphoreAPIError("Unexpected response for POST /matchers")
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

    # ---- Project events + backup ----------------------------------------

    def list_project_events(self, project_id: int) -> list[ProjectEvent]:
        """GET /api/project/{pid}/events."""
        data = self._request(f"project/{project_id}/events")
        if not isinstance(data, list):
            raise SemaphoreAPIError("Unexpected response for /events")
        return [ProjectEvent.model_validate(e) for e in data]

    def export_project_backup(self, project_id: int) -> dict[str, Any]:
        """GET /api/project/{pid}/backup — returns the full project as JSON."""
        data = self._request(f"project/{project_id}/backup")
        if not isinstance(data, dict):
            raise SemaphoreAPIError("Unexpected response for /backup")
        return data
