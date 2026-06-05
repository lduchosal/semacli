"""Tests for the P1 client methods (inventories, environments, repositories, keys, schedules + tasks list/stop/raw-output)."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

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


def _resp(body: str, status: int = 200) -> MagicMock:
    """Build a Mock that quacks like a ``requests.Response``."""
    m = MagicMock()
    m.status_code = status
    m.reason = "OK"
    m.text = body
    m.content = body.encode("utf-8")
    return m


class TestTasksExtras:
    def test_list_tasks(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value=[{"id": 1, "template_id": 10, "status": "success"}]
        ):
            tasks = c.list_tasks(5)
        assert tasks[0].id == 1
        assert tasks[0].status == "success"

    def test_stop_task(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.stop_task(5, 99)
        req.assert_called_once_with("project/5/tasks/99/stop", method="POST", body={})

    def test_raw_output_string(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value="PLAY [all]\nTASK [ping]"):
            assert "PLAY" in c.get_task_raw_output(5, 99)

    def test_raw_output_non_string(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"oops": 1}):
            assert c.get_task_raw_output(5, 99) == ""


class TestInventoriesClient:
    def test_list_parses(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp(
                json.dumps([{"id": 1, "name": "hosts", "type": "static", "inventory": "[all]"}])
            )
            inv = c.list_inventories(5)
        assert inv[0].content == "[all]"

    def test_get_parses(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp(
                json.dumps({"id": 1, "name": "hosts", "type": "static"})
            )
            assert c.get_inventory(5, 1).name == "hosts"

    def test_create_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 7}) as req:
            c.create_inventory(
                5,
                name="hosts",
                type="static",
                content="[all]\nans1",
                ssh_key_id=3,
                become_key_id=4,
            )
        body = req.call_args.kwargs["body"]
        assert body["name"] == "hosts"
        assert body["inventory"] == "[all]\nans1"
        assert body["ssh_key_id"] == 3
        assert body["become_key_id"] == 4
        assert body["project_id"] == 5

    def test_update_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_inventory(5, 7, name="renamed", inventory="new content")
        body = req.call_args.kwargs["body"]
        assert body == {"name": "renamed", "inventory": "new content", "id": 7, "project_id": 5}

    def test_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.delete_inventory(5, 7)
        assert req.call_args.args[0] == "project/5/inventory/7"
        assert req.call_args.kwargs["method"] == "DELETE"

    def test_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.list_inventories(5)


class TestEnvironmentsClient:
    def test_list_show(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[{"id": 1, "name": "prod"}]):
            assert c.list_environments(5)[0].name == "prod"
        with patch.object(c, "_request", return_value={"id": 1, "json": '{"k":"v"}'}):
            assert c.get_environment(5, 1).vars_json == '{"k":"v"}'

    def test_create_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 1}) as req:
            c.create_environment(5, name="prod", json_vars='{"k":"v"}', password="sekret")
        body = req.call_args.kwargs["body"]
        assert body == {"name": "prod", "json": '{"k":"v"}', "password": "sekret", "project_id": 5}

    def test_update_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_environment(5, 7, name="renamed")
        assert req.call_args.kwargs["body"]["name"] == "renamed"
        with patch.object(c, "_request", return_value=None) as req:
            c.delete_environment(5, 7)
        assert req.call_args.kwargs["method"] == "DELETE"


class TestRepositoriesClient:
    def test_list_show(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[{"id": 1, "git_url": "g"}]):
            assert c.list_repositories(5)[0].git_url == "g"
        with patch.object(c, "_request", return_value={"id": 1, "git_branch": "main"}):
            assert c.get_repository(5, 1).git_branch == "main"

    def test_create_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 1}) as req:
            c.create_repository(5, name="r", git_url="git@x", git_branch="main", ssh_key_id=3)
        body = req.call_args.kwargs["body"]
        assert body == {
            "name": "r",
            "git_url": "git@x",
            "git_branch": "main",
            "ssh_key_id": 3,
            "project_id": 5,
        }

    def test_update_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_repository(5, 7, git_branch="develop")
        assert req.call_args.kwargs["body"]["git_branch"] == "develop"
        with patch.object(c, "_request", return_value=None):
            c.delete_repository(5, 7)


class TestKeysClient:
    def test_list_show(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[{"id": 1, "type": "ssh"}]):
            assert c.list_keys(5)[0].type == "ssh"
        with patch.object(c, "_request", return_value={"id": 1, "type": "ssh"}):
            assert c.get_key(5, 1).type == "ssh"

    def test_create_ssh(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 1}) as req:
            c.create_key(5, name="k", type="ssh", login="root", private_key="PEM")
        body = req.call_args.kwargs["body"]
        assert body["ssh"] == {"login": "root", "passphrase": "", "private_key": "PEM"}
        assert body["type"] == "ssh"

    def test_create_login_password(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 1}) as req:
            c.create_key(5, name="k", type="login_password", login="u", password="p")
        body = req.call_args.kwargs["body"]
        assert body["login_password"] == {"login": "u", "password": "p"}

    def test_update_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_key(5, 7, name="renamed")
        assert req.call_args.kwargs["body"]["name"] == "renamed"
        with patch.object(c, "_request", return_value=None):
            c.delete_key(5, 7)


class TestSchedulesClient:
    def test_list_show(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c,
            "_request",
            return_value=[{"id": 1, "template_id": 10, "cron_format": "* * * * *"}],
        ):
            assert c.list_schedules(5)[0].cron_format == "* * * * *"
        with patch.object(c, "_request", return_value={"id": 1, "active": False}):
            assert c.get_schedule(5, 1).active is False

    def test_create_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 1}) as req:
            c.create_schedule(5, template_id=10, cron_format="0 3 * * *", name="nightly")
        body = req.call_args.kwargs["body"]
        assert body == {
            "template_id": 10,
            "cron_format": "0 3 * * *",
            "name": "nightly",
            "project_id": 5,
            "active": True,
        }

    def test_update_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_schedule(5, 7, active=False)
        assert req.call_args.kwargs["body"]["active"] is False
        with patch.object(c, "_request", return_value=None):
            c.delete_schedule(5, 7)
