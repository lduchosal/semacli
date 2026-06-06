"""Tests for ``sem self-update`` (ken #746)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from semacli import __version__
from semacli.cli import main
from semacli.cli.commands.self_update import (
    _fetch_latest_version,
    _is_stable,
    _version_key,
)


def _pypi_json(latest: str, all_versions: list[str] | None = None) -> dict[str, Any]:
    """Shape of the response from ``GET /pypi/semacli/json``."""
    releases = {v: [{"filename": "x"}] for v in (all_versions or [latest])}
    return {"info": {"version": latest}, "releases": releases}


def _runner_invoke(args: list[str]) -> Any:
    return CliRunner().invoke(main, args)


# ── helpers ───────────────────────────────────────────────────────────────
class TestStableFilter:
    def test_plain_version_is_stable(self) -> None:
        assert _is_stable("1.2.3")

    @pytest.mark.parametrize("v", ["1.2.0a1", "1.2.0b2", "1.2.0rc1", "1.2.0.dev3"])
    def test_pre_release_is_unstable(self, v: str) -> None:
        assert not _is_stable(v)

    def test_version_key_orders_numerically(self) -> None:
        assert _version_key("0.5.7") > _version_key("0.5.6")
        assert _version_key("0.6.0") > _version_key("0.5.99")


# ── _fetch_latest_version ─────────────────────────────────────────────────
class TestFetchLatest:
    def test_stable_path_picks_highest_stable(self) -> None:
        payload = _pypi_json(latest="0.6.0a1", all_versions=["0.5.7", "0.5.8", "0.6.0a1"])
        with patch("semacli.cli.commands.self_update.requests.get") as Mock:
            Mock.return_value.json.return_value = payload
            Mock.return_value.raise_for_status.return_value = None
            assert _fetch_latest_version(allow_pre=False) == "0.5.8"

    def test_pre_path_uses_info_version(self) -> None:
        payload = _pypi_json(latest="0.6.0a1", all_versions=["0.5.7", "0.6.0a1"])
        with patch("semacli.cli.commands.self_update.requests.get") as Mock:
            Mock.return_value.json.return_value = payload
            Mock.return_value.raise_for_status.return_value = None
            assert _fetch_latest_version(allow_pre=True) == "0.6.0a1"

    def test_fallback_to_info_when_no_stable(self) -> None:
        payload = _pypi_json(latest="0.6.0a1", all_versions=["0.6.0a1"])
        with patch("semacli.cli.commands.self_update.requests.get") as Mock:
            Mock.return_value.json.return_value = payload
            Mock.return_value.raise_for_status.return_value = None
            assert _fetch_latest_version(allow_pre=False) == "0.6.0a1"

    def test_network_failure_raises(self) -> None:
        import requests as r

        with patch(
            "semacli.cli.commands.self_update.requests.get",
            side_effect=r.exceptions.ConnectionError("nx"),
        ):
            with pytest.raises(RuntimeError):
                _fetch_latest_version(allow_pre=False)


# ── CLI invocation ────────────────────────────────────────────────────────
class TestCliAlreadyUpToDate:
    def test_zero_exit_when_versions_match(self) -> None:
        with patch(
            "semacli.cli.commands.self_update._fetch_latest_version",
            return_value=__version__,
        ):
            result = _runner_invoke(["self-update"])
        assert result.exit_code == 0
        assert "Already up to date" in result.output


class TestCliCheckMode:
    def test_check_only_zero_when_up_to_date(self) -> None:
        with patch(
            "semacli.cli.commands.self_update._fetch_latest_version",
            return_value=__version__,
        ):
            result = _runner_invoke(["self-update", "--check"])
        assert result.exit_code == 0

    def test_check_only_one_when_upgrade_available(self) -> None:
        with patch(
            "semacli.cli.commands.self_update._fetch_latest_version",
            return_value="99.99.99",
        ):
            result = _runner_invoke(["self-update", "--check"])
        assert result.exit_code == 1
        assert "Upgrade available" in result.output


class TestCliDryRun:
    def test_dry_run_prints_pip_command_no_subprocess(self) -> None:
        with (
            patch(
                "semacli.cli.commands.self_update._fetch_latest_version",
                return_value="99.99.99",
            ),
            patch("semacli.cli.commands.self_update.subprocess.run") as run_mock,
        ):
            result = _runner_invoke(["self-update", "--dry-run"])
        assert result.exit_code == 0
        assert "pip install --upgrade semacli" in result.output
        assert "--dry-run: pip not executed" in result.output
        run_mock.assert_not_called()


class TestCliUpgrade:
    def test_runs_pip_when_upgrade_available(self) -> None:
        run_mock = MagicMock(returncode=0)
        with (
            patch(
                "semacli.cli.commands.self_update._fetch_latest_version",
                return_value="99.99.99",
            ),
            patch(
                "semacli.cli.commands.self_update.subprocess.run",
                return_value=run_mock,
            ) as run_patch,
        ):
            result = _runner_invoke(["self-update"])
        assert result.exit_code == 0
        assert "Done" in result.output
        # Called with the current interpreter, not bare `pip`.
        args, _ = run_patch.call_args
        cmd = args[0]
        assert cmd[1:5] == ["-m", "pip", "install", "--upgrade"]
        assert cmd[5] == "semacli"
        assert "--pre" not in cmd

    def test_pre_flag_passes_pre_to_pip(self) -> None:
        run_mock = MagicMock(returncode=0)
        with (
            patch(
                "semacli.cli.commands.self_update._fetch_latest_version",
                return_value="99.99.99a1",
            ),
            patch(
                "semacli.cli.commands.self_update.subprocess.run",
                return_value=run_mock,
            ) as run_patch,
        ):
            result = _runner_invoke(["self-update", "--pre"])
        assert result.exit_code == 0
        cmd = run_patch.call_args.args[0]
        assert "--pre" in cmd

    def test_pip_failure_exits_one(self) -> None:
        run_mock = MagicMock(returncode=1)
        with (
            patch(
                "semacli.cli.commands.self_update._fetch_latest_version",
                return_value="99.99.99",
            ),
            patch(
                "semacli.cli.commands.self_update.subprocess.run",
                return_value=run_mock,
            ),
        ):
            result = _runner_invoke(["self-update"])
        assert result.exit_code == 1
        assert "pip exited" in result.output


class TestCliPypiUnreachable:
    def test_network_error_exits_two(self) -> None:
        with patch(
            "semacli.cli.commands.self_update._fetch_latest_version",
            side_effect=RuntimeError("could not reach PyPI: timed out"),
        ):
            result = _runner_invoke(["self-update"])
        assert result.exit_code == 2
        assert "could not reach PyPI" in result.output
