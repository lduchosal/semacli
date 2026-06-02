"""Tests for semacli.core.client."""

import io
import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from semacli.core.client import SemaphoreClient
from semacli.core.config import SemaphoreConfig
from semacli.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    SemaphoreAPIError,
)
from semacli.core.models import Project


def _cfg(**overrides: Any) -> SemaphoreConfig:
    base = {
        "url": "https://sema.example",
        "bearer_token": "tok",
        "timeout": 5,
        "verify_ssl": True,
        "allow_http": False,
    }
    base.update(overrides)
    return SemaphoreConfig(**base)


def _http_response(body: str | bytes, status: int = 200) -> MagicMock:
    if isinstance(body, str):
        body = body.encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    return resp


class TestRequestBuilding:
    def test_bearer_header_added(self) -> None:
        c = SemaphoreClient(_cfg())
        req = c._build_request("projects")
        assert req.get_header("Authorization") == "Bearer tok"
        assert req.get_header("Accept") == "application/json"
        assert req.full_url == "https://sema.example/api/projects"

    def test_ping_skips_auth(self) -> None:
        c = SemaphoreClient(_cfg())
        req = c._build_request("ping", require_auth=False)
        assert req.get_header("Authorization") is None

    def test_missing_token_raises(self) -> None:
        c = SemaphoreClient(_cfg(bearer_token=None))
        with pytest.raises(AuthenticationError):
            c._build_request("projects")

    def test_query_params_encoded(self) -> None:
        c = SemaphoreClient(_cfg())
        req = c._build_request("x", params={"a": "1", "b": "2"})
        assert "a=1" in req.full_url and "b=2" in req.full_url

    def test_post_body_serialized(self) -> None:
        c = SemaphoreClient(_cfg())
        req = c._build_request("x", method="POST", body={"k": "v"})
        assert req.get_header("Content-type") == "application/json"
        assert req.data == b'{"k": "v"}'


class TestOpener:
    def test_opener_cached(self) -> None:
        c = SemaphoreClient(_cfg())
        op1 = c._get_opener()
        op2 = c._get_opener()
        assert op1 is op2

    def test_opener_skips_ssl_verify_when_disabled(self) -> None:
        c = SemaphoreClient(_cfg(verify_ssl=False))
        opener = c._get_opener()
        # one of the handlers should be an HTTPSHandler with a custom SSL ctx
        assert any(
            type(h).__name__ == "HTTPSHandler" for h in opener.handlers
        )

    def test_secure_opener_uses_certifi_bundle(self, monkeypatch: Any) -> None:
        # urllib's default SSL store is broken on Python.org macOS builds;
        # secure mode must pin to certifi's bundle.
        import certifi

        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        monkeypatch.delenv("SSL_CERT_DIR", raising=False)
        c = SemaphoreClient(_cfg(verify_ssl=True))
        opener = c._get_opener()
        https = next(
            h for h in opener.handlers if type(h).__name__ == "HTTPSHandler"
        )
        ctx = https._context
        assert ctx.verify_mode == __import__("ssl").CERT_REQUIRED
        assert ctx.check_hostname is True
        # cafile=certifi.where() shows up as a loaded location
        locations = ctx.get_ca_certs()
        assert len(locations) > 0
        # sanity check: certifi bundle should be referenced
        assert certifi.where()

    def test_secure_opener_respects_ssl_cert_file_env(
        self, monkeypatch: Any
    ) -> None:
        # When the operator pins SSL_CERT_FILE we must not override it.
        import certifi

        monkeypatch.setenv("SSL_CERT_FILE", certifi.where())
        c = SemaphoreClient(_cfg(verify_ssl=True))
        opener = c._get_opener()
        https = next(
            h for h in opener.handlers if type(h).__name__ == "HTTPSHandler"
        )
        assert https._context.verify_mode == __import__("ssl").CERT_REQUIRED


