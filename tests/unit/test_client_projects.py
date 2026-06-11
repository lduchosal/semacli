"""Tests for the projects client mixin (projects, members, events, backup)."""

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


class TestProjectsClient:
    def test_get_projects(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value=[{"id": 1, "name": "infra"}, {"id": 2, "name": "web"}]
        ) as req:
            projects = c.get_projects()
        assert [p.name for p in projects] == ["infra", "web"]
        assert req.call_args.args[0] == "projects"

    def test_get_projects_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.get_projects()

    def test_get_project(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 5, "name": "infra"}) as req:
            project = c.get_project(5)
        assert project.id == 5
        assert req.call_args.args[0] == "project/5"

    def test_get_project_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.get_project(5)

    def test_create_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 5, "name": "infra"}) as req:
            project = c.create_project("infra", alert=True, alert_chat="ops", max_parallel_tasks=4)
        assert project.name == "infra"
        body = req.call_args.kwargs["body"]
        assert body == {
            "name": "infra",
            "alert": True,
            "alert_chat": "ops",
            "max_parallel_tasks": 4,
        }
        assert req.call_args.kwargs["method"] == "POST"

    def test_create_minimal_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 5}) as req:
            c.create_project("infra")
        assert req.call_args.kwargs["body"] == {"name": "infra", "alert": False}

    def test_create_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.create_project("infra")

    def test_update_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_project(5, name="renamed", alert_chat=None)
        body = req.call_args.kwargs["body"]
        assert body == {"name": "renamed", "id": 5}
        assert req.call_args.args[0] == "project/5"
        assert req.call_args.kwargs["method"] == "PUT"

    def test_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.delete_project(5)
        req.assert_called_once_with("project/5", method="DELETE")


class TestProjectMembersClient:
    def test_list(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value=[{"user_id": 2, "role": "owner", "username": "luc"}]
        ) as req:
            members = c.list_project_members(5)
        assert members[0].role == "owner"
        assert req.call_args.args[0] == "project/5/users"

    def test_list_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.list_project_members(5)

    def test_add(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.add_project_member(5, 2, "manager")
        req.assert_called_once_with(
            "project/5/users",
            method="POST",
            body={"user_id": 2, "role": "manager", "project_id": 5},
        )

    def test_update(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_project_member(5, 2, "guest")
        req.assert_called_once_with(
            "project/5/users/2",
            method="PUT",
            body={"user_id": 2, "role": "guest", "project_id": 5},
        )

    def test_remove(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.remove_project_member(5, 2)
        req.assert_called_once_with("project/5/users/2", method="DELETE")


class TestProjectEventsClient:
    def test_list(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c,
            "_request",
            return_value=[{"user_id": 2, "object_type": "task", "description": "ran"}],
        ) as req:
            events = c.list_project_events(5)
        assert events[0].description == "ran"
        assert req.call_args.args[0] == "project/5/events"

    def test_list_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.list_project_events(5)


class TestProjectBackupClient:
    def test_export(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"meta": {"name": "infra"}}) as req:
            backup = c.export_project_backup(5)
        assert backup == {"meta": {"name": "infra"}}
        assert req.call_args.args[0] == "project/5/backup"

    def test_export_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.export_project_backup(5)
