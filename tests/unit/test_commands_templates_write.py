"""Tests for `template create` / `update` / `audit` / `sync` (ken #1118)."""

import json
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.exceptions import SemaphoreAPIError
from semacli.core.models import (
    Environment,
    Inventory,
    Repository,
    Template,
    TemplateTaskParams,
    View,
)

_PERMISSIVE = TemplateTaskParams(
    allow_debug=True,
    allow_override_inventory=True,
    allow_override_limit=True,
    allow_override_skip_tags=True,
    allow_override_tags=True,
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


def _client(mock: MagicMock) -> MagicMock:
    """Wire the name→id lookups a template write needs."""
    client = mock.return_value
    client.list_repositories.return_value = [Repository(id=3, name="2113-ansible")]
    client.list_inventories.return_value = [Inventory(id=4, name="hosts")]
    client.list_environments.return_value = [Environment(id=1, name="default")]
    client.list_views.return_value = [View(id=2, title="BSD")]
    client.get_templates.return_value = [Template(id=6, name="mtree", playbook="mtree.yml")]
    client.create_template.return_value = Template(id=12, name="new")
    client.update_template.return_value = {}
    return client


def _run(cfg: Path, *args: str) -> Any:
    return CliRunner().invoke(main, ["template", "-c", str(cfg), *args])


class TestTemplateCreate:
    def test_resolves_names_to_ids(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            result = _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "2113-ansible",
                "--inventory",
                "hosts",
                "--environment",
                "default",
                "--view",
                "BSD",
            )
        assert result.exit_code == 0, result.output
        kwargs = client.create_template.call_args.kwargs
        assert (kwargs["repository_id"], kwargs["inventory_id"]) == (3, 4)
        assert (kwargs["environment_id"], kwargs["view_id"]) == (1, 2)

    def test_defaults_to_every_override_allowed(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
            )
        assert set(client.create_template.call_args.kwargs["task_params"].values()) == {True}

    def test_allow_override_narrows_the_toggles(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
                "--allow-override",
                "limit",
            )
        params = client.create_template.call_args.kwargs["task_params"]
        assert params["allow_override_limit"] is True
        assert params["allow_debug"] is False

    def test_unknown_override_word_is_a_user_error(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            _client(Mock)
            result = _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
                "--allow-override",
                "bogus",
            )
        assert result.exit_code == 2
        assert "unknown override" in result.output

    def test_no_allow_override_args(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
                "--no-allow-override-args",
            )
        assert client.create_template.call_args.kwargs["allow_override_args"] is False

    def test_jinja_arguments_refused_before_the_post(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            result = _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
                "--arguments",
                '["{{ limit }}"]',
            )
        assert result.exit_code == 2
        client.create_template.assert_not_called()

    def test_survey_vars_must_be_json_objects(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            _client(Mock)
            bad_json = _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
                "--survey-vars",
                "nope",
            )
            not_objects = _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
                "--survey-vars",
                "[1]",
            )
        assert bad_json.exit_code == 2
        assert not_objects.exit_code == 2

    def test_survey_vars_are_forwarded(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            _run(
                cfg,
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
                "--survey-vars",
                '[{"name": "release"}]',
            )
        assert client.create_template.call_args.kwargs["survey_vars"] == [{"name": "release"}]

    def test_json_output(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            _client(Mock)
            result = _run(
                cfg,
                "--json",
                "create",
                "--name",
                "x",
                "--playbook",
                "x.yml",
                "--repository",
                "3",
                "--inventory",
                "4",
            )
        assert json.loads(result.output)["id"] == 12


class TestTemplateUpdate:
    def test_only_passed_fields_are_patched(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            result = _run(cfg, "update", "6", "--environment", "default")
        assert result.exit_code == 0
        args, kwargs = client.update_template.call_args
        assert args == (1, 6)
        assert kwargs["environment_id"] == 1
        assert kwargs["name"] is None
        assert kwargs["task_params"] is None

    def test_resolves_the_template_by_name(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            result = _run(cfg, "update", "mtree", "--playbook", "other.yml")
        assert result.exit_code == 0
        assert client.update_template.call_args.args == (1, 6)

    def test_reports_the_patched_fields(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            _client(Mock)
            result = _run(cfg, "update", "6", "--allow-override", "limit")
        assert "task_params" in result.output

    def test_nothing_to_patch_is_reported(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            _client(Mock)
            result = _run(cfg, "update", "6")
        assert "nothing" in result.output

    def test_jinja_arguments_refused(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            result = _run(cfg, "update", "6", "--arguments", '["{{ tags }}"]')
        assert result.exit_code == 2
        client.update_template.assert_not_called()


class TestTemplateAudit:
    def test_clean_project_exits_zero(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = [
                Template(id=1, name="ok", task_params=_PERMISSIVE)
            ]
            result = _run(cfg, "audit")
        assert result.exit_code == 0
        assert "All 1 template(s) allow: limit" in result.output

    def test_offender_exits_one_and_names_the_missing_override(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = [
                Template(id=1, name="ok", task_params=_PERMISSIVE),
                Template(id=2, name="legacy"),
            ]
            result = _run(cfg, "audit")
        assert result.exit_code == 1
        assert "legacy  missing: limit" in result.output
        assert "Total: 1 of 2" in result.output

    def test_require_accepts_several_words(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = [
                Template(
                    id=2, name="narrow", task_params=TemplateTaskParams(allow_override_limit=True)
                )
            ]
            result = _run(cfg, "audit", "--require", "limit,tags")
        assert result.exit_code == 1
        assert "missing: tags" in result.output

    def test_unknown_require_word_is_a_user_error(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        result = _run(cfg, "audit", "--require", "bogus")
        assert result.exit_code == 2

    def test_json_output(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_templates.return_value = [Template(id=2, name="legacy")]
            result = _run(cfg, "--json", "audit")
        assert json.loads(result.output) == [{"id": 2, "name": "legacy", "missing": ["limit"]}]


_MANIFEST = """
defaults:
  repository: 2113-ansible
  inventory: hosts
  environment: default
  description: "Run ansible playbook {playbook}"
playbooks: ansible
views:
  mtree: BSD
"""


def _manifest(tmp_path: Path, *playbooks: str) -> Path:
    path = tmp_path / "templates.yml"
    path.write_text(_MANIFEST)
    (tmp_path / "ansible").mkdir(exist_ok=True)
    for name in playbooks:
        (tmp_path / "ansible" / name).write_text("---\n")
    return path


def _raw(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": 6,
        "name": "mtree",
        "playbook": "mtree.yml",
        "app": "ansible",
        "repository_id": 3,
        "inventory_id": 4,
        "environment_id": 1,
        "view_id": 2,
        "description": "Run ansible playbook mtree.yml",
        "arguments": "[]",
        "allow_override_args_in_task": True,
        "task_params": {
            "allow_debug": True,
            "allow_override_inventory": True,
            "allow_override_limit": True,
            "allow_override_skip_tags": True,
            "allow_override_tags": True,
        },
    }
    base.update(overrides)
    return base


class TestTemplateSync:
    def test_dry_run_touches_nothing(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "mtree.yml", "ntp.yml")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = [_raw()]
            result = _run(cfg, "sync", "--manifest", str(manifest), "--dry-run")
        assert result.exit_code == 0
        assert "CREATE  ntp" in result.output
        assert "SKIP" in result.output
        assert "0 to create" in result.output or "to create" in result.output
        client.create_template.assert_not_called()
        client.update_template.assert_not_called()

    def test_creates_the_missing_templates(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "mtree.yml", "ntp.yml")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = [_raw()]
            result = _run(cfg, "sync", "--manifest", str(manifest))
        assert result.exit_code == 0
        assert client.create_template.call_count == 1
        kwargs = client.create_template.call_args.kwargs
        assert kwargs["name"] == "ntp"
        assert kwargs["repository_id"] == 3
        client.update_template.assert_not_called()

    def test_update_patches_only_the_drifted_template(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "mtree.yml")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = [_raw(view_id=None)]
            result = _run(cfg, "sync", "--manifest", str(manifest), "--update")
        assert result.exit_code == 0
        assert "view_id: 0 -> 2" in result.output
        assert client.update_template.call_args.kwargs["view_id"] == 2

    def test_update_is_a_noop_when_nothing_differs(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "mtree.yml")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = [_raw()]
            result = _run(cfg, "sync", "--manifest", str(manifest), "--update")
        assert "unchanged" in result.output
        client.update_template.assert_not_called()

    def test_orphans_are_reported_never_deleted(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "mtree.yml")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = [_raw(), _raw(id=7, name="legacy")]
            result = _run(cfg, "sync", "--manifest", str(manifest))
        assert "1 template(s) on the server are not in the manifest" in result.output
        client.delete_template.assert_not_called()

    def test_one_failure_does_not_stop_the_run(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "one.yml", "two.yml")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = []
            client.create_template.side_effect = [SemaphoreAPIError("boom"), Template(id=13)]
            result = _run(cfg, "sync", "--manifest", str(manifest))
        assert result.exit_code == 1
        assert "FAILED  one" in result.output
        assert client.create_template.call_count == 2

    def test_manifest_error_is_a_user_error(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        result = _run(cfg, "sync", "--manifest", str(tmp_path / "missing.yml"))
        assert result.exit_code == 2
        assert "manifest" in result.output

    def test_playbooks_flag_overrides_the_manifest(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "mtree.yml")
        other = tmp_path / "elsewhere"
        other.mkdir()
        (other / "solo.yml").write_text("---\n")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = []
            _run(cfg, "sync", "--manifest", str(manifest), "--playbooks", str(other), "--dry-run")
        assert client.create_template.call_count == 0

    def test_skip_mentions_the_pending_diff(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "mtree.yml")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = [_raw(view_id=None)]
            result = _run(cfg, "sync", "--manifest", str(manifest), "--dry-run")
        assert "field(s) differ — pass --update" in result.output

    def test_json_plan(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        manifest = _manifest(tmp_path, "mtree.yml")
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            client = _client(Mock)
            client.get_templates_raw.return_value = []
            result = _run(cfg, "--json", "sync", "--manifest", str(manifest), "--dry-run")
        payload = json.loads(result.output)
        assert payload["actions"][0]["verb"] == "create"
        assert payload["orphans"] == []
