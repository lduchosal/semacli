"""`sem project cache clear` + `repo update --monorepo` (ken #1248).

The fork svn v2.21.0-svn.1 adds a ``monorepo`` repository flag (one
checkout shared by every template) and the cache purge
``DELETE /project/{pid}/cache`` wipes the project's tmp dir with no check
of its own, so semacli refuses it while a task of the project is active.
"""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from semacli.cli import main
from semacli.core.client import SemaphoreClient
from semacli.core.config import SemaphoreConfig
from semacli.core.exceptions import ActiveTasksError, UnsupportedFieldError
from semacli.core.guards import ensure_no_active_tasks
from semacli.core.models import ACTIVE_TASK_STATUSES, Repository, Task

_CLIENT = "semacli.cli.commands._project_cache.SemaphoreClient"
_REPO = {
    "id": 3,
    "project_id": 1,
    "name": "2113-ansible",
    "git_url": "svn+ssh://svn@dev/ansible",
    "git_branch": "trunk",
    "ssh_key_id": 2,
}
_RUNNING = Task(id=4242, template_id=9, tpl_alias="mtree", status="running")
_ZOMBIE = Task(id=4100, template_id=7, status="waiting")


def _cfg() -> SemaphoreConfig:
    return SemaphoreConfig(url="https://sema.example", bearer_token="tok")


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


def _clear(tmp_path: Path, *extra: str, active: list[Task] | None = None):  # noqa: ANN202
    cfg = _write_cfg(tmp_path)
    head = [a for a in extra if a in ("--json", "-q")]
    tail = [a for a in extra if a not in head]
    with patch(_CLIENT) as mock:
        mock.return_value.list_active_tasks.return_value = active or []
        r = CliRunner().invoke(main, ["project", "-c", str(cfg), *head, "cache", "clear", *tail])
    return r, mock.return_value


# ── client ────────────────────────────────────────────────────────────────
class TestClient:
    def test_clear_project_cache_is_a_delete(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=None) as req:
            c.clear_project_cache(1)
        req.assert_called_once_with("project/1/cache", method="DELETE")

    def test_list_active_tasks_keeps_unfinished_only(self) -> None:
        rows = [
            {"id": 1, "status": "success"},
            {"id": 2, "status": "running"},
            {"id": 3, "status": "error"},
            {"id": 4, "status": "waiting"},
            {"id": 5, "status": "stopped"},
            {"id": 6, "status": "stopping"},
        ]
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", return_value=rows):
            assert [t.id for t in c.list_active_tasks(1)] == [2, 4, 6]

    def test_active_statuses_mirror_the_server(self) -> None:
        # task_logger.UnfinishedTaskStatuses() of the fork
        assert ACTIVE_TASK_STATUSES == {
            "waiting",
            "starting",
            "waiting_confirmation",
            "confirmed",
            "rejected",
            "running",
            "stopping",
        }

    def test_update_repository_sets_monorepo(self) -> None:
        current = {**_REPO, "monorepo": False}
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", side_effect=[current, None]) as req:
            c.update_repository(1, 3, monorepo=True)
        assert req.call_args.kwargs["body"] == {**current, "monorepo": True}

    def test_update_repository_refuses_monorepo_on_upstream_server(self) -> None:
        # upstream Semaphore has no `monorepo`: the PUT would drop it silently
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", side_effect=[dict(_REPO), None]) as req:
            with pytest.raises(UnsupportedFieldError, match="svn fork"):
                c.update_repository(1, 3, monorepo=True)
        assert req.call_count == 1  # GET only, no PUT

    def test_update_repository_without_monorepo_works_on_upstream(self) -> None:
        c = SemaphoreClient(_cfg())
        with patch.object(c, "_request", side_effect=[dict(_REPO), None]) as req:
            c.update_repository(1, 3, git_branch="branches/x", monorepo=None)
        assert req.call_args.kwargs["body"]["git_branch"] == "branches/x"
        assert "monorepo" not in req.call_args.kwargs["body"]

    def test_repository_model_reads_monorepo(self) -> None:
        assert Repository.model_validate({**_REPO, "monorepo": True}).monorepo is True
        assert Repository.model_validate(_REPO).monorepo is False


# ── guard ─────────────────────────────────────────────────────────────────
class TestGuard:
    def test_no_active_task_passes(self) -> None:
        ensure_no_active_tasks(1, [])

    def test_active_tasks_raise_with_details(self) -> None:
        with pytest.raises(ActiveTasksError) as exc:
            ensure_no_active_tasks(1, [_RUNNING, _ZOMBIE])
        msg = str(exc.value)
        assert "2 active task(s)" in msg
        assert "#4242 running (mtree)" in msg
        assert "#4100 waiting (template 7)" in msg
        assert "--force" in msg
        assert exc.value.tasks == [(4242, "running", "mtree"), (4100, "waiting", "template 7")]


