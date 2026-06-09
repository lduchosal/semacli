"""End-to-end tests for `sem run` interaction with `[hook]`."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.models import Task


def _write_cfg(tmp_path: Path, hook_lines: str = "") -> Path:
    path = tmp_path / "semacli.ini"
    path.write_text(textwrap.dedent(f"""
            [semaphore]
            url = https://sema.example
            project = 1

            [auth]
            method = bearer_token
            bearer_token = tok

            [hook]
            {hook_lines}
            """).lstrip())
    return path


def _write_hook(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body).lstrip())
    os.chmod(path, 0o755)
    return path


def _invoke(args: list[str]) -> object:
    return CliRunner().invoke(main, args)


class TestRunPrehook:
    def test_prehook_fires_before_run_task(self, tmp_path: Path) -> None:
        marker = tmp_path / "ran"
        hook = _write_hook(
            tmp_path,
            "pre.sh",
            f"#!/bin/sh\ntouch {marker}\nexit 0\n",
        )
        cfg = _write_cfg(tmp_path, f"task_run_prehook = {hook}")
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "-c", str(cfg)])
        assert r.exit_code == 0
        assert marker.exists()

    def test_prehook_failure_aborts_with_exit_6(self, tmp_path: Path) -> None:
        hook = _write_hook(tmp_path, "bad.sh", "#!/bin/sh\necho bad >&2\nexit 9\n")
        cfg = _write_cfg(tmp_path, f"task_run_prehook = {hook}")
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "-c", str(cfg)])
        assert r.exit_code == 6
        # run_task must NOT have been called when the prehook aborted.
        Mock.return_value.run_task.assert_not_called()

    def test_no_hooks_flag_bypasses_prehook(self, tmp_path: Path) -> None:
        marker = tmp_path / "ran"
        hook = _write_hook(
            tmp_path,
            "pre.sh",
            f"#!/bin/sh\ntouch {marker}\nexit 9\n",
        )
        cfg = _write_cfg(tmp_path, f"task_run_prehook = {hook}")
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "--no-hooks", "-c", str(cfg)])
        assert r.exit_code == 0
        assert not marker.exists()

    def test_prehook_receives_template_and_limit_env(self, tmp_path: Path) -> None:
        captured = tmp_path / "env.out"
        hook = _write_hook(
            tmp_path,
            "envcap.sh",
            f"""
            #!/bin/sh
            echo "$SEMACLI_TEMPLATE|$SEMACLI_LIMIT|$SEMACLI_PROJECT" > {captured}
            exit 0
            """,
        )
        cfg = _write_cfg(tmp_path, f"task_run_prehook = {hook}")
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "--limit", "ans2", "-c", str(cfg)])
        assert r.exit_code == 0
        assert captured.read_text().strip() == "mtree|ans2|1"


class TestRunPostHook:
    def test_posthook_receives_task_id_and_status(self, tmp_path: Path) -> None:
        captured = tmp_path / "post.out"
        hook = _write_hook(
            tmp_path,
            "post.sh",
            f"""
            #!/bin/sh
            echo "$SEMACLI_TASK_ID|$SEMACLI_STATUS" > {captured}
            exit 0
            """,
        )
        cfg = _write_cfg(tmp_path, f"task_run_posthook = {hook}")
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "-c", str(cfg)])
        assert r.exit_code == 0
        assert captured.read_text().strip() == "99|success"

    def test_failhook_fires_only_on_failure(self, tmp_path: Path) -> None:
        marker = tmp_path / "failed"
        hook = _write_hook(
            tmp_path,
            "fail.sh",
            f"#!/bin/sh\ntouch {marker}\nexit 0\n",
        )
        cfg = _write_cfg(tmp_path, f"task_run_failhook = {hook}")
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "-c", str(cfg)])
        assert r.exit_code == 0
        assert not marker.exists()

    def test_failhook_fires_when_task_fails(self, tmp_path: Path) -> None:
        marker = tmp_path / "failed"
        hook = _write_hook(
            tmp_path,
            "fail.sh",
            f"#!/bin/sh\ntouch {marker}\nexit 0\n",
        )
        cfg = _write_cfg(tmp_path, f"task_run_failhook = {hook}")
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="error"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "-c", str(cfg)])
        assert r.exit_code == 1  # run failed → exit 1, not 6
        assert marker.exists()

    def test_posthook_failure_does_not_block_command(self, tmp_path: Path) -> None:
        hook = _write_hook(tmp_path, "bad.sh", "#!/bin/sh\nexit 7\n")
        cfg = _write_cfg(tmp_path, f"task_run_posthook = {hook}")
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "-c", str(cfg)])
        # posthook failure is a warning, not a fatal error
        assert r.exit_code == 0
        assert "warning" in r.output.lower()
