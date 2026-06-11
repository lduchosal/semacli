"""Fail-closed override guard on `sem run` / `sem task run` (ken #827).

Semaphore silently drops per-run overrides the template forbids — a
refused --limit runs the playbook on the FULL inventory. semacli must
refuse to post the task instead.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.models import Task, Template, TemplateTaskParams

_RESTRICTIVE = Template(id=5, name="mtree")  # server default: all toggles false
_PERMISSIVE = Template(
    id=5,
    name="mtree",
    task_params=TemplateTaskParams(
        allow_debug=True,
        allow_override_inventory=True,
        allow_override_limit=True,
        allow_override_skip_tags=True,
        allow_override_tags=True,
    ),
)


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


class TestRunGuard:
    def test_limit_on_restrictive_template_refused(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
        ):
            Mock.return_value.get_template.return_value = _RESTRICTIVE
            r = CliRunner().invoke(main, ["run", "mtree", "-c", str(cfg), "--limit", "web1"])
        assert r.exit_code == 2
        assert "allow_override_limit" in r.output
        assert "FULL inventory" in r.output
        Mock.return_value.run_task.assert_not_called()

    def test_limit_on_permissive_template_runs(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.get_template.return_value = _PERMISSIVE
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = CliRunner().invoke(main, ["run", "mtree", "-c", str(cfg), "--limit", "web1"])
        assert r.exit_code == 0
        Mock.return_value.run_task.assert_called_once()

    def test_no_flags_skips_template_fetch(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = CliRunner().invoke(main, ["run", "mtree", "-c", str(cfg)])
        assert r.exit_code == 0
        Mock.return_value.get_template.assert_not_called()

    def test_debug_on_restrictive_template_refused(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
        ):
            Mock.return_value.get_template.return_value = _RESTRICTIVE
            r = CliRunner().invoke(main, ["run", "mtree", "-c", str(cfg), "--debug", "2"])
        assert r.exit_code == 2
        assert "allow_debug" in r.output
        Mock.return_value.run_task.assert_not_called()


class TestTaskRunGuard:
    def test_limit_on_restrictive_template_refused(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            Mock.return_value.get_template.return_value = _RESTRICTIVE
            r = CliRunner().invoke(main, ["task", "-c", str(cfg), "run", "5", "--limit", "web1"])
        assert r.exit_code == 2
        assert "allow_override_limit" in r.output
        Mock.return_value.run_task.assert_not_called()

    def test_tags_on_permissive_template_runs(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            Mock.return_value.get_template.return_value = _PERMISSIVE
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = CliRunner().invoke(main, ["task", "-c", str(cfg), "run", "5", "--tags", "ntp"])
        assert r.exit_code == 0
        Mock.return_value.run_task.assert_called_once()

    def test_no_flags_skips_template_fetch(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = CliRunner().invoke(main, ["task", "-c", str(cfg), "run", "5"])
        assert r.exit_code == 0
        Mock.return_value.get_template.assert_not_called()
