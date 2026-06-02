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
from .models import Project, Task, Template


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
