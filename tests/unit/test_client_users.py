"""Tests for the users client mixin (self, tokens, admin users, server info)."""

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


class TestWhoami:
    def test_whoami(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value={"id": 1, "username": "luc", "admin": True}
        ) as req:
            user = c.whoami()
        assert user.username == "luc"
        assert user.admin is True
        assert req.call_args.args[0] == "user"

    def test_whoami_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.whoami()


class TestUserTokens:
    def test_list(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value=[{"id": "abc", "expired": False, "user_id": 1}]
        ) as req:
            tokens = c.list_user_tokens()
        assert tokens[0].id == "abc"
        assert tokens[0].expired is False
        assert req.call_args.args[0] == "user/tokens"

    def test_list_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.list_user_tokens()

    def test_create(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": "fresh", "user_id": 1}) as req:
            token = c.create_user_token()
        assert token.id == "fresh"
        req.assert_called_once_with("user/tokens", method="POST", body={})

    def test_create_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.create_user_token()

    def test_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.delete_user_token("abc")
        req.assert_called_once_with("user/tokens/abc", method="DELETE")


class TestServerInfo:
    def test_get_info(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"version": "2.10.22"}) as req:
            info = c.get_info()
        assert info.version == "2.10.22"
        req.assert_called_once_with("info", require_auth=False)

    def test_get_info_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.get_info()


class TestAdminUsers:
    def test_list(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value=[{"id": 1, "username": "luc"}, {"id": 2, "username": "bob"}]
        ) as req:
            users = c.list_users()
        assert [u.username for u in users] == ["luc", "bob"]
        assert req.call_args.args[0] == "users"

    def test_list_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.list_users()

    def test_get(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 2, "email": "bob@example"}) as req:
            user = c.get_user(2)
        assert user.email == "bob@example"
        assert req.call_args.args[0] == "users/2"

    def test_get_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.get_user(2)

    def test_create_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 3, "username": "bob"}) as req:
            user = c.create_user("bob", "Bob", "bob@example", "sekret", admin=True)
        assert user.id == 3
        body = req.call_args.kwargs["body"]
        assert body == {
            "username": "bob",
            "name": "Bob",
            "email": "bob@example",
            "password": "sekret",
            "admin": True,
        }
        assert req.call_args.kwargs["method"] == "POST"

    def test_create_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.create_user("bob", "Bob", "bob@example", "sekret")

    def test_update_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_user(2, name="Robert", email=None)
        body = req.call_args.kwargs["body"]
        assert body == {"name": "Robert", "id": 2}
        assert req.call_args.args[0] == "users/2"
        assert req.call_args.kwargs["method"] == "PUT"

    def test_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.delete_user(2)
        req.assert_called_once_with("users/2", method="DELETE")

    def test_set_password(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.set_user_password(2, "newpass")
        req.assert_called_once_with("users/2/password", method="POST", body={"password": "newpass"})
