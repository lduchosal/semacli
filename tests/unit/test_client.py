"""Tests for semacli.core.client (requests-backed transport)."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

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


def _resp(
    body: str = "",
    status: int = 200,
    reason: str = "",
) -> MagicMock:
    """Build a Mock that quacks like a ``requests.Response``."""
    r = MagicMock(spec=requests.Response)
    r.status_code = status
    r.reason = reason or ("OK" if status == 200 else "")
    payload = body.encode("utf-8") if isinstance(body, str) else body
    r.text = body if isinstance(body, str) else body.decode("utf-8")
    r.content = payload
    return r


class TestRequestBuilding:
    def test_bearer_header_added(self) -> None:
        c = SemaphoreClient(_cfg())
        kwargs = c._build_request("projects")
        assert kwargs["headers"]["Authorization"] == "Bearer tok"
        assert kwargs["headers"]["Accept"] == "application/json"
        assert kwargs["url"] == "https://sema.example/api/projects"
        assert kwargs["method"] == "GET"

    def test_ping_skips_auth(self) -> None:
        c = SemaphoreClient(_cfg())
        kwargs = c._build_request("ping", require_auth=False)
        assert "Authorization" not in kwargs["headers"]

    def test_missing_token_raises(self) -> None:
        c = SemaphoreClient(_cfg(bearer_token=None))
        with pytest.raises(AuthenticationError):
            c._build_request("projects")

    def test_query_params_passed_through(self) -> None:
        c = SemaphoreClient(_cfg())
        kwargs = c._build_request("x", params={"a": "1", "b": "2"})
        assert kwargs["params"] == {"a": "1", "b": "2"}

    def test_post_body_serialized_as_json(self) -> None:
        c = SemaphoreClient(_cfg())
        kwargs = c._build_request("x", method="POST", body={"k": "v"})
        # `json=` lets requests serialize + set Content-Type itself.
        assert kwargs["json"] == {"k": "v"}
        assert kwargs["method"] == "POST"

    def test_timeout_propagates_from_config(self) -> None:
        c = SemaphoreClient(_cfg(timeout=42))
        kwargs = c._build_request("x")
        assert kwargs["timeout"] == 42


class TestSession:
    def test_session_cached(self) -> None:
        c = SemaphoreClient(_cfg())
        s1 = c._get_session()
        s2 = c._get_session()
        assert s1 is s2
        assert isinstance(s1, requests.Session)

    def test_secure_session_verifies_by_default(self) -> None:
        c = SemaphoreClient(_cfg(verify_ssl=True))
        assert c._get_session().verify is True

    def test_insecure_session_disables_verify(self) -> None:
        c = SemaphoreClient(_cfg(verify_ssl=False))
        assert c._get_session().verify is False


class TestSystemCA:
    def test_use_system_ca_triggers_truststore_inject(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Reset the module-level guard so we observe a fresh inject.
        monkeypatch.setattr("semacli.core.client._truststore_injected", False)
        with patch("semacli.core.client.truststore.inject_into_ssl") as inj:
            c = SemaphoreClient(_cfg(verify_ssl=True, use_system_ca=True))
            c._get_session()
            inj.assert_called_once()

    def test_use_system_ca_off_no_inject(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("semacli.core.client._truststore_injected", False)
        with patch("semacli.core.client.truststore.inject_into_ssl") as inj:
            c = SemaphoreClient(_cfg(verify_ssl=True, use_system_ca=False))
            c._get_session()
            inj.assert_not_called()

    def test_verify_off_skips_inject_even_with_system_ca(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No point patching ssl when verification is disabled altogether.
        monkeypatch.setattr("semacli.core.client._truststore_injected", False)
        with patch("semacli.core.client.truststore.inject_into_ssl") as inj:
            c = SemaphoreClient(_cfg(verify_ssl=False, use_system_ca=True))
            c._get_session()
            inj.assert_not_called()

    def test_inject_guard_idempotent_across_clients(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("semacli.core.client._truststore_injected", False)
        with patch("semacli.core.client.truststore.inject_into_ssl") as inj:
            for _ in range(3):
                SemaphoreClient(_cfg(verify_ssl=True, use_system_ca=True))._get_session()
            inj.assert_called_once()


class TestPing:
    def test_string_pong(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp("pong\n")
            assert c.ping() == "pong"

    def test_json_pong(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp('{"status":"ok"}')
            result = c.ping()
            assert "ok" in result or "status" in result


class TestGetProjects:
    def test_parses_list(self) -> None:
        payload = [
            {"id": 1, "name": "alpha"},
            {"id": 2, "name": "beta", "alert": True, "max_parallel_tasks": 3},
        ]
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp(json.dumps(payload))
            projects = c.get_projects()
        assert len(projects) == 2
        assert projects[0] == Project(id=1, name="alpha")
        assert projects[1].alert is True
        assert projects[1].max_parallel_tasks == 3

    def test_non_list_response_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp('{"oops": 1}')
            with pytest.raises(SemaphoreAPIError):
                c.get_projects()


class TestErrorMapping:
    def _client_returning(self, response: MagicMock) -> SemaphoreClient:
        c = SemaphoreClient(_cfg())
        session = MagicMock()
        session.request.return_value = response
        c._session = session  # type: ignore[assignment]
        return c

    def _client_raising(self, exc: BaseException) -> SemaphoreClient:
        c = SemaphoreClient(_cfg())
        session = MagicMock()
        session.request.side_effect = exc
        c._session = session  # type: ignore[assignment]
        return c

    def test_401_to_auth_error(self) -> None:
        c = self._client_returning(_resp(status=401, reason="Unauthorized"))
        with pytest.raises(AuthenticationError):
            c.get_projects()

    def test_403_to_auth_error(self) -> None:
        c = self._client_returning(_resp(status=403, reason="Forbidden"))
        with pytest.raises(AuthenticationError):
            c.get_projects()

    def test_404_to_not_found(self) -> None:
        c = self._client_returning(_resp(status=404, reason="Not Found"))
        with pytest.raises(NotFoundError):
            c.get_projects()

    def test_500_to_api_error(self) -> None:
        c = self._client_returning(_resp(status=500, reason="Server Error"))
        with pytest.raises(SemaphoreAPIError):
            c.get_projects()

    def test_connection_error_to_api_error(self) -> None:
        c = self._client_raising(requests.exceptions.ConnectionError("nx"))
        with pytest.raises(SemaphoreAPIError):
            c.get_projects()

    def test_timeout_to_api_error(self) -> None:
        c = self._client_raising(requests.exceptions.Timeout("slow"))
        with pytest.raises(SemaphoreAPIError):
            c.get_projects()

    def test_empty_response_returns_none(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp("")
            assert c._request("ping", require_auth=False) is None

    def test_verbose_prints(self, capsys: pytest.CaptureFixture[str]) -> None:
        c = SemaphoreClient(_cfg(), verbose=3)
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp("pong")
            c.ping()
        out = capsys.readouterr().out
        assert "GET" in out and "Response:" in out


class TestInsecureWarnings:
    def test_no_warning_when_secure(self, capsys: pytest.CaptureFixture[str]) -> None:
        SemaphoreClient(_cfg())
        assert capsys.readouterr().err == ""

    def test_warns_when_verify_ssl_false(self, capsys: pytest.CaptureFixture[str]) -> None:
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
