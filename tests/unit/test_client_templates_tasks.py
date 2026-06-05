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
                debug=True,
                dry_run=True,
            )
        body = req.call_args.kwargs["body"]
        assert body == {
            "template_id": 10,
            "playbook": "custom.yml",
            "environment": '{"k": "v"}',
            "limit": "ans1",
            "debug": True,
            "dry_run": True,
        }

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
