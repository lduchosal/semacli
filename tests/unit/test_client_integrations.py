"""Tests for the integrations client mixin (integrations + matchers CRUD)."""

from typing import Any
from unittest.mock import patch

import pytest

from semacli.core.client import SemaphoreClient
from semacli.core.config import SemaphoreConfig
from semacli.core.exceptions import SemaphoreAPIError


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


class TestIntegrationsClient:
    def test_list(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value=[{"id": 1, "name": "hook", "template_id": 10}]
        ) as req:
            integrations = c.list_integrations(5)
        assert integrations[0].name == "hook"
        assert integrations[0].template_id == 10
        assert req.call_args.args[0] == "project/5/integrations"

    def test_list_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.list_integrations(5)

    def test_get(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value={"id": 7, "name": "hook", "auth_method": "token"}
        ) as req:
            integration = c.get_integration(5, 7)
        assert integration.id == 7
        assert integration.auth_method == "token"
        assert req.call_args.args[0] == "project/5/integrations/7"

    def test_get_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.get_integration(5, 7)

    def test_create_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 7, "name": "hook"}) as req:
            integration = c.create_integration(
                5, name="hook", template_id=10, auth_method="token", auth_header="X-Tok"
            )
        assert integration.id == 7
        body = req.call_args.kwargs["body"]
        assert body == {
            "project_id": 5,
            "name": "hook",
            "template_id": 10,
            "auth_method": "token",
            "auth_header": "X-Tok",
        }
        assert req.call_args.kwargs["method"] == "POST"

    def test_create_with_secret_id(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 7}) as req:
            c.create_integration(5, name="hook", template_id=10, auth_secret_id=3)
        body = req.call_args.kwargs["body"]
        assert body["auth_secret_id"] == 3
        assert "auth_header" not in body

    def test_create_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.create_integration(5, name="hook", template_id=10)

    def test_update_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_integration(5, 7, name="renamed", auth_method=None)
        body = req.call_args.kwargs["body"]
        assert body == {"name": "renamed", "id": 7, "project_id": 5}
        assert req.call_args.args[0] == "project/5/integrations/7"
        assert req.call_args.kwargs["method"] == "PUT"

    def test_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.delete_integration(5, 7)
        assert req.call_args.args[0] == "project/5/integrations/7"
        assert req.call_args.kwargs["method"] == "DELETE"


class TestIntegrationMatchersClient:
    def test_list(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c,
            "_request",
            return_value=[{"id": 1, "integration_id": 7, "name": "m", "match_type": "body"}],
        ) as req:
            matchers = c.list_integration_matchers(5, 7)
        assert matchers[0].match_type == "body"
        assert req.call_args.args[0] == "project/5/integrations/7/matchers"

    def test_list_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.list_integration_matchers(5, 7)

    def test_add_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 1, "name": "m"}) as req:
            matcher = c.add_integration_matcher(
                5, 7, name="m", match_type="body", method="equals", key="ref", value="main"
            )
        assert matcher.name == "m"
        body = req.call_args.kwargs["body"]
        assert body == {
            "integration_id": 7,
            "name": "m",
            "match_type": "body",
            "method": "equals",
            "key": "ref",
            "value": "main",
        }
        assert req.call_args.kwargs["method"] == "POST"

    def test_add_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.add_integration_matcher(
                    5, 7, name="m", match_type="body", method="equals", key="k", value="v"
                )

    def test_update_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_integration_matcher(5, 7, 3, value="develop", key=None)
        body = req.call_args.kwargs["body"]
        assert body == {"value": "develop", "id": 3, "integration_id": 7}
        assert req.call_args.args[0] == "project/5/integrations/7/matchers/3"
        assert req.call_args.kwargs["method"] == "PUT"

    def test_remove(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.remove_integration_matcher(5, 7, 3)
        assert req.call_args.args[0] == "project/5/integrations/7/matchers/3"
        assert req.call_args.kwargs["method"] == "DELETE"