# ── project cache clear ───────────────────────────────────────────────────
class TestCacheClear:
    def test_idle_project_is_cleared(self, tmp_path: Path) -> None:
        r, client = _clear(tmp_path, "-p", "1")
        assert r.exit_code == 0, r.output
        client.clear_project_cache.assert_called_once_with(1)
        assert "cleared cache of project 1" in r.output

    def test_default_project_from_config(self, tmp_path: Path) -> None:
        r, client = _clear(tmp_path)
        assert r.exit_code == 0
        client.list_active_tasks.assert_called_once_with(1)

    def test_active_task_refuses_without_delete(self, tmp_path: Path) -> None:
        r, client = _clear(tmp_path, active=[_RUNNING])
        assert r.exit_code == 2
        assert "#4242 running (mtree)" in r.output
        client.clear_project_cache.assert_not_called()

    def test_force_clears_over_active_tasks(self, tmp_path: Path) -> None:
        r, client = _clear(tmp_path, "--force", active=[_ZOMBIE])
        assert r.exit_code == 0
        client.clear_project_cache.assert_called_once_with(1)
        assert "--force over 1 active task(s)" in r.output
        assert "4100" in r.output

    def test_dry_run_idle_exits_0_and_clears_nothing(self, tmp_path: Path) -> None:
        r, client = _clear(tmp_path, "--dry-run")
        assert r.exit_code == 0
        assert "would go ahead" in r.output
        client.clear_project_cache.assert_not_called()

    def test_dry_run_busy_exits_1(self, tmp_path: Path) -> None:
        r, client = _clear(tmp_path, "--dry-run", active=[_RUNNING])
        assert r.exit_code == 1
        assert "would be refused" in r.output
        assert "4242" in r.output
        client.clear_project_cache.assert_not_called()

    def test_dry_run_force_busy_exits_0(self, tmp_path: Path) -> None:
        r, client = _clear(tmp_path, "--dry-run", "--force", active=[_RUNNING])
        assert r.exit_code == 0
        assert "would go ahead (--force" in r.output
        client.clear_project_cache.assert_not_called()

    def test_json(self, tmp_path: Path) -> None:
        r, _ = _clear(tmp_path, "--json", "--force", active=[_ZOMBIE])
        assert r.exit_code == 0
        out = json.loads(r.output)
        assert out["cleared"] is True
        assert out["forced"] is True
        assert out["allowed"] is True
        assert [t["id"] for t in out["active_tasks"]] == [4100]

    def test_json_dry_run_busy(self, tmp_path: Path) -> None:
        r, _ = _clear(tmp_path, "--json", "--dry-run", active=[_RUNNING])
        assert r.exit_code == 1
        out = json.loads(r.output)
        assert out == {
            "project_id": 1,
            "dry_run": True,
            "forced": False,
            "allowed": False,
            "cleared": False,
            "active_tasks": [_RUNNING.model_dump()],
        }

    def test_quiet(self, tmp_path: Path) -> None:
        r, client = _clear(tmp_path, "-q")
        assert r.exit_code == 0
        assert r.output == ""
        client.clear_project_cache.assert_called_once()

    def test_help_examples(self) -> None:
        r = CliRunner().invoke(main, ["project", "cache", "clear", "--help"])
        assert r.exit_code == 0
        assert "sem project cache clear -p 1 --dry-run" in r.output


# ── repo update --monorepo / show / list ─────────────────────────────────
class TestRepoMonorepo:
    @pytest.mark.parametrize(("flag", "value"), [("--monorepo", True), ("--no-monorepo", False)])
    def test_update_flag(self, tmp_path: Path, flag: str, value: bool) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as mock:
            r = CliRunner().invoke(main, ["repo", "-c", str(cfg), "update", "3", flag])
        assert r.exit_code == 0, r.output
        assert mock.return_value.update_repository.call_args.kwargs["monorepo"] is value

    def test_update_without_flag_leaves_monorepo_alone(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as mock:
            CliRunner().invoke(main, ["repo", "-c", str(cfg), "update", "3", "--name", "x"])
        assert mock.return_value.update_repository.call_args.kwargs["monorepo"] is None

    def test_update_on_upstream_server_exits_4(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as mock:
            mock.return_value.update_repository.side_effect = UnsupportedFieldError(
                "project/1/repositories/3", "monorepo", "needs the svn fork"
            )
            r = CliRunner().invoke(main, ["repo", "-c", str(cfg), "update", "3", "--monorepo"])
        assert r.exit_code == 4
        assert "does not know 'monorepo'" in r.output

    def test_show_and_list_display_the_flag(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        mono = Repository.model_validate({**_REPO, "monorepo": True})
        plain = Repository.model_validate({**_REPO, "id": 4, "name": "infra"})
        with patch("semacli.cli._crud.SemaphoreClient") as mock:
            mock.return_value.get_repository.return_value = mono
            mock.return_value.list_repositories.return_value = [mono, plain]
            shown = CliRunner().invoke(main, ["repo", "-c", str(cfg), "show", "3"])
            listed = CliRunner().invoke(main, ["repo", "-c", str(cfg)])
        assert "monorepo:   True" in shown.output
        lines = listed.output.splitlines()
        assert lines[0].endswith("[monorepo]")
        assert "[monorepo]" not in lines[1]