class TestPing:
    def test_string_pong(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_opener") as opener:
            opener.return_value.open.return_value = _http_response("pong\n")
            assert c.ping() == "pong"

    def test_json_pong(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_opener") as opener:
            opener.return_value.open.return_value = _http_response('{"status":"ok"}')
            result = c.ping()
            assert "ok" in result or "status" in result


class TestGetProjects:
    def test_parses_list(self) -> None:
        payload = [
            {"id": 1, "name": "alpha"},
            {"id": 2, "name": "beta", "alert": True, "max_parallel_tasks": 3},
        ]
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_opener") as opener:
            opener.return_value.open.return_value = _http_response(json.dumps(payload))
            projects = c.get_projects()
        assert len(projects) == 2
        assert projects[0] == Project(id=1, name="alpha")
        assert projects[1].alert is True
        assert projects[1].max_parallel_tasks == 3

    def test_non_list_response_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_opener") as opener:
            opener.return_value.open.return_value = _http_response('{"oops": 1}')
            with pytest.raises(SemaphoreAPIError):
                c.get_projects()


class TestErrorMapping:
    def _raise(self, exc: Exception) -> MagicMock:
        opener = MagicMock()
        opener.open.side_effect = exc
        return opener

    def test_401_to_auth_error(self) -> None:
        c = SemaphoreClient(_cfg())
        http_err = urllib.error.HTTPError(
            "u", 401, "Unauthorized", {}, io.BytesIO(b"")  # type: ignore[arg-type]
        )
        with patch.object(c, "_get_opener", return_value=self._raise(http_err)):
            with pytest.raises(AuthenticationError):
                c.get_projects()

    def test_403_to_auth_error(self) -> None:
        c = SemaphoreClient(_cfg())
        http_err = urllib.error.HTTPError(
            "u", 403, "Forbidden", {}, io.BytesIO(b"")  # type: ignore[arg-type]
        )
        with patch.object(c, "_get_opener", return_value=self._raise(http_err)):
            with pytest.raises(AuthenticationError):
                c.get_projects()

    def test_404_to_not_found(self) -> None:
        c = SemaphoreClient(_cfg())
        http_err = urllib.error.HTTPError(
            "u", 404, "Not Found", {}, io.BytesIO(b"")  # type: ignore[arg-type]
        )
        with patch.object(c, "_get_opener", return_value=self._raise(http_err)):
            with pytest.raises(NotFoundError):
                c.get_projects()

    def test_500_to_api_error(self) -> None:
        c = SemaphoreClient(_cfg())
        http_err = urllib.error.HTTPError(
            "u", 500, "Server Error", {}, io.BytesIO(b"")  # type: ignore[arg-type]
        )
        with patch.object(c, "_get_opener", return_value=self._raise(http_err)):
            with pytest.raises(SemaphoreAPIError):
                c.get_projects()

    def test_urlerror_to_api_error(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_get_opener", return_value=self._raise(urllib.error.URLError("nx"))
        ):
            with pytest.raises(SemaphoreAPIError):
                c.get_projects()

    def test_empty_response_returns_none(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_opener") as opener:
            opener.return_value.open.return_value = _http_response("")
            assert c._request("ping", require_auth=False) is None

    def test_verbose_prints(self, capsys: pytest.CaptureFixture[str]) -> None:
        c = SemaphoreClient(_cfg(), verbose=3)
        with patch.object(c, "_get_opener") as opener:
            opener.return_value.open.return_value = _http_response("pong")
            c.ping()
        out = capsys.readouterr().out
        assert "GET" in out and "Response:" in out


class TestInsecureWarnings:
    def test_no_warning_when_secure(self, capsys: pytest.CaptureFixture[str]) -> None:
        SemaphoreClient(_cfg())
        assert capsys.readouterr().err == ""

    def test_warns_when_verify_ssl_false(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        SemaphoreClient(_cfg(verify_ssl=False))
        err = capsys.readouterr().err
        assert "TLS certificate verification is DISABLED" in err

    def test_warns_when_http(self, capsys: pytest.CaptureFixture[str]) -> None:
        SemaphoreClient(_cfg(url="http://sema.example", allow_http=True))
        err = capsys.readouterr().err
        assert "plain HTTP" in err

    def test_warns_for_both(self, capsys: pytest.CaptureFixture[str]) -> None:
        SemaphoreClient(_cfg(url="http://sema.example", allow_http=True, verify_ssl=False))
        err = capsys.readouterr().err
        assert "TLS certificate verification is DISABLED" in err
        assert "plain HTTP" in err
