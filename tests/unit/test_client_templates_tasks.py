"""Tests for the templates + tasks client methods."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from semacli.core.client import SemaphoreClient
from semacli.core.config import SemaphoreConfig
from semacli.core.exceptions import SemaphoreAPIError
from semacli.core.models import Task, Template


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


class TestTemplates:
    def test_list_parses(self) -> None:
        payload = [
            {"id": 1, "project_id": 5, "name": "deploy", "playbook": "site.yml"},
            {"id": 2, "project_id": 5, "name": "backup"},
        ]
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp(json.dumps(payload))
            templates = c.get_templates(5)
        assert templates == [
            Template(id=1, project_id=5, name="deploy", playbook="site.yml"),
            Template(id=2, project_id=5, name="backup"),
        ]

    def test_list_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp('{"oops": 1}')
            with pytest.raises(SemaphoreAPIError):
                c.get_templates(5)

    def test_create_sends_app_ansible_by_default(self) -> None:
        # Modern Semaphore rejects a template without `app` with
        # HTTP 400 "Invalid app id" (ken #812).
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp('{"id": 183, "name": "x"}')
            c.create_template(1, name="x", playbook="x.yml", inventory_id=4, repository_id=3)
        body = session.return_value.request.call_args.kwargs["json"]
        assert body["app"] == "ansible"

    def test_create_sends_permissive_task_params(self) -> None:
        # Without task_params the server forbids every per-run override
        # and silently drops --limit/--tags/--debug (ken #826).
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp('{"id": 183, "name": "x"}')
            c.create_template(1, name="x", playbook="x.yml", inventory_id=4, repository_id=3)
        body = session.return_value.request.call_args.kwargs["json"]
        assert body["allow_override_args_in_task"] is True
        assert body["task_params"] == {
            "allow_debug": True,
            "allow_override_inventory": True,
            "allow_override_limit": True,
            "allow_override_skip_tags": True,
            "allow_override_tags": True,
        }

    def test_create_app_override(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp('{"id": 184, "name": "x"}')
            c.create_template(
                1, name="x", playbook="x.tf", inventory_id=4, repository_id=3, app="terraform"
            )
        body = session.return_value.request.call_args.kwargs["json"]
        assert body["app"] == "terraform"

    def test_show_parses(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp(
                json.dumps(
                    {
                        "id": 7,
                        "project_id": 5,
                        "name": "deploy",
                        "playbook": "site.yml",
                        "inventory_id": 3,
                        "repository_id": 4,
                        "environment_id": 6,
                        "description": "prod",
                    }
                )
            )
            t = c.get_template(5, 7)
        assert t.id == 7
        assert t.description == "prod"
        assert t.inventory_id == 3

    def test_show_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp("[]")
            with pytest.raises(SemaphoreAPIError):
                c.get_template(5, 7)


class TestRunTask:
    def test_minimal_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 99, "template_id": 10}) as req:
            t = c.run_task(5, 10)
        req.assert_called_once_with("project/5/tasks", method="POST", body={"template_id": 10})
        assert t.id == 99

    def test_full_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 99}) as req:
            c.run_task(
                5,
                10,
                playbook="custom.yml",
                environment='{"k": "v"}',
                limit="ans1",
                debug=2,
                dry_run=True,
            )
        body = req.call_args.kwargs["body"]
        # Ansible flags live under `params`; only template_id, playbook
        # and environment stay at the top level of the body (cf ken #782
        # — top-level dry_run/diff/debug were silently dropped server-side).
        assert body == {
            "template_id": 10,
            "playbook": "custom.yml",
            "environment": '{"k": "v"}',
            "params": {
                "limit": ["ans1"],
                "dry_run": True,
                "debug": True,
                "debug_level": 2,
            },
        }

    def test_csv_limit_tags_split_into_arrays(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 99}) as req:
            c.run_task(5, 10, limit="ans1,ans2", tags="ntp, users", skip_tags="slow")
        body = req.call_args.kwargs["body"]
        assert body["params"]["limit"] == ["ans1", "ans2"]
        assert body["params"]["tags"] == ["ntp", "users"]
        assert body["params"]["skip_tags"] == ["slow"]

    def test_diff_flag_propagates(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 99}) as req:
            c.run_task(5, 10, diff=True)
        body = req.call_args.kwargs["body"]
        assert body["params"] == {"diff": True}

    def test_no_params_dict_when_all_defaults(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 99}) as req:
            c.run_task(5, 10)
        body = req.call_args.kwargs["body"]
        # When no ansible flags are given, params is absent — the server
        # treats absent params and {} the same, but absence is the
        # cleanest contract.
        assert "params" not in body

    def test_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=["not", "a", "dict"]):
            with pytest.raises(SemaphoreAPIError):
                c.run_task(5, 10)


class TestGetTask:
    def test_parses(self) -> None:
        c = SemaphoreClient(_cfg())
        payload = {
            "id": 99,
            "template_id": 10,
            "status": "success",
            "playbook": "site.yml",
            "created": "2026-06-02T10:00:00Z",
            "start": "2026-06-02T10:00:01Z",
            "end": "2026-06-02T10:00:30Z",
        }
        with patch.object(c, "_request", return_value=payload):
            t = c.get_task(5, 99)
        assert t == Task(
            id=99,
            template_id=10,
            status="success",
            playbook="site.yml",
            created="2026-06-02T10:00:00Z",
            start="2026-06-02T10:00:01Z",
            end="2026-06-02T10:00:30Z",
        )

    def test_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.get_task(5, 99)


class TestGetTaskOutput:
    def test_returns_list(self) -> None:
        c = SemaphoreClient(_cfg())
        payload = [
            {"time": "2026-06-02T10:00:01Z", "output": "PLAY [all]"},
            {"time": "2026-06-02T10:00:02Z", "output": "TASK [ping]"},
        ]
        with patch.object(c, "_request", return_value=payload):
            entries = c.get_task_output(5, 99)
        assert len(entries) == 2
        assert entries[0]["output"] == "PLAY [all]"

    def test_non_list_returns_empty(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None):
            assert c.get_task_output(5, 99) == []


class TestTemplateWrites:
    """Create extras + the read-modify-write update (ken #1118)."""

    def test_create_sends_view_survey_and_narrow_task_params(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp('{"id": 12, "name": "x"}')
            c.create_template(
                1,
                name="x",
                playbook="x.yml",
                inventory_id=4,
                repository_id=3,
                view_id=2,
                task_params={"allow_override_limit": True},
                allow_override_args=False,
                survey_vars=[{"name": "release"}],
            )
        body = session.return_value.request.call_args.kwargs["json"]
        assert body["view_id"] == 2
        assert body["task_params"] == {"allow_override_limit": True}
        assert body["allow_override_args_in_task"] is False
        assert body["survey_vars"] == [{"name": "release"}]

    def test_get_templates_raw_keeps_unknown_fields(self) -> None:
        c = SemaphoreClient(_cfg())
        payload = [{"id": 1, "name": "deploy", "surprise": "kept"}]
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp(json.dumps(payload))
            assert c.get_templates_raw(5)[0]["surprise"] == "kept"

    def test_get_templates_raw_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp('{"oops": 1}')
            with pytest.raises(SemaphoreAPIError):
                c.get_templates_raw(5)

    def test_create_non_dict_response_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp("[]")
            with pytest.raises(SemaphoreAPIError):
                c.create_template(1, name="x", playbook="x.yml", inventory_id=4, repository_id=3)

    def test_get_template_raw_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_get_session") as session:
            session.return_value.request.return_value = _resp("[]")
            with pytest.raises(SemaphoreAPIError):
                c.get_template_raw(5, 6)


_CURRENT = {
    "id": 6,
    "project_id": 1,
    "name": "mtree",
    "playbook": "mtree.yml",
    "app": "ansible",
    "inventory_id": 4,
    "repository_id": 3,
    "environment_id": 1,
    "environment_ids": [1],
    "view_id": 2,
    "arguments": "[]",
    "allow_override_args_in_task": True,
    "task_params": {"allow_override_limit": True, "allow_debug": False},
    "survey_vars": [{"name": "release"}],
    "tasks": 17,
    "permissions": 15,
}


def _update(client: SemaphoreClient, **fields: Any) -> dict[str, Any]:
    """Run update_template against a canned GET and return the PUT body."""
    with patch.object(client, "_get_session") as session:
        session.return_value.request.side_effect = [
            _resp(json.dumps(_CURRENT)),
            _resp("{}"),
        ]
        client.update_template(1, 6, **fields)
        return session.return_value.request.call_args.kwargs["json"]  # type: ignore[no-any-return]


class TestUpdateTemplateReadModifyWrite:
    """A partial PUT used to drop app/task_params/view_id (ken #1118)."""

    def test_unpassed_fields_are_preserved(self) -> None:
        body = _update(SemaphoreClient(_cfg()), name="renamed")
        assert body["name"] == "renamed"
        assert body["app"] == "ansible"
        assert body["playbook"] == "mtree.yml"
        assert body["view_id"] == 2
        assert body["survey_vars"] == [{"name": "release"}]
        assert body["task_params"]["allow_override_limit"] is True

    def test_read_only_fields_are_not_sent_back(self) -> None:
        body = _update(SemaphoreClient(_cfg()), name="renamed")
        assert "tasks" not in body
        assert "permissions" not in body

    def test_task_params_are_merged_not_replaced(self) -> None:
        body = _update(SemaphoreClient(_cfg()), task_params={"allow_debug": True})
        assert body["task_params"] == {"allow_override_limit": True, "allow_debug": True}

    def test_none_values_are_ignored(self) -> None:
        body = _update(SemaphoreClient(_cfg()), name=None, playbook=None)
        assert body["name"] == "mtree"

    def test_environment_change_syncs_the_multi_env_list(self) -> None:
        body = _update(SemaphoreClient(_cfg()), environment_id=8)
        assert body["environment_id"] == 8
        assert body["environment_ids"] == [8]

    def test_identity_fields_are_forced(self) -> None:
        body = _update(SemaphoreClient(_cfg()), name="renamed")
        assert body["id"] == 6
        assert body["project_id"] == 1

    def test_returns_the_body_that_was_sent(self) -> None:
        client = SemaphoreClient(_cfg())
        with patch.object(client, "_get_session") as session:
            session.return_value.request.side_effect = [
                _resp(json.dumps(_CURRENT)),
                _resp("{}"),
            ]
            assert client.update_template(1, 6, name="renamed")["name"] == "renamed"
