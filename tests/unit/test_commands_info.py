"""Tests for the `sem info` command."""

import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.models import ApiInfo


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


class TestInfo:
    def test_text_output(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.info.SemaphoreClient") as mock:
            mock.return_value.get_info.return_value = ApiInfo(version="2.16.31")
            r = CliRunner().invoke(main, ["info", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "version: 2.16.31" in r.output

    def test_json_output(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.info.SemaphoreClient") as mock:
            mock.return_value.get_info.return_value = ApiInfo(version="2.16.31")
            r = CliRunner().invoke(main, ["info", "--json", "-c", str(cfg)])
        assert r.exit_code == 0
        assert '"version": "2.16.31"' in r.output

    def test_quiet_suppresses_output(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.info.SemaphoreClient") as mock:
            mock.return_value.get_info.return_value = ApiInfo(version="2.16.31")
            r = CliRunner().invoke(main, ["info", "-q", "-c", str(cfg)])
        assert r.exit_code == 0
        assert r.output == ""
