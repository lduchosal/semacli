"""Tests for the templates + tasks CLI commands."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.models import Task, Template


def _write_cfg(tmp_path: Path, project: int | None = 1) -> Path:
    path = tmp_path / "semacli.ini"
    project_line = f"project = {project}" if project is not None else ""
    path.write_text(
        textwrap.dedent(
            f"""
            [semaphore]
            url = https://sema.example
            {project_line}

            [auth]
            method = bearer_token
            bearer_token = tok
            """
        ).lstrip()
    )
    return path


class TestTemplatesList:
    def test_default_lists(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = [
                Template(id=1, project_id=1, name="deploy", playbook="site.yml"),
                Template(id=2, project_id=1, name="backup"),
            ]
            result = CliRunner().invoke(main, ["templates", "-c", str(cfg)])
        assert result.exit_code == 0
        assert "deploy" in result.output
        assert "Total: 2" in result.output

    def test_empty(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = []
            result = CliRunner().invoke(main, ["templates", "-c", str(cfg)])
        assert "No templates" in result.output

    def test_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = [
                Template(id=1, project_id=1, name="deploy"),
            ]
            result = CliRunner().invoke(
                main, ["templates", "-c", str(cfg), "--json"]
            )
        payload = json.loads(result.output)
        assert payload[0]["id"] == 1

    def test_missing_project_in_config(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path, project=None)
        result = CliRunner().invoke(main, ["templates", "-c", str(cfg)])
        assert result.exit_code == 2
        assert "Project id required" in result.output

    def test_project_override(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path, project=None)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = []
            result = CliRunner().invoke(
                main, ["templates", "-c", str(cfg), "-p", "9"]
            )
        assert result.exit_code == 0
        Mock.return_value.get_templates.assert_called_with(9)


class TestTemplatesShow:
    def test_show_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.get_template.return_value = Template(
                id=7,
                project_id=1,
                name="deploy",
                playbook="site.yml",
                inventory_id=3,
                description="prod",
            )
            result = CliRunner().invoke(
                main, ["templates", "-c", str(cfg), "show", "7"]
            )
        assert result.exit_code == 0
        assert "playbook:" in result.output
        assert "site.yml" in result.output
        assert "prod" in result.output

    def test_show_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.get_template.return_value = Template(
                id=7, project_id=1, name="deploy"
            )
            result = CliRunner().invoke(
                main, ["templates", "-c", str(cfg), "--json", "show", "7"]
            )
        assert json.loads(result.output)["id"] == 7


class TestTasksRun:
    def test_minimal(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.run_task.return_value = Task(
                id=99, template_id=10, status="waiting"
            )
            result = CliRunner().invoke(
                main, ["tasks", "-c", str(cfg), "run", "10"]
            )
        assert result.exit_code == 0
        assert "id:" in result.output
        assert "99" in result.output
        Mock.return_value.run_task.assert_called_once_with(
            1, 10,
            playbook=None,
            environment=None,
            limit=None,
            debug=False,
            dry_run=False,
        )

    def test_with_limit_and_flags(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.run_task.return_value = Task(id=1, template_id=10)
            CliRunner().invoke(
                main,
                [
                    "tasks", "-c", str(cfg), "run", "10",
                    "--limit", "ans1",
                    "--debug",
                    "--dry-run",
                ],
            )
        Mock.return_value.run_task.assert_called_with(
            1, 10,
            playbook=None,
            environment=None,
            limit="ans1",
            debug=True,
            dry_run=True,
        )


class TestTasksShow:
    def test_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.get_task.return_value = Task(
                id=99, template_id=10, status="success", created="t1", end="t2"
            )
            result = CliRunner().invoke(
                main, ["tasks", "-c", str(cfg), "show", "99"]
            )
        assert result.exit_code == 0
        assert "status:      success" in result.output


class TestTasksOutput:
    def test_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.get_task_output.return_value = [
                {"output": "PLAY [all]"},
                {"output": "TASK [ping]"},
            ]
            result = CliRunner().invoke(
                main, ["tasks", "-c", str(cfg), "output", "99"]
            )
        assert "PLAY [all]" in result.output
        assert "TASK [ping]" in result.output

    def test_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.get_task_output.return_value = [{"output": "x"}]
            result = CliRunner().invoke(
                main, ["tasks", "-c", str(cfg), "--json", "output", "99"]
            )
        assert json.loads(result.output) == [{"output": "x"}]


class TestTasksWatch:
    def test_polls_until_final(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock, patch(
            "semacli.cli.commands.tasks.time.sleep"
        ):
            client = Mock.return_value
            # Two polling rounds: first running, second success.
            client.get_task_output.side_effect = [
                [{"output": "starting"}],
                [{"output": "starting"}, {"output": "done"}],
            ]
            client.get_task.side_effect = [
                Task(id=99, template_id=10, status="running"),
                Task(id=99, template_id=10, status="success"),
            ]
            result = CliRunner().invoke(
                main, ["tasks", "-c", str(cfg), "watch", "99", "--interval", "0"]
            )
        assert result.exit_code == 0
        assert "starting" in result.output
        assert "done" in result.output
