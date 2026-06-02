"""Smoke tests for the CLI entrypoint and command registration."""

import runpy

from click.testing import CliRunner

from semacli import __version__
from semacli.cli import main


class TestRootCli:
    def test_version_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Semaphore CLI" in result.output
        assert "ping" in result.output
        assert "projects" in result.output

    def test_subcommands_registered(self) -> None:
        assert "ping" in main.commands
        assert "projects" in main.commands


class TestMainModule:
    def test_run_as_module(self) -> None:
        # `python -m semacli` should reach the click group without crashing.
        # We invoke __main__ with sys.argv=[--help] equivalent via runpy.
        try:
            runpy.run_module("semacli", run_name="__main__", alter_sys=True)
        except SystemExit as e:
            # click exits with 0 on --help, but here no args → exits 2 (missing cmd)
            assert e.code in (0, 2)
