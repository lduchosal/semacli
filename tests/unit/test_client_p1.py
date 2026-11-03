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
        current = {
            "id": 7,
            "project_id": 5,
            "name": "old",
            "type": "static",
            "inventory": "old content",
            "ssh_key_id": 2,
            "become_key_id": 3,
        }
        with patch.object(c, "_request", side_effect=[current, None]) as req:
            c.update_inventory(5, 7, name="renamed", inventory="new content")
        body = req.call_args.kwargs["body"]
        assert body == {**current, "name": "renamed", "inventory": "new content"}

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
        current = {
            "id": 7,
            "project_id": 5,
            "name": "old",
            "json": '{"a": 1}',
            "env": "{}",
            "password": "vault",
            "secrets": [{"id": 1, "name": "S"}],
        }
        with patch.object(c, "_request", side_effect=[current, None]) as req:
            c.update_environment(5, 7, name="renamed")
        body = req.call_args.kwargs["body"]
        assert body["name"] == "renamed"
        # ken #1170: extra vars + vault password kept; secrets list not replayed as ops.
        assert body["json"] == '{"a": 1}'
        assert body["password"] == "vault"
        assert "secrets" not in body
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
        current = {
            "id": 7,
            "project_id": 5,
            "name": "r",
            "git_url": "svn+ssh://x",
            "git_branch": "trunk",
            "ssh_key_id": 2,
        }
        with patch.object(c, "_request", side_effect=[current, None]) as req:
            c.update_repository(5, 7, git_branch="develop")
        assert req.call_args.kwargs["body"] == {**current, "git_branch": "develop"}
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
        current = {"id": 7, "project_id": 5, "name": "old", "type": "ssh", "empty": False}
        with patch.object(c, "_request", side_effect=[current, None]) as req:
            c.update_key(5, 7, name="renamed")
        body = req.call_args.kwargs["body"]
        assert body == {"id": 7, "project_id": 5, "name": "renamed", "type": "ssh"}
        assert "override_secret" not in body  # rename never touches the secret
        with patch.object(c, "_request", return_value=None):
            c.delete_key(5, 7)

    def test_update_private_key_overrides_secret(self) -> None:
        # ken #1170: without override_secret the server silently kept the old key.
        c = SemaphoreClient(_cfg())
        current = {"id": 7, "project_id": 5, "name": "deploy", "type": "login_password"}
        ssh = {"private_key": "PEM", "login": "root", "passphrase": ""}
        with patch.object(c, "_request", side_effect=[current, None]) as req:
            c.update_key(5, 7, ssh=ssh)
        body = req.call_args.kwargs["body"]
        assert body["name"] == "deploy"
        assert body["override_secret"] is True
        assert body["type"] == "ssh"
        assert body["ssh"] == ssh


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

    def test_create_body_with_overrides(self) -> None:
        # ken #907: inventory/message/cli-args ride in task_params; limit/tags/
        # skip-tags in the nested params; run-at/once at the top level.
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 1}) as req:
            c.create_schedule(
                5,
                template_id=10,
                cron_format="",
                name="oneshot",
                schedule_type="run_at",
                run_at="2026-06-25T02:00:00Z",
                delete_after_run=True,
                message="hi",
                inventory_id=4,
                cli_args='["--forks","5"]',
                limit="h1,h2",
                tags="pkg",
                skip_tags="slow",
            )
        body = req.call_args.kwargs["body"]
        assert body["type"] == "run_at"
        assert body["run_at"] == "2026-06-25T02:00:00Z"
        assert body["delete_after_run"] is True
        assert body["task_params"] == {
            "message": "hi",
            "inventory_id": 4,
            "arguments": '["--forks","5"]',
            "params": {"limit": ["h1", "h2"], "tags": ["pkg"], "skip_tags": ["slow"]},
        }

    @staticmethod
    def _current() -> dict[str, Any]:
        """A schedule as GET returns it: cron, inventory + limit + tags set."""
        return {
            "id": 7,
            "project_id": 5,
            "template_id": 10,
            "cron_format": "0 6 * * *",
            "name": "winchoco",
            "active": True,
            "type": "",
            "delete_after_run": False,
            "repository_id": None,
            "task_params": {
                "inventory_id": 4,
                "message": "keep",
                "params": {"limit": ["ci-01"], "tags": ["pkg"]},
            },
        }

    def _run_update(self, **kwargs: Any) -> list[Any]:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", side_effect=[self._current(), None]) as req:
            c.update_schedule(5, 7, **kwargs)
        return req.call_args_list

    def test_update_is_read_modify_write(self) -> None:
        # ken #1169: PUT is a full replace server-side -> GET then PUT everything.
        calls = self._run_update(cron_format="30 6 * * *")
        assert calls[0].args == ("project/5/schedules/7",)
        put = calls[1]
        assert put.kwargs["method"] == "PUT"
        body = put.kwargs["body"]
        assert body["cron_format"] == "30 6 * * *"
        assert body["type"] == ""  # db.ScheduleTypeCron
        # untouched fields survive (the bug: limit was wiped)
        assert body["name"] == "winchoco"
        assert body["template_id"] == 10
        assert body["active"] is True
        assert body["task_params"]["params"]["limit"] == ["ci-01"]
        assert body["task_params"]["inventory_id"] == 4

    def test_update_overrides_merge_task_params(self) -> None:
        body = self._run_update(limit="h3", skip_tags="slow")[1].kwargs["body"]
        assert body["id"] == 7
        assert body["cron_format"] == "0 6 * * *"
        assert body["task_params"] == {
            "inventory_id": 4,
            "message": "keep",
            "params": {"limit": ["h3"], "tags": ["pkg"], "skip_tags": ["slow"]},
        }

    def test_update_overrides_on_schedule_without_task_params(self) -> None:
        c = SemaphoreClient(_cfg())
        current = {**self._current(), "task_params": None}
        with patch.object(c, "_request", side_effect=[current, None]) as req:
            c.update_schedule(5, 7, limit="h1")
        assert req.call_args.kwargs["body"]["task_params"] == {"params": {"limit": ["h1"]}}

    def test_update_body_run_at(self) -> None:
        body = self._run_update(
            schedule_type="run_at", run_at="2026-06-25T02:00:00Z", delete_after_run=False
        )[1].kwargs["body"]
        assert body["type"] == "run_at"
        assert body["run_at"] == "2026-06-25T02:00:00Z"
        assert body["cron_format"] == ""
        assert body["delete_after_run"] is False  # --no-once sends an explicit False

    def test_update_cron_on_run_at_schedule_switches_back(self) -> None:
        c = SemaphoreClient(_cfg())
        current = {
            **self._current(),
            "type": "run_at",
            "cron_format": "",
            "run_at": "2030-01-01T02:00:00Z",
        }
        with patch.object(c, "_request", side_effect=[current, None]) as req:
            c.update_schedule(5, 7, cron_format="0 3 * * *")
        body = req.call_args.kwargs["body"]
        assert body["type"] == ""  # db.ScheduleTypeCron
        assert "run_at" not in body

    def test_update_active_only_uses_active_endpoint(self) -> None:
        # ken #1169: `--inactive` must not resend a (possibly empty) cron.
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_schedule(5, 7, active=False)
        req.assert_called_once_with(
            "project/5/schedules/7/active", method="PUT", body={"active": False}
        )

    def test_update_nothing_is_noop(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request") as req:
            c.update_schedule(5, 7)
        req.assert_not_called()

    def test_update_bad_get_response(self) -> None:
        c = SemaphoreClient(_cfg())
        with (
            patch.object(c, "_request", return_value=[]),
            pytest.raises(SemaphoreAPIError),
        ):
            c.update_schedule(5, 7, name="x")

    def test_delete_schedule(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None):
            c.delete_schedule(5, 7)
