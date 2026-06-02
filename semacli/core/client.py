"""Semaphore HTTP API client."""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import SemaphoreConfig
from .exceptions import AuthenticationError, NotFoundError, SemaphoreAPIError
from .models import Project


class SemaphoreClient:
    """HTTP client for Semaphore UI REST API."""

    def __init__(self, config: SemaphoreConfig, verbose: int = 0) -> None:
        self.config = config
        self.verbose = verbose
        self._opener: urllib.request.OpenerDirector | None = None

    def _get_opener(self) -> urllib.request.OpenerDirector:
        """Get or create HTTP opener with SSL handling."""
        if self._opener is None:
            handlers: list[urllib.request.BaseHandler] = []

            if not self.config.verify_ssl:
                # Opt-in insecure mode for self-signed certs.
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False  # NOSONAR: explicit user opt-in via verify_ssl=False
                ssl_context.verify_mode = ssl.CERT_NONE  # NOSONAR: explicit user opt-in via verify_ssl=False
                handlers.append(urllib.request.HTTPSHandler(context=ssl_context))

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
