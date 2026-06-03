"""Tests for the ping + projects CLI commands."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.exceptions import ConfigurationError
from semacli.core.models import Project


def _write_cfg(tmp_path: Path) -> Path:
    path = tmp_path / "semacli.ini"
    path.write_text(textwrap.dedent("""
            [semaphore]
            url = https://sema.example

            [auth]
            method = bearer_token
            bearer_token = tok
            """).lstrip())
    return path


class TestPingCommand:
    def test_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            result = CliRunner().invoke(main, ["ping", "-c", str(cfg)])
        assert result.exit_code == 0
        assert "pong" in result.output

    def test_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            result = CliRunner().invoke(main, ["ping", "-c", str(cfg), "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["ping"] == "pong"

    def test_quiet(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            result = CliRunner().invoke(main, ["ping", "-c", str(cfg), "-q"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_missing_config_exits_2(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(main, ["ping", "-c", str(tmp_path / "absent.ini")])
        assert result.exit_code == 2
        assert "Configuration error" in result.output

    def test_propagates_internal_error(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.side_effect = ConfigurationError("boom")
            result = CliRunner().invoke(main, ["ping", "-c", str(cfg)])
        assert result.exit_code == 2


class TestProjectsCommand:
    def test_text_with_projects(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = [
                Project(id=1, name="alpha"),
                Project(id=2, name="beta"),
            ]
            result = CliRunner().invoke(main, ["projects", "-c", str(cfg)])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output
        assert "Total: 2" in result.output

    def test_text_empty(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = []
            result = CliRunner().invoke(main, ["projects", "-c", str(cfg)])
        assert result.exit_code == 0
        assert "No projects found" in result.output

    def test_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = [
                Project(id=1, name="alpha", created="c"),
            ]
            result = CliRunner().invoke(main, ["projects", "-c", str(cfg), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload == [{"id": 1, "name": "alpha", "created": "c"}]

    def test_quiet(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = []
            result = CliRunner().invoke(main, ["projects", "-c", str(cfg), "-q"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_verbose(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = []
            result = CliRunner().invoke(main, ["projects", "-c", str(cfg), "-v"])
        assert result.exit_code == 0
        # OutputFormatter.format_verbose writes to stderr — Click mixes stderr
        # into output by default in CliRunner.
