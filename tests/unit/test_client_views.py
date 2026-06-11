"""Tests for the views client mixin (board views CRUD)."""

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


class TestViewsClient:
    def test_list(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value=[{"id": 1, "title": "Deploys", "position": 0}]
        ) as req:
            views = c.list_views(5)
        assert views[0].title == "Deploys"
        assert req.call_args.args[0] == "project/5/views"

    def test_list_non_list_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"x": 1}):
            with pytest.raises(SemaphoreAPIError):
                c.list_views(5)

    def test_get(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(
            c, "_request", return_value={"id": 7, "title": "Deploys", "position": 2}
        ) as req:
            view = c.get_view(5, 7)
        assert view.id == 7
        assert view.position == 2
        assert req.call_args.args[0] == "project/5/views/7"

    def test_get_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.get_view(5, 7)

    def test_create_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value={"id": 7, "title": "Deploys"}) as req:
            view = c.create_view(5, "Deploys", position=3)
        assert view.title == "Deploys"
        body = req.call_args.kwargs["body"]
        assert body == {"project_id": 5, "title": "Deploys", "position": 3}
        assert req.call_args.args[0] == "project/5/views"
        assert req.call_args.kwargs["method"] == "POST"

    def test_create_non_dict_raises(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=[]):
            with pytest.raises(SemaphoreAPIError):
                c.create_view(5, "Deploys")

    def test_update_body(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.update_view(5, 7, title="Renamed", position=None)
        body = req.call_args.kwargs["body"]
        assert body == {"title": "Renamed", "id": 7, "project_id": 5}
        assert req.call_args.args[0] == "project/5/views/7"
        assert req.call_args.kwargs["method"] == "PUT"

    def test_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.delete_view(5, 7)
        req.assert_called_once_with("project/5/views/7", method="DELETE")
