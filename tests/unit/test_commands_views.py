"""Tests for the `sem view` command group."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.exceptions import SemaphoreAPIError
from semacli.core.models import View


def _write_cfg(tmp_path: Path) -> Path:
    path = tmp_path / "semacli.ini"
    path.write_text(textwrap.dedent("""
            [semaphore]
            url = https://sema.example
            project = 1

            [auth]
            method = bearer_token
            bearer_token = tok
            """).lstrip())
    return path


class TestViewList:
    def test_bare_group_lists_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.list_views.return_value = [
                View(id=2, project_id=1, title="Deploys", position=1),
                View(id=1, project_id=1, title="Nightly", position=0),
            ]
            r = CliRunner().invoke(main, ["view", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "Nightly" in r.output
        assert "Deploys" in r.output
        assert "Total: 2 view(s)" in r.output
        # sorted by position: Nightly (pos=0) before Deploys (pos=1)
        assert r.output.index("Nightly") < r.output.index("Deploys")

    def test_bare_group_lists_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.list_views.return_value = [
                View(id=3, project_id=1, title="Ops", position=0),
            ]
            r = CliRunner().invoke(main, ["view", "-c", str(cfg), "--json"])
        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload[0]["id"] == 3
        assert payload[0]["title"] == "Ops"

    def test_empty_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.list_views.return_value = []
            r = CliRunner().invoke(main, ["view", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "No views found" in r.output

    def test_views_alias(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.list_views.return_value = []
            r = CliRunner().invoke(main, ["views", "-c", str(cfg)])
        assert r.exit_code == 0
        Mock.return_value.list_views.assert_called_once_with(1)


class TestViewShow:
    def test_show_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.get_view.return_value = View(
                id=3, project_id=1, title="Nightly jobs", position=2
            )
            r = CliRunner().invoke(main, ["view", "-c", str(cfg), "show", "3"])
        assert r.exit_code == 0
        assert "Nightly jobs" in r.output
        assert "position:   2" in r.output
        Mock.return_value.get_view.assert_called_once_with(1, 3)

    def test_show_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.get_view.return_value = View(
                id=3, project_id=1, title="Nightly jobs", position=2
            )
            r = CliRunner().invoke(main, ["view", "-c", str(cfg), "--json", "show", "3"])
        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["title"] == "Nightly jobs"


class TestViewCreate:
    def test_create(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.create_view.return_value = View(
                id=9, project_id=1, title="New view", position=0
            )
            r = CliRunner().invoke(
                main,
                ["view", "-c", str(cfg), "create", "--title", "New view", "--position", "0"],
            )
        assert r.exit_code == 0
        assert "created view id=9" in r.output
        Mock.return_value.create_view.assert_called_once_with(1, title="New view", position=0)

    def test_create_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.create_view.return_value = View(
                id=9, project_id=1, title="New view", position=0
            )
            r = CliRunner().invoke(
                main,
                ["view", "-c", str(cfg), "--json", "create", "--title", "New view"],
            )
        assert r.exit_code == 0
        assert json.loads(r.output)["id"] == 9


class TestViewUpdate:
    def test_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            r = CliRunner().invoke(
                main,
                ["view", "-c", str(cfg), "update", "3", "--position", "1"],
            )
        assert r.exit_code == 0
        assert "updated view id=3" in r.output
        Mock.return_value.update_view.assert_called_once_with(1, 3, title=None, position=1)


class TestViewDelete:
    def test_delete_with_yes(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            r = CliRunner().invoke(main, ["view", "-c", str(cfg), "delete", "3", "--yes"])
        assert r.exit_code == 0
        assert "deleted view id=3" in r.output
        Mock.return_value.delete_view.assert_called_once_with(1, 3)

    def test_delete_declined_prompt_aborts(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            r = CliRunner().invoke(main, ["view", "-c", str(cfg), "delete", "3"], input="n\n")
        assert r.exit_code == 0
        Mock.return_value.delete_view.assert_not_called()


class TestViewErrors:
    def test_api_error_exits_4(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.views.SemaphoreClient") as Mock:
            Mock.return_value.list_views.side_effect = SemaphoreAPIError("boom")
            r = CliRunner().invoke(main, ["view", "-c", str(cfg)])
        assert r.exit_code == 4
