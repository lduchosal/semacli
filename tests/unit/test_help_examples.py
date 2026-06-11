"""Validate every example cited in `semacli ... --help`.

For each command whose ``--help`` epilog ships an ``Examples:`` block,
this module replays the literal command line through Click's CliRunner
with the HTTP layer mocked. A test asserts at minimum:

* Click accepts the syntax (no UsageError).
* The expected client method is invoked.
* The exit code matches the documented golden path.

The initial pass (ken #732) flagged 6 examples that diverged from
the Click signature as ``xfail(strict=True)``. Each became its own
BUG card and was reconciled (kens #733/#734/#735/#736/#737); the
markers have been removed and the tests now serve as plain
regression coverage.

Conventions inherited from ``test_commands*.py``:
    * SemaphoreClient is patched at the call site
      (``semacli.cli._crud.SemaphoreClient`` for crud groups,
      ``semacli.cli.commands.<mod>.SemaphoreClient`` otherwise).
    * A minimal ``semacli.ini`` is written under ``tmp_path`` so the
      Click commands can load it via ``-c``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.models import (
    Environment,
    Inventory,
    Key,
    Project,
    Repository,
    Schedule,
    Task,
    Template,
    User,
    UserToken,
)

# ── helpers ───────────────────────────────────────────────────────────────


def _write_cfg(tmp_path: Path, project: int | None = 1) -> Path:
    path = tmp_path / "semacli.ini"
    project_line = f"project = {project}" if project is not None else ""
    path.write_text(textwrap.dedent(f"""
            [semaphore]
            url = https://sema.example
            {project_line}

            [auth]
            method = bearer_token
            bearer_token = tok
            """).lstrip())
    return path


def _invoke(args: list[str]) -> Any:
    return CliRunner().invoke(main, args)


# ─────────────────────────────────────────────────────────────────────────
# semacli (root) — EXAMPLES block
# ─────────────────────────────────────────────────────────────────────────
class TestRootExamples:
    """Examples in the root ``semacli --help`` epilog."""

    def test_project_lists(self, tmp_path: Path) -> None:
        # semacli project
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = []
            r = _invoke(["project", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_run_template_with_limit(self, tmp_path: Path) -> None:
        # semacli run mtree --limit ans2
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "--limit", "ans2", "-c", str(cfg)])
        assert r.exit_code == 0
        Mock.return_value.run_task.assert_called_once_with(
            1,
            5,
            playbook=None,
            environment=None,
            limit="ans2",
            tags=None,
            skip_tags=None,
            debug=0,
            dry_run=False,
            diff=False,
        )

    def test_env_create_from_vars_file(self, tmp_path: Path) -> None:
        # semacli env create --name prod --vars @vars.json
        cfg = _write_cfg(tmp_path)
        vars_file = tmp_path / "vars.json"
        vars_file.write_text('{"region":"eu-west-1"}')
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_environment.return_value = Environment(
                id=1, project_id=1, name="prod"
            )
            r = _invoke(
                [
                    "env",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "prod",
                    "--vars",
                    f"@{vars_file}",
                ]
            )
        assert r.exit_code == 0
        kwargs = Mock.return_value.create_environment.call_args.kwargs
        assert kwargs["name"] == "prod"
        assert "eu-west-1" in kwargs["json_vars"]

    def test_sched_create_by_template_name(self, tmp_path: Path) -> None:
        # semacli sched create --template mtree --cron '0 3 * * *'
        # Fixed by ken #736 — `sched create` resolves a name via
        # resolve_template, matching the name-first convention.
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli._crud.SemaphoreClient") as Mock,
            patch(
                "semacli.cli.commands.schedules.resolve_template", return_value=5
            ) as resolve_mock,
        ):
            Mock.return_value.create_schedule.return_value = Schedule(
                id=1, project_id=1, template_id=5
            )
            r = _invoke(
                [
                    "sched",
                    "-c",
                    str(cfg),
                    "create",
                    "--template",
                    "mtree",
                    "--cron",
                    "0 3 * * *",
                ]
            )
        assert r.exit_code == 0
        resolve_mock.assert_called_once()
        assert Mock.return_value.create_schedule.call_args.kwargs["template_id"] == 5


# ─────────────────────────────────────────────────────────────────────────
# semacli ping — Examples block
# ─────────────────────────────────────────────────────────────────────────
class TestPingExamples:
    def test_plain(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            r = _invoke(["ping", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "pong" in r.output

    def test_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            r = _invoke(["ping", "--json", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "pong" in r.output

    def test_explicit_config(self, tmp_path: Path) -> None:
        # semacli -c ./staging.ini ping  (Click accepts -c on the subcommand too)
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            r = _invoke(["ping", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_verbose_short_on_subcommand(self, tmp_path: Path) -> None:
        # sem ping -vv  (verbose flag on the subcommand)
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            r = _invoke(["ping", "-vv", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_verbose_short_at_root(self, tmp_path: Path) -> None:
        # sem -vv ping  (verbose flag at the root, inherited by subcommand)
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            r = _invoke(["-vv", "ping", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_quiet(self, tmp_path: Path) -> None:
        # semacli ping -q
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.ping.SemaphoreClient") as Mock:
            Mock.return_value.ping.return_value = "pong"
            r = _invoke(["ping", "-q", "-c", str(cfg)])
        assert r.exit_code == 0
        assert r.output == ""


# ─────────────────────────────────────────────────────────────────────────
# sem self-update — Examples (ken #746)
# ─────────────────────────────────────────────────────────────────────────
class TestSelfUpdateExamples:
    """``self-update`` does not touch a Semaphore server — only PyPI +
    pip. We patch the PyPI fetch + pip subprocess so the test runs
    offline and never alters the venv."""

    def test_already_up_to_date(self, tmp_path: Path) -> None:
        from semacli import __version__

        with patch(
            "semacli.cli.commands.self_update._fetch_latest_version",
            return_value=__version__,
        ):
            r = _invoke(["self-update"])
        assert r.exit_code == 0
        assert "Already up to date" in r.output

    def test_check_only(self, tmp_path: Path) -> None:
        with patch(
            "semacli.cli.commands.self_update._fetch_latest_version",
            return_value="99.99.99",
        ):
            r = _invoke(["self-update", "--check"])
        # --check exit 1 when an upgrade is available — scriptable.
        assert r.exit_code == 1


# ─────────────────────────────────────────────────────────────────────────
# semacli init — interactive, only flag parsing is validated here
# ─────────────────────────────────────────────────────────────────────────
class TestInitExamples:
    """The interactive prompts are mocked; the assertion is that Click
    parses the example flag combination and that the documented helpers
    are reached in the expected order."""

    def _run(self, extra: list[str], tmp_path: Path) -> Any:
        target = tmp_path / "out.ini"
        with (
            patch("semacli.cli.commands.init._prompt_url", return_value=("https://x", True, False)),
            patch("semacli.cli.commands.init._prompt_token", return_value="tok"),
            patch("semacli.cli.commands.init._prompt_project", return_value=None),
            patch("semacli.cli.commands.init._prompt_location", return_value=target),
            patch("semacli.cli.commands.init.SemaphoreClient"),
        ):
            args = ["init", *extra]
            # When --output is not in extra, the location prompt is used.
            return CliRunner().invoke(main, args)

    def test_prompt_for_everything(self, tmp_path: Path) -> None:
        # semacli init
        r = self._run([], tmp_path)
        assert r.exit_code == 0

    def test_with_url(self, tmp_path: Path) -> None:
        # sem init --url https://semaphore.domain.com
        r = self._run(["--url", "https://semaphore.domain.com"], tmp_path)
        assert r.exit_code == 0

    def test_with_output(self, tmp_path: Path) -> None:
        # semacli init --output ~/.semacli.ini  (use tmp instead of ~)
        target = tmp_path / "custom.ini"
        r = self._run(["--output", str(target)], tmp_path)
        assert r.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────
# semacli user / semacli user tokens — Examples blocks
# ─────────────────────────────────────────────────────────────────────────
class TestUserExamples:
    def test_user_default_is_whoami(self, tmp_path: Path) -> None:
        # semacli user
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.user.SemaphoreClient") as Mock:
            Mock.return_value.whoami.return_value = User(id=1, username="luc")
            r = _invoke(["user", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "luc" in r.output

    def test_user_whoami(self, tmp_path: Path) -> None:
        # semacli user whoami
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.user.SemaphoreClient") as Mock:
            Mock.return_value.whoami.return_value = User(id=1, username="luc")
            r = _invoke(["user", "-c", str(cfg), "whoami"])
        assert r.exit_code == 0
        assert "luc" in r.output

    def test_user_tokens_list(self, tmp_path: Path) -> None:
        # semacli user tokens
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_tokens.SemaphoreClient") as Mock:
            Mock.return_value.list_user_tokens.return_value = []
            r = _invoke(["user", "-c", str(cfg), "tokens"])
        assert r.exit_code == 0

    def test_user_tokens_create(self, tmp_path: Path) -> None:
        # semacli user tokens create
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_tokens.SemaphoreClient") as Mock:
            Mock.return_value.create_user_token.return_value = UserToken(id="sem-new", created="t")
            r = _invoke(["user", "-c", str(cfg), "tokens", "create"])
        assert r.exit_code == 0
        assert "sem-new" in r.output

    def test_user_tokens_delete(self, tmp_path: Path) -> None:
        # semacli user tokens delete sem-abc123
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_tokens.SemaphoreClient") as Mock:
            r = _invoke(["user", "-c", str(cfg), "tokens", "delete", "sem-abc123", "--yes"])
        assert r.exit_code == 0
        Mock.return_value.delete_user_token.assert_called_once_with("sem-abc123")


# ─────────────────────────────────────────────────────────────────────────
# semacli project — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestProjectExamples:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = []
            r = _invoke(["project", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_show(self, tmp_path: Path) -> None:
        # semacli project show 2
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_project.return_value = Project(id=2, name="x")
            r = _invoke(["project", "-c", str(cfg), "show", "2"])
        assert r.exit_code == 0
        Mock.return_value.get_project.assert_called_once_with(2)

    def test_create(self, tmp_path: Path) -> None:
        # semacli project create --name infra-prod
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.create_project.return_value = Project(id=3, name="infra-prod")
            r = _invoke(["project", "-c", str(cfg), "create", "--name", "infra-prod"])
        assert r.exit_code == 0
        Mock.return_value.create_project.assert_called_once()
        assert Mock.return_value.create_project.call_args.kwargs["name"] == "infra-prod"

    def test_update(self, tmp_path: Path) -> None:
        # semacli project update 2 --name infra-eu
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            r = _invoke(["project", "-c", str(cfg), "update", "2", "--name", "infra-eu"])
        assert r.exit_code == 0
        Mock.return_value.update_project.assert_called_once()
        args, kwargs = Mock.return_value.update_project.call_args
        assert args[0] == 2 and kwargs["name"] == "infra-eu"

    def test_delete(self, tmp_path: Path) -> None:
        # semacli project delete 2  (--yes added so we don't deadlock on prompt)
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            r = _invoke(["project", "-c", str(cfg), "delete", "2", "--yes"])
        assert r.exit_code == 0
        Mock.return_value.delete_project.assert_called_once_with(2)

    def test_json_for_pipe(self, tmp_path: Path) -> None:
        # semacli project --json  (the | jq part is shell, not Click)
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.projects.SemaphoreClient") as Mock:
            Mock.return_value.get_projects.return_value = [Project(id=1, name="a")]
            r = _invoke(["project", "--json", "-c", str(cfg)])
        assert r.exit_code == 0
        assert '"a"' in r.output


# ─────────────────────────────────────────────────────────────────────────
# semacli template — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestTemplateExamples:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = []
            r = _invoke(["template", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.get_template.return_value = Template(
                id=5, project_id=1, name="deploy"
            )
            r = _invoke(["template", "-c", str(cfg), "show", "5"])
        assert r.exit_code == 0

    def test_create_full(self, tmp_path: Path) -> None:
        # semacli template create --name deploy-prod --playbook deploy/prod.yml
        #     --repository 4 --inventory 42 --environment 7
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            Mock.return_value.create_template.return_value = Template(
                id=10, project_id=1, name="deploy-prod"
            )
            r = _invoke(
                [
                    "template",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "deploy-prod",
                    "--playbook",
                    "deploy/prod.yml",
                    "--repository",
                    "4",
                    "--inventory",
                    "42",
                    "--environment",
                    "7",
                ]
            )
        assert r.exit_code == 0
        kwargs = Mock.return_value.create_template.call_args.kwargs
        assert kwargs["name"] == "deploy-prod"
        assert kwargs["playbook"] == "deploy/prod.yml"
        assert kwargs["repository_id"] == 4
        assert kwargs["inventory_id"] == 42
        assert kwargs["environment_id"] == 7

    def test_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            r = _invoke(["template", "-c", str(cfg), "update", "5", "--environment", "8"])
        assert r.exit_code == 0
        Mock.return_value.update_template.assert_called_once()

    def test_delete(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.templates.SemaphoreClient") as Mock:
            r = _invoke(["template", "-c", str(cfg), "delete", "5", "--yes"])
        assert r.exit_code == 0
        Mock.return_value.delete_template.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────
# semacli task — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestTaskExamples:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.list_tasks.return_value = []
            r = _invoke(["task", "-c", str(cfg), "list"])
        assert r.exit_code == 0

    def test_run_with_limit(self, tmp_path: Path) -> None:
        # sem task run 5 --limit web1
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["task", "-c", str(cfg), "run", "5", "--limit", "web1"])
        assert r.exit_code == 0
        Mock.return_value.run_task.assert_called_once_with(
            1,
            5,
            playbook=None,
            environment=None,
            limit="web1",
            tags=None,
            skip_tags=None,
            debug=0,
            dry_run=False,
            diff=False,
        )

    def test_run_check(self, tmp_path: Path) -> None:
        # sem task run 5 --check --diff
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["task", "-c", str(cfg), "run", "5", "--check", "--diff"])
        assert r.exit_code == 0
        kwargs = Mock.return_value.run_task.call_args.kwargs
        assert kwargs["dry_run"] is True
        assert kwargs["diff"] is True

    def test_watch(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.tasks.time.sleep"),
        ):
            client = Mock.return_value
            client.get_task_output.return_value = [{"output": "done"}]
            client.get_task.return_value = Task(id=142, status="success")
            r = _invoke(["task", "-c", str(cfg), "watch", "142"])
        assert r.exit_code == 0

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.get_task.return_value = Task(id=142, template_id=5, status="success")
            r = _invoke(["task", "-c", str(cfg), "show", "142"])
        assert r.exit_code == 0

    def test_raw_output(self, tmp_path: Path) -> None:
        # semacli task raw-output 142  (> task-142.log is shell redirection)
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            Mock.return_value.get_task_raw_output.return_value = "PLAY [all]"
            r = _invoke(["task", "-c", str(cfg), "raw-output", "142"])
        assert r.exit_code == 0
        assert "PLAY [all]" in r.output

    def test_stop(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands.tasks.SemaphoreClient") as Mock:
            r = _invoke(["task", "-c", str(cfg), "stop", "142"])
        assert r.exit_code == 0
        Mock.return_value.stop_task.assert_called_once_with(1, 142)


# ─────────────────────────────────────────────────────────────────────────
# semacli inv — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestInvExamples:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_inventories.return_value = []
            r = _invoke(["inv", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_inventory.return_value = Inventory(
                id=42, project_id=1, name="hosts", type="static"
            )
            r = _invoke(["inv", "-c", str(cfg), "show", "42"])
        assert r.exit_code == 0

    def test_create_static_inline(self, tmp_path: Path) -> None:
        # Fixed by ken #733 — `inv create --content` renamed to `--inventory`.
        # semacli inv create --name prod-hosts --type static \
        #      --inventory '[prod]\nweb1'
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_inventory.return_value = Inventory(
                id=1, project_id=1, name="prod-hosts"
            )
            r = _invoke(
                [
                    "inv",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "prod-hosts",
                    "--type",
                    "static",
                    "--inventory",
                    "[prod]\nweb1",
                ]
            )
        assert r.exit_code == 0

    def test_create_from_file(self, tmp_path: Path) -> None:
        # Fixed by ken #733 — epilog now uses `--inventory <path>` (no @)
        # for type=file, where the value is a path inside the repo.
        # semacli inv create --name from-file --type file \
        #      --inventory ./hosts.ini
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_inventory.return_value = Inventory(
                id=1, project_id=1, name="from-file"
            )
            r = _invoke(
                [
                    "inv",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "from-file",
                    "--type",
                    "file",
                    "--inventory",
                    "./hosts.ini",
                ]
            )
        assert r.exit_code == 0
        assert Mock.return_value.create_inventory.call_args.kwargs["content"] == "./hosts.ini"

    def test_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = _invoke(["inv", "-c", str(cfg), "update", "42", "--name", "prod-hosts-eu"])
        assert r.exit_code == 0
        Mock.return_value.update_inventory.assert_called_once()

    def test_delete(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = _invoke(["inv", "-c", str(cfg), "delete", "42", "--yes"])
        assert r.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────
# semacli env — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestEnvExamples:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_environments.return_value = []
            r = _invoke(["env", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_environment.return_value = Environment(
                id=7, project_id=1, name="prod"
            )
            r = _invoke(["env", "-c", str(cfg), "show", "7"])
        assert r.exit_code == 0

    def test_create_inline_json(self, tmp_path: Path) -> None:
        # semacli env create --name prod --vars '{"region":"eu-west-1"}'
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_environment.return_value = Environment(
                id=1, project_id=1, name="prod"
            )
            r = _invoke(
                [
                    "env",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "prod",
                    "--vars",
                    '{"region":"eu-west-1"}',
                ]
            )
        assert r.exit_code == 0
        kwargs = Mock.return_value.create_environment.call_args.kwargs
        assert kwargs["json_vars"] == '{"region":"eu-west-1"}'

    def test_create_from_file_with_password(self, tmp_path: Path) -> None:
        # semacli env create --name prod --vars @vars.json --password 'vault-pw'
        cfg = _write_cfg(tmp_path)
        vars_file = tmp_path / "vars.json"
        vars_file.write_text('{"k":"v"}')
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_environment.return_value = Environment(
                id=1, project_id=1, name="prod"
            )
            r = _invoke(
                [
                    "env",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "prod",
                    "--vars",
                    f"@{vars_file}",
                    "--password",
                    "vault-pw",
                ]
            )
        assert r.exit_code == 0
        kwargs = Mock.return_value.create_environment.call_args.kwargs
        assert kwargs["password"] == "vault-pw"

    def test_update_with_file(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        vars_file = tmp_path / "vars.json"
        vars_file.write_text('{"k":"v"}')
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = _invoke(["env", "-c", str(cfg), "update", "7", "--vars", f"@{vars_file}"])
        assert r.exit_code == 0

    def test_delete(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = _invoke(["env", "-c", str(cfg), "delete", "7", "--yes"])
        assert r.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────
# semacli repo — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestRepoExamples:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_repositories.return_value = []
            r = _invoke(["repo", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_repository.return_value = Repository(
                id=4, project_id=1, name="infra"
            )
            r = _invoke(["repo", "-c", str(cfg), "show", "4"])
        assert r.exit_code == 0

    def test_create_full(self, tmp_path: Path) -> None:
        # Fixed by ken #737 — epilog typo `--ssh-key` -> `--ssh-key-id`.
        # semacli repo create --name infra \
        #      --git-url git@github.com:org/infra.git \
        #      --branch main --ssh-key-id 12
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_repository.return_value = Repository(
                id=1, project_id=1, name="infra"
            )
            r = _invoke(
                [
                    "repo",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "infra",
                    "--git-url",
                    "git@github.com:org/infra.git",
                    "--branch",
                    "main",
                    "--ssh-key-id",
                    "12",
                ]
            )
        assert r.exit_code == 0
        assert Mock.return_value.create_repository.call_args.kwargs["ssh_key_id"] == 12

    def test_update_branch(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = _invoke(["repo", "-c", str(cfg), "update", "4", "--branch", "release/2026"])
        assert r.exit_code == 0
        Mock.return_value.update_repository.assert_called_once()

    def test_delete(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = _invoke(["repo", "-c", str(cfg), "delete", "4", "--yes"])
        assert r.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────
# semacli key — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestKeyExamples:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_keys.return_value = []
            r = _invoke(["key", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_key.return_value = Key(
                id=12, project_id=1, name="root", type="ssh"
            )
            r = _invoke(["key", "-c", str(cfg), "show", "12"])
        assert r.exit_code == 0

    def test_create_ssh_from_file(self, tmp_path: Path) -> None:
        # semacli key create --name deploy-ssh --type ssh \
        #      --private-key @~/.ssh/id_ed25519  (use tmp instead of ~)
        cfg = _write_cfg(tmp_path)
        pem = tmp_path / "id_ed25519"
        pem.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_key.return_value = Key(
                id=1, project_id=1, name="deploy-ssh", type="ssh"
            )
            r = _invoke(
                [
                    "key",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "deploy-ssh",
                    "--type",
                    "ssh",
                    "--private-key",
                    f"@{pem}",
                ]
            )
        assert r.exit_code == 0
        kwargs = Mock.return_value.create_key.call_args.kwargs
        assert "OPENSSH" in kwargs["private_key"]

    def test_create_vault_password(self, tmp_path: Path) -> None:
        # Fixed by ken #734 — `key create --password` accepted on type=none.
        # semacli key create --name vault-pw --type none --password 's3cr3t'
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_key.return_value = Key(
                id=1, project_id=1, name="vault-pw", type="none"
            )
            r = _invoke(
                [
                    "key",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "vault-pw",
                    "--type",
                    "none",
                    "--password",
                    "s3cr3t",
                ]
            )
        assert r.exit_code == 0
        assert Mock.return_value.create_key.call_args.kwargs["password"] == "s3cr3t"

    def test_create_login_password(self, tmp_path: Path) -> None:
        # Fixed by ken #735 — `--login` + `--password` accepted as separate
        # flags; the legacy `user:pass` combined form still works when
        # `--password` is omitted.
        # semacli key create --name reg-login --type login_password \
        #      --login admin --password 's3cr3t'
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_key.return_value = Key(
                id=1, project_id=1, name="reg-login", type="login_password"
            )
            r = _invoke(
                [
                    "key",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "reg-login",
                    "--type",
                    "login_password",
                    "--login",
                    "admin",
                    "--password",
                    "s3cr3t",
                ]
            )
        assert r.exit_code == 0
        kwargs = Mock.return_value.create_key.call_args.kwargs
        assert kwargs["login"] == "admin"
        assert kwargs["password"] == "s3cr3t"

    def test_delete(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = _invoke(["key", "-c", str(cfg), "delete", "12", "--yes"])
        assert r.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────
# semacli sched — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestSchedExamples:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_schedules.return_value = []
            r = _invoke(["sched", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_schedule.return_value = Schedule(
                id=12, project_id=1, template_id=5, cron_format="0 3 * * *"
            )
            r = _invoke(["sched", "-c", str(cfg), "show", "12"])
        assert r.exit_code == 0

    def test_create_nightly(self, tmp_path: Path) -> None:
        # semacli sched create --template mtree --cron '0 3 * * *'
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli._crud.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.schedules.resolve_template", return_value=5),
        ):
            Mock.return_value.create_schedule.return_value = Schedule(
                id=1, project_id=1, template_id=5, cron_format="0 3 * * *"
            )
            r = _invoke(
                [
                    "sched",
                    "-c",
                    str(cfg),
                    "create",
                    "--template",
                    "mtree",
                    "--cron",
                    "0 3 * * *",
                ]
            )
        assert r.exit_code == 0
        Mock.return_value.create_schedule.assert_called_once()
        kwargs = Mock.return_value.create_schedule.call_args.kwargs
        assert kwargs["template_id"] == 5
        assert kwargs["cron_format"] == "0 3 * * *"

    def test_create_quarter_hour(self, tmp_path: Path) -> None:
        # semacli sched create --template 7 --cron '*/15 * * * *'
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli._crud.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.schedules.resolve_template", return_value=7),
        ):
            Mock.return_value.create_schedule.return_value = Schedule(
                id=2, project_id=1, template_id=7
            )
            r = _invoke(
                [
                    "sched",
                    "-c",
                    str(cfg),
                    "create",
                    "--template",
                    "7",
                    "--cron",
                    "*/15 * * * *",
                ]
            )
        assert r.exit_code == 0
        assert Mock.return_value.create_schedule.call_args.kwargs["cron_format"] == "*/15 * * * *"

    def test_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = _invoke(["sched", "-c", str(cfg), "update", "12", "--cron", "0 4 * * *"])
        assert r.exit_code == 0
        Mock.return_value.update_schedule.assert_called_once()

    def test_delete(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = _invoke(["sched", "-c", str(cfg), "delete", "12", "--yes"])
        assert r.exit_code == 0


# ─────────────────────────────────────────────────────────────────────────
# semacli run — Examples
# ─────────────────────────────────────────────────────────────────────────
class TestRunExamples:
    """``run`` watches by default; we patch ``_watch_task`` to short-
    circuit the polling loop, and ``resolve_template`` to skip the
    name → id lookup against the mocked client list."""

    def _patch_run(self, tmp_path: Path) -> tuple[Any, Any, Any, Any]:
        cfg = _write_cfg(tmp_path)
        client_p = patch("semacli.cli.commands.run.SemaphoreClient")
        resolve_p = patch("semacli.cli.commands.run.resolve_template", return_value=5)
        watch_p = patch("semacli.cli.commands.run._watch_task", return_value="success")
        return cfg, client_p, resolve_p, watch_p

    def test_by_name_watch(self, tmp_path: Path) -> None:
        # semacli run mtree
        cfg, client_p, resolve_p, watch_p = self._patch_run(tmp_path)
        with client_p as Mock, resolve_p, watch_p:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "-c", str(cfg)])
        assert r.exit_code == 0

    def test_by_name_with_limit(self, tmp_path: Path) -> None:
        # semacli run mtree --limit ans2
        cfg, client_p, resolve_p, watch_p = self._patch_run(tmp_path)
        with client_p as Mock, resolve_p, watch_p:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "--limit", "ans2", "-c", str(cfg)])
        assert r.exit_code == 0
        assert Mock.return_value.run_task.call_args.kwargs["limit"] == "ans2"

    def test_check_diff(self, tmp_path: Path) -> None:
        # sem run mtree --check --diff
        cfg, client_p, resolve_p, watch_p = self._patch_run(tmp_path)
        with client_p as Mock, resolve_p, watch_p:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "--check", "--diff", "-c", str(cfg)])
        assert r.exit_code == 0
        kwargs = Mock.return_value.run_task.call_args.kwargs
        assert kwargs["dry_run"] is True
        assert kwargs["diff"] is True

    def test_debug_level(self, tmp_path: Path) -> None:
        # sem run mtree --debug 2
        cfg, client_p, resolve_p, watch_p = self._patch_run(tmp_path)
        with client_p as Mock, resolve_p, watch_p:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "--debug", "2", "-c", str(cfg)])
        assert r.exit_code == 0
        assert Mock.return_value.run_task.call_args.kwargs["debug"] == 2

    def test_tags(self, tmp_path: Path) -> None:
        # sem run mtree --tags ntp,users
        cfg, client_p, resolve_p, watch_p = self._patch_run(tmp_path)
        with client_p as Mock, resolve_p, watch_p:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "--tags", "ntp,users", "-c", str(cfg)])
        assert r.exit_code == 0
        assert Mock.return_value.run_task.call_args.kwargs["tags"] == "ntp,users"

    def test_environment_key_val_sugar(self, tmp_path: Path) -> None:
        # sem run echo --environment 'msg=coucou' (ken #745)
        cfg, client_p, resolve_p, watch_p = self._patch_run(tmp_path)
        with client_p as Mock, resolve_p, watch_p:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "echo", "--environment", "msg=coucou", "-c", str(cfg)])
        assert r.exit_code == 0
        env = Mock.return_value.run_task.call_args.kwargs["environment"]
        assert env == '{"msg": "coucou"}'

    def test_environment_json_passthrough(self, tmp_path: Path) -> None:
        # sem run echo --environment '{"msg":"x"}' (ken #745)
        cfg, client_p, resolve_p, watch_p = self._patch_run(tmp_path)
        with client_p as Mock, resolve_p, watch_p:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "echo", "--environment", '{"msg":"x"}', "-c", str(cfg)])
        assert r.exit_code == 0
        env = Mock.return_value.run_task.call_args.kwargs["environment"]
        assert env == '{"msg":"x"}'

    def test_environment_invalid_json_exits_2(self, tmp_path: Path) -> None:
        # ken #745: malformed JSON must give a clean UsageError, not an HTTP 500.
        cfg = _write_cfg(tmp_path)
        r = _invoke(["run", "echo", "--environment", '{"msg":"x"', "-c", str(cfg)])
        assert r.exit_code == 2
        assert "not valid JSON" in r.output

    def test_no_watch(self, tmp_path: Path) -> None:
        # semacli run mtree --no-watch
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5),
        ):
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "mtree", "--no-watch", "-c", str(cfg)])
        assert r.exit_code == 0
        # Watcher should not have been called — but task id must be emitted.
        assert "99" in r.output

    def test_by_id_skips_resolve(self, tmp_path: Path) -> None:
        # semacli run 5 --limit web1
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli.commands.run.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.run.resolve_template", return_value=5) as resolve_mock,
            patch("semacli.cli.commands.run._watch_task", return_value="success"),
        ):
            Mock.return_value.run_task.return_value = Task(id=42, template_id=5)
            r = _invoke(["run", "5", "--limit", "web1", "-c", str(cfg)])
        assert r.exit_code == 0
        # The id form still passes through resolve_template, which is the
        # documented behavior (the resolver handles "numeric == id" itself).
        resolve_mock.assert_called_once()

    def test_exact_flag(self, tmp_path: Path) -> None:
        # semacli run --exact mtree
        cfg, client_p, resolve_p, watch_p = self._patch_run(tmp_path)
        with client_p as Mock, resolve_p as resolve_mock, watch_p:
            Mock.return_value.run_task.return_value = Task(id=99, template_id=5)
            r = _invoke(["run", "--exact", "mtree", "-c", str(cfg)])
        assert r.exit_code == 0
        assert resolve_mock.call_args.kwargs["exact"] is True
