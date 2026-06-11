"""HTTP transport for the Semaphore API client."""

import json
import sys
from http import HTTPStatus
from typing import Any

import requests
import truststore
import urllib3

from ..config import SemaphoreConfig
from ..exceptions import AuthenticationError, NotFoundError, SemaphoreAPIError

# Verbosity tiers (UX.md: -v config, -vv requests, -vvv response bodies).
_VERBOSE_REQUESTS = 2
_VERBOSE_RESPONSES = 3
# Any HTTP status in this range is surfaced as a semacli exception.
_HTTP_ERROR_RANGE = range(400, 600)


def _split_csv(raw: str) -> list[str]:
    """Split an ansible-style comma list into trimmed non-empty items."""
    return [s.strip() for s in raw.split(",") if s.strip()]


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


class BaseClient:
    """Transport layer: session management, request building, error mapping.

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
        """Warn once on stderr when SSL verification is off or the URL is plain HTTP."""
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
            s.verify = self.config.verify_ssl
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
        *,
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
                msg = "No bearer_token configured"
                raise AuthenticationError(msg)
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

        if self.verbose >= _VERBOSE_REQUESTS:
            print(f"DEBUG: {method} {url}")
        return kwargs

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        *,
        require_auth: bool = True,
    ) -> Any:  # noqa: ANN401  # returns parsed JSON, shape varies per endpoint
        """Make HTTP request to Semaphore API and return parsed JSON (or raw text)."""
        kwargs = self._build_request(endpoint, method, params, body, require_auth=require_auth)

        try:
            response = self._get_session().request(**kwargs)
        except requests.exceptions.RequestException as e:
            msg = f"Connection error: {e}"
            raise SemaphoreAPIError(msg) from e

        text = response.text
        status = response.status_code

        if self.verbose >= _VERBOSE_RESPONSES:
            print(f"DEBUG: Response: {text[:500]}")

        if status in _HTTP_ERROR_RANGE:
            reason = response.reason
            # Include the server body in the message so the user sees the
            # actual reason Semaphore complained (truncated to keep the
            # exception printable).
            detail = text.strip()[:500]
            suffix = f" — {detail}" if detail else ""
            if status in (401, 403):
                msg = f"HTTP {status}: {reason}{suffix}"
                raise AuthenticationError(msg)
            if status == HTTPStatus.NOT_FOUND:
                msg = f"HTTP 404: {endpoint}{suffix}"
                raise NotFoundError(msg)
            msg = f"HTTP {status}: {reason}{suffix}"
            raise SemaphoreAPIError(msg)

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
