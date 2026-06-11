"""Tests for the `sem init` interactive wizard."""

import stat
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from semacli.cli import main
from semacli.cli.commands.init import (
    _check_token,
    _confirm_overwrite,
    _normalize_url,
    _ping_with,
    _prompt_location,
    _prompt_project,
    _prompt_token,
    _prompt_url,
    _write_ini,
)
from semacli.core.config import SemaphoreConfig
from semacli.core.exceptions import AuthenticationError, SemaCliError
from semacli.core.models import Project


def _cfg(url: str = "https://sema.example") -> SemaphoreConfig:
    return SemaphoreConfig(url=url, bearer_token="tok", verify_ssl=True, allow_http=False)


class TestNormalizeUrl:
    def test_adds_https_scheme(self) -> None:
        assert _normalize_url("sema.example") == "https://sema.example"

    def test_strips_trailing_slash_and_whitespace(self) -> None:
        assert _normalize_url("  https://sema.example/  ") == "https://sema.example"

    def test_preserves_http_scheme(self) -> None:
        assert _normalize_url("http://sema.example") == "http://sema.example"


class TestPingWith:
    def test_success_returns_none(self) -> None:
        with patch("semacli.cli.commands.init.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            assert _ping_with(_cfg()) is None

    def test_failure_returns_message(self) -> None:
        with patch("semacli.cli.commands.init.SemaphoreClient") as Mock:
            Mock.return_value.ping.side_effect = ConnectionError("no route")
            assert _ping_with(_cfg()) == "no route"


class TestCheckToken:
    def test_success_returns_project_count(self) -> None:
        with patch("semacli.cli.commands.init.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = [
                Project(id=1, name="alpha"),
                Project(id=2, name="beta"),
            ]
            assert _check_token(_cfg()) == (2, None)

    def test_authentication_error(self) -> None:
        with patch("semacli.cli.commands.init.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.side_effect = AuthenticationError("401")
            count, err = _check_token(_cfg())
        assert count is None
        assert err is not None
        assert "token refused by server" in err

    def test_generic_error(self) -> None:
        with patch("semacli.cli.commands.init.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.side_effect = RuntimeError("boom")
            assert _check_token(_cfg()) == (None, "boom")


class TestConfirmOverwrite:
    def test_missing_target_is_noop(self, tmp_path: Path) -> None:
        _confirm_overwrite(tmp_path / "absent.ini")

    def test_existing_confirmed(self, tmp_path: Path) -> None:
        target = tmp_path / "semacli.ini"
        target.write_text("old")
        with patch("semacli.cli.commands.init.click.confirm", return_value=True):
            _confirm_overwrite(target)

    def test_existing_declined_aborts(self, tmp_path: Path) -> None:
        target = tmp_path / "semacli.ini"
        target.write_text("old")
        with (
            patch("semacli.cli.commands.init.click.confirm", return_value=False),
            pytest.raises(click.Abort),
        ):
            _confirm_overwrite(target)


class TestWriteIni:
    def test_full_content_and_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "semacli.ini"
        _write_ini(
            target,
            url="http://sema.example",
            token="tok",
            verify_ssl=False,
            allow_http=True,
            project=7,
        )
        content = target.read_text(encoding="utf-8")
        assert "[semaphore]" in content
        assert "url = http://sema.example" in content
        assert "project = 7" in content
        assert "[auth]" in content
        assert "bearer_token = tok" in content
        assert "[settings]" in content
        assert "verify_ssl = false" in content
        assert "allow_http = true" in content
        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_minimal_omits_settings_and_project(self, tmp_path: Path) -> None:
        target = tmp_path / "semacli.ini"
        _write_ini(
            target,
            url="https://sema.example",
            token="tok",
            verify_ssl=True,
            allow_http=False,
            project=None,
        )
        content = target.read_text(encoding="utf-8")
        assert "[settings]" not in content
        assert "project =" not in content


class TestPromptUrl:
    def test_https_happy_path(self) -> None:
        with (
            patch("semacli.cli.commands.init.click.prompt", return_value="sema.example"),
            patch("semacli.cli.commands.init.click.confirm", return_value=True),
            patch("semacli.cli.commands.init._ping_with", return_value=None),
        ):
            assert _prompt_url() == ("https://sema.example", True, False)

    def test_http_confirmed(self) -> None:
        with (
            patch(
                "semacli.cli.commands.init.click.prompt",
                return_value="http://sema.example",
            ),
            patch("semacli.cli.commands.init.click.confirm", return_value=True),
            patch("semacli.cli.commands.init._ping_with", return_value=None),
        ):
            assert _prompt_url() == ("http://sema.example", True, True)

    def test_ping_failure_declined_aborts(self) -> None:
        with (
            patch("semacli.cli.commands.init.click.prompt", return_value="sema.example"),
            patch(
                "semacli.cli.commands.init.click.confirm",
                side_effect=[True, False],  # verify TLS, then "try another URL?" -> no
            ),
            patch("semacli.cli.commands.init._ping_with", return_value="no route"),
            pytest.raises(click.Abort),
        ):
            _prompt_url()


class TestPromptToken:
    def test_happy_path(self) -> None:
        with (
            patch("semacli.cli.commands.init.click.prompt", return_value="tok"),
            patch("semacli.cli.commands.init._check_token", return_value=(3, None)),
        ):
            assert _prompt_token("https://sema.example", True, False) == "tok"

    def test_refused_then_declined_aborts(self) -> None:
        with (
            patch("semacli.cli.commands.init.click.prompt", return_value="tok"),
            patch(
                "semacli.cli.commands.init._check_token",
                return_value=(None, "token refused by server: 401"),
            ),
            patch("semacli.cli.commands.init.click.confirm", return_value=False),
            pytest.raises(click.Abort),
        ):
            _prompt_token("https://sema.example", True, False)


class TestPromptProject:
    def _projects(self) -> list[Project]:
        return [Project(id=1, name="alpha"), Project(id=2, name="beta")]

    def test_no_projects_returns_none(self) -> None:
        with patch("semacli.cli.commands.init.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = []
            assert _prompt_project(_cfg()) is None

    def test_digit_input_returns_id(self) -> None:
        with (
            patch("semacli.cli.commands.init.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.init.click.prompt", return_value="2"),
        ):
            Mock.return_value.get_projects.return_value = self._projects()
            assert _prompt_project(_cfg()) == 2

    def test_name_match_returns_id(self) -> None:
        with (
            patch("semacli.cli.commands.init.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.init.click.prompt", return_value="ALPHA"),
        ):
            Mock.return_value.get_projects.return_value = self._projects()
            assert _prompt_project(_cfg()) == 1

    def test_blank_skips(self) -> None:
        with (
            patch("semacli.cli.commands.init.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.init.click.prompt", return_value="  "),
        ):
            Mock.return_value.get_projects.return_value = self._projects()
            assert _prompt_project(_cfg()) is None

    def test_no_match_skips(self) -> None:
        with (
            patch("semacli.cli.commands.init.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.init.click.prompt", return_value="gamma"),
        ):
            Mock.return_value.get_projects.return_value = self._projects()
            assert _prompt_project(_cfg()) is None

    def test_ambiguous_skips(self) -> None:
        with (
            patch("semacli.cli.commands.init.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.init.click.prompt", return_value="a"),
        ):
            Mock.return_value.get_projects.return_value = self._projects()
            assert _prompt_project(_cfg()) is None


class TestPromptLocation:
    def test_home_choice(self) -> None:
        with patch("semacli.cli.commands.init.click.prompt", return_value="2"):
            assert _prompt_location() == Path.home() / ".semacli.ini"

    def test_default_is_current_directory(self) -> None:
        with patch("semacli.cli.commands.init.click.prompt", return_value="1"):
            assert _prompt_location() == Path("./semacli.ini")


class TestInitCmd:
    def test_happy_path_with_url_and_output(self, tmp_path: Path) -> None:
        target = tmp_path / "semacli.ini"
        with patch("semacli.cli.commands.init.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = [Project(id=1, name="alpha")]
            result = CliRunner().invoke(
                main,
                ["init", "--url", "https://sema.example", "--output", str(target)],
                input="tok\n1\n",
            )
        assert result.exit_code == 0
        assert f"wrote {target}" in result.output
        content = target.read_text(encoding="utf-8")
        assert "url = https://sema.example" in content
        assert "project = 1" in content
        assert "bearer_token = tok" in content
        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_semacli_error_exits_2(self, tmp_path: Path) -> None:
        target = tmp_path / "semacli.ini"
        with patch("semacli.cli.commands.init.SemaphoreClient") as Mock:
            # token check succeeds, then project listing blows up
            Mock.return_value.get_projects.side_effect = [
                [Project(id=1, name="alpha")],
                SemaCliError("server went away"),
            ]
            result = CliRunner().invoke(
                main,
                ["init", "--url", "https://sema.example", "--output", str(target)],
                input="tok\n",
            )
        assert result.exit_code == 2
        assert "error: server went away" in result.output
        assert not target.exists()
