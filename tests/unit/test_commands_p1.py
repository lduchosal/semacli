"""Tests for the P1 CLI command groups (inventories, environments, repositories, keys, schedules)."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from semacli.cli import main
from semacli.core.models import (
    Environment,
    Inventory,
    Key,
    Repository,
    Schedule,
    Task,
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


# ── Inventories ────────────────────────────────────────────────────────────
class TestInventoriesCommands:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_inventories.return_value = [
                Inventory(id=1, project_id=1, name="hosts", type="static"),
            ]
            r = CliRunner().invoke(main, ["inventories", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "hosts" in r.output

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_inventory.return_value = Inventory(
                id=7, project_id=1, name="hosts", type="static", content="[all]\nans1"
            )
            r = CliRunner().invoke(main, ["inventories", "-c", str(cfg), "show", "7"])
        assert r.exit_code == 0
        assert "ans1" in r.output

    def test_create_inline_content(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_inventory.return_value = Inventory(
                id=9, project_id=1, name="x", type="static"
            )
            r = CliRunner().invoke(
                main,
                [
                    "inventories",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "x",
                    "--type",
                    "static",
                    "--inventory",
                    "[all]",
                ],
            )
        assert r.exit_code == 0
        Mock.return_value.create_inventory.assert_called_with(
            1, name="x", type="static", content="[all]", ssh_key_id=0, become_key_id=0
        )

    def test_create_file_content(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        hosts = tmp_path / "hosts.ini"
        hosts.write_text("[all]\nans2\n")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_inventory.return_value = Inventory(
                id=10, project_id=1, name="y", type="static"
            )
            CliRunner().invoke(
                main,
                [
                    "inventories",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "y",
                    "--type",
                    "static",
                    "--inventory",
                    f"@{hosts}",
                ],
            )
        call_kwargs = Mock.return_value.create_inventory.call_args.kwargs
        assert "ans2" in call_kwargs["content"]

    def test_delete_with_yes(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(main, ["inventories", "-c", str(cfg), "delete", "7", "--yes"])
        assert r.exit_code == 0
        Mock.return_value.delete_inventory.assert_called_once_with(1, 7)

    def test_delete_without_yes_prompts(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = CliRunner().invoke(
                main, ["inventories", "-c", str(cfg), "delete", "7"], input="n\n"
            )
        assert r.exit_code != 0  # aborted


# ── Environments ──────────────────────────────────────────────────────────
class TestEnvironmentsCommands:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_environments.return_value = [
                Environment(id=1, project_id=1, name="prod")
            ]
            r = CliRunner().invoke(main, ["environments", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "prod" in r.output

    def test_create_inline_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_environment.return_value = Environment(
                id=2, project_id=1, name="dev"
            )
            r = CliRunner().invoke(
                main,
                ["environments", "-c", str(cfg), "create", "--name", "dev", "--vars", '{"k":"v"}'],
            )
        assert r.exit_code == 0
        Mock.return_value.create_environment.assert_called_with(
            1, name="dev", json_vars='{"k":"v"}', password=""
        )

    def test_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            CliRunner().invoke(
                main, ["environments", "-c", str(cfg), "update", "3", "--name", "renamed"]
            )
        Mock.return_value.update_environment.assert_called_with(
            1, 3, name="renamed", json=None, password=None
        )


# ── Repositories ──────────────────────────────────────────────────────────
class TestRepositoriesCommands:
    def test_list_and_create(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_repositories.return_value = [
                Repository(id=1, project_id=1, name="r", git_url="g@x", git_branch="main")
            ]
            r1 = CliRunner().invoke(main, ["repositories", "-c", str(cfg)])
            assert "r" in r1.output

            Mock.return_value.create_repository.return_value = Repository(
                id=2, project_id=1, name="r2"
            )
            r2 = CliRunner().invoke(
                main,
                [
                    "repositories",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "r2",
                    "--git-url",
                    "git@y",
                    "--ssh-key-id",
                    "1",
                ],
            )
            assert r2.exit_code == 0
            Mock.return_value.create_repository.assert_called_with(
                1, name="r2", git_url="git@y", git_branch="main", ssh_key_id=1
            )


# ── Keys ──────────────────────────────────────────────────────────────────
class TestKeysCommands:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_keys.return_value = [
                Key(id=1, project_id=1, name="root", type="ssh")
            ]
            r = CliRunner().invoke(main, ["keys", "-c", str(cfg)])
        assert "root" in r.output

    def test_create_ssh_from_file(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        pem = tmp_path / "id_rsa"
        pem.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END...")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_key.return_value = Key(
                id=9, project_id=1, name="root", type="ssh"
            )
            CliRunner().invoke(
                main,
                [
                    "keys",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "root",
                    "--type",
                    "ssh",
                    "--login",
                    "root",
                    "--private-key",
                    f"@{pem}",
                ],
            )
        kwargs = Mock.return_value.create_key.call_args.kwargs
        assert kwargs["name"] == "root"
        assert kwargs["type"] == "ssh"
        assert kwargs["login"] == "root"
        assert "OPENSSH" in kwargs["private_key"]

    def test_create_login_password(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_key.return_value = Key(
                id=10, project_id=1, name="creds", type="login_password"
            )
            CliRunner().invoke(
                main,
                [
                    "keys",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "creds",
                    "--type",
                    "login_password",
                    "--login",
                    "alice:wonderland",
                ],
            )
        kwargs = Mock.return_value.create_key.call_args.kwargs
        assert kwargs["login"] == "alice"
        assert kwargs["password"] == "wonderland"


# ── Schedules ─────────────────────────────────────────────────────────────
class TestSchedulesCommands:
    def test_create(self, tmp_path: Path) -> None:
        # `sched create` now exposes `--template <name|id>` (resolved via
        # resolve_template). See ken #736.
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli._crud.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.schedules.resolve_template", return_value=10),
        ):
            Mock.return_value.create_schedule.return_value = Schedule(
                id=1, project_id=1, template_id=10, cron_format="0 3 * * *", name="x", active=True
            )
            r = CliRunner().invoke(
                main,
                [
                    "schedules",
                    "-c",
                    str(cfg),
                    "create",
                    "--template",
                    "10",
                    "--cron",
                    "0 3 * * *",
                    "--name",
                    "x",
                ],
            )
        assert r.exit_code == 0
        # The legacy fields keep their values; the new overrides default to None/False
        # so the body builder omits them (back-compat, ken #907).
        Mock.return_value.create_schedule.assert_called_with(
            1,
            template_id=10,
            cron_format="0 3 * * *",
            name="x",
            active=True,
            schedule_type=None,
            run_at=None,
            delete_after_run=False,
            message=None,
            inventory_id=None,
            cli_args=None,
            limit=None,
            tags=None,
            skip_tags=None,
        )

    def test_create_with_overrides(self, tmp_path: Path) -> None:
        # ken #907: a schedule can carry --limit / --tags / --inventory natively.
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli._crud.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.schedules.resolve_template", return_value=10),
            patch("semacli.cli.commands.schedules.resolve_inventory", return_value=7) as inv,
        ):
            Mock.return_value.create_schedule.return_value = Schedule(id=1)
            r = CliRunner().invoke(
                main,
                [
                    "schedules", "-c", str(cfg), "create",
                    "--template", "mtree", "--cron", "0 3 * * *",
                    "--limit", "h1,h2", "--tags", "pkg", "--skip-tags", "slow",
                    "--inventory", "prod", "--cli-args", '["--forks","5"]',
                    "--message", "nightly",
                ],
            )  # fmt: skip
        assert r.exit_code == 0
        inv.assert_called_once()  # name resolution happened for --inventory
        kwargs = Mock.return_value.create_schedule.call_args.kwargs
        assert kwargs["limit"] == "h1,h2"
        assert kwargs["tags"] == "pkg"
        assert kwargs["skip_tags"] == "slow"
        assert kwargs["inventory_id"] == 7
        assert kwargs["cli_args"] == '["--forks","5"]'
        assert kwargs["message"] == "nightly"

    def test_create_run_at_once(self, tmp_path: Path) -> None:
        # ken #907: one-shot run-at + delete-after-run.
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli._crud.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.schedules.resolve_template", return_value=10),
        ):
            Mock.return_value.create_schedule.return_value = Schedule(id=1)
            r = CliRunner().invoke(
                main,
                [
                    "schedules", "-c", str(cfg), "create",
                    "--template", "mtree", "--run-at", "2026-06-25 02:00", "--once",
                ],
            )  # fmt: skip
        assert r.exit_code == 0
        kwargs = Mock.return_value.create_schedule.call_args.kwargs
        assert kwargs["schedule_type"] == "run_at"
        assert kwargs["run_at"] == "2026-06-25T02:00:00Z"
        assert kwargs["delete_after_run"] is True

    def test_create_requires_a_trigger(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = CliRunner().invoke(
                main, ["schedules", "-c", str(cfg), "create", "--template", "mtree"]
            )
        assert r.exit_code == 2  # UsageError: neither --cron nor --run-at
        assert "trigger" in r.output

    def test_create_rejects_both_triggers(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = CliRunner().invoke(
                main,
                [
                    "schedules", "-c", str(cfg), "create",
                    "--template", "mtree", "--cron", "0 3 * * *", "--run-at", "2026-06-25 02:00",
                ],
            )  # fmt: skip
        assert r.exit_code == 2
        assert "not both" in r.output

    def test_create_rejects_bad_run_at(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = CliRunner().invoke(
                main,
                [
                    "schedules", "-c", str(cfg), "create",
                    "--template", "mtree", "--run-at", "not-a-time",
                ],
            )  # fmt: skip
        assert r.exit_code == 2

    def test_update_active_flag(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            CliRunner().invoke(main, ["schedules", "-c", str(cfg), "update", "5", "--inactive"])
        Mock.return_value.update_schedule.assert_called_with(
            1,
            5,
            name=None,
            cron_format=None,
            active=False,
            schedule_type=None,
            run_at=None,
            delete_after_run=None,
            message=None,
            inventory_id=None,
            cli_args=None,
            limit=None,
            tags=None,
            skip_tags=None,
        )

    def test_update_overrides(self, tmp_path: Path) -> None:
        # ken #907: tweak limit + skip-tags on an existing schedule.
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(
                main,
                [
                    "schedules", "-c", str(cfg), "update", "12",
                    "--limit", "h3", "--skip-tags", "slow",
                ],
            )  # fmt: skip
        assert r.exit_code == 0
        kwargs = Mock.return_value.update_schedule.call_args.kwargs
        assert kwargs["limit"] == "h3"
        assert kwargs["skip_tags"] == "slow"

    def test_update_rejects_both_triggers(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient"):
            r = CliRunner().invoke(
                main,
                [
                    "schedules", "-c", str(cfg), "update", "12",
                    "--cron", "0 3 * * *", "--run-at", "2026-06-25 02:00",
                ],
            )  # fmt: skip
        assert r.exit_code == 2
        assert "not both" in r.output

    def test_show_renders_overrides(self, tmp_path: Path) -> None:
        # ken #907: show surfaces run-at + every task_params override line.
        cfg = _write_cfg(tmp_path)
        sched = Schedule.model_validate(
            {
                "id": 12, "project_id": 1, "template_id": 5,
                "type": "run_at", "run_at": "2026-06-25T02:00:00Z",
                "delete_after_run": True,
                "task_params": {
                    "message": "nightly", "inventory_id": 4, "arguments": '["--forks","5"]',
                    "params": {"limit": ["h1", "h2"], "tags": ["pkg"], "skip_tags": ["slow"]},
                },
            }
        )  # fmt: skip
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_schedule.return_value = sched
            r = CliRunner().invoke(main, ["schedules", "-c", str(cfg), "show", "12"])
        assert r.exit_code == 0
        for token in ("run_at", "once", "inventory_id: 4", "h1,h2", "pkg", "slow", "nightly"):
            assert token in r.output

    def test_list_run_at_and_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        items = [Schedule(id=1, template_id=5, type="run_at", run_at="2026-06-25T02:00:00Z")]
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_schedules.return_value = items
            text = CliRunner().invoke(main, ["schedules", "-c", str(cfg)])
            js = CliRunner().invoke(main, ["schedules", "-c", str(cfg), "--json"])
        assert text.exit_code == 0
        assert "run-at" in text.output  # fmt_row run-at branch
        assert js.exit_code == 0
        assert '"run_at"' in js.output  # emit_json_list branch

    def test_create_json_output(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with (
            patch("semacli.cli._crud.SemaphoreClient") as Mock,
            patch("semacli.cli.commands.schedules.resolve_template", return_value=5),
        ):
            Mock.return_value.create_schedule.return_value = Schedule(id=9, template_id=5)
            r = CliRunner().invoke(
                main,
                ["schedules", "-c", str(cfg), "--json", "create", "--template", "5", "--cron",
                 "0 3 * * *"],
            )  # fmt: skip
        assert r.exit_code == 0
        assert '"id": 9' in r.output

    def test_delete(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(main, ["schedules", "-c", str(cfg), "delete", "7", "--yes"])
        assert r.exit_code == 0
        Mock.return_value.delete_schedule.assert_called_with(1, 7)


# ── Tasks extras ──────────────────────────────────────────────────────────
class TestTasksExtras:
    def test_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            Mock.return_value.list_tasks.return_value = [
                Task(id=99, template_id=10, status="success", created="t"),
            ]
            r = CliRunner().invoke(main, ["tasks", "-c", str(cfg), "list"])
        assert r.exit_code == 0
        assert "99" in r.output

    def test_list_shows_template_alias_and_id(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            Mock.return_value.list_tasks.return_value = [
                Task(id=99, template_id=10, tpl_alias="doas", status="success", created="t"),
                Task(id=98, template_id=12, tpl_alias="mtree", status="error", created="t"),
            ]
            r = CliRunner().invoke(main, ["tasks", "-c", str(cfg), "list"])
        assert r.exit_code == 0
        assert "tpl=10" in r.output
        assert "doas " in r.output
        assert "mtree" in r.output

    def test_list_json_includes_alias_fields(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            Mock.return_value.list_tasks.return_value = [
                Task(
                    id=99,
                    template_id=10,
                    tpl_alias="doas",
                    tpl_playbook="doas.yml",
                    status="success",
                    created="t",
                ),
            ]
            r = CliRunner().invoke(main, ["tasks", "-c", str(cfg), "--json", "list"])
        payload = json.loads(r.output)
        assert payload[0]["template_id"] == 10
        assert payload[0]["tpl_alias"] == "doas"
        assert payload[0]["tpl_playbook"] == "doas.yml"

    def test_show_displays_template_alias(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            Mock.return_value.get_task.return_value = Task(
                id=99, template_id=10, tpl_alias="doas", status="success", created="t"
            )
            r = CliRunner().invoke(main, ["tasks", "-c", str(cfg), "show", "99"])
        assert r.exit_code == 0
        assert "template:    doas" in r.output

    def test_stop(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            r = CliRunner().invoke(main, ["tasks", "-c", str(cfg), "stop", "99"])
        assert r.exit_code == 0
        Mock.return_value.stop_task.assert_called_once_with(1, 99)

    def test_raw_output_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._task_views.SemaphoreClient") as Mock:
            Mock.return_value.get_task_raw_output.return_value = "PLAY [all]\nTASK [ping]"
            r = CliRunner().invoke(main, ["tasks", "-c", str(cfg), "raw-output", "99"])
        assert "PLAY [all]" in r.output


@pytest.fixture(autouse=True)
def _silence_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    # The client's _warn_insecure prints to stderr at init — for CliRunner
    # invocations that's mixed with stdout. We don't need to silence it but
    # tests assert on stdout so leave it; this fixture is a future hook.
    return None
