"""Tests for the `sem integration` command group and its `matchers` subgroup."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.exceptions import SemaphoreAPIError
from semacli.core.models import Integration, IntegrationMatcher


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


def _integration(**overrides: object) -> Integration:
    base: dict = {
        "id": 4,
        "project_id": 1,
        "name": "gh-push",
        "template_id": 5,
        "auth_method": "github",
        "auth_header": "",
        "auth_secret_id": 12,
    }
    base.update(overrides)
    return Integration(**base)


def _matcher(**overrides: object) -> IntegrationMatcher:
    base: dict = {
        "id": 7,
        "integration_id": 4,
        "name": "only-main",
        "match_type": "equals",
        "method": "body",
        "key": "ref",
        "value": "refs/heads/main",
    }
    base.update(overrides)
    return IntegrationMatcher(**base)


class TestIntegrationList:
    def test_bare_group_lists_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_integrations.return_value = [_integration()]
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "gh-push" in r.output
        assert "Total: 1 integration(s)" in r.output
        Mock.return_value.list_integrations.assert_called_once_with(1)

    def test_bare_group_lists_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_integrations.return_value = [_integration()]
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg), "--json"])
        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload[0]["name"] == "gh-push"
        assert payload[0]["template_id"] == 5

    def test_empty_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_integrations.return_value = []
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg)])
        assert r.exit_code == 0
        assert "No integrations found" in r.output

    def test_integrations_alias(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_integrations.return_value = []
            r = CliRunner().invoke(main, ["integrations", "-c", str(cfg)])
        assert r.exit_code == 0
        Mock.return_value.list_integrations.assert_called_once_with(1)


class TestIntegrationShow:
    def test_show_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_integration.return_value = _integration()
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg), "show", "4"])
        assert r.exit_code == 0
        assert "gh-push" in r.output
        assert "auth_method:    github" in r.output
        Mock.return_value.get_integration.assert_called_once_with(1, 4)

    def test_show_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.get_integration.return_value = _integration()
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg), "--json", "show", "4"])
        assert r.exit_code == 0
        assert json.loads(r.output)["auth_secret_id"] == 12


class TestIntegrationCreate:
    def test_create(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_integration.return_value = _integration(id=8)
            r = CliRunner().invoke(
                main,
                [
                    "integration",
                    "-c",
                    str(cfg),
                    "create",
                    "--name",
                    "gh-push",
                    "--template",
                    "5",
                    "--auth-method",
                    "github",
                    "--auth-secret-id",
                    "12",
                ],
            )
        assert r.exit_code == 0
        assert "created integration id=8" in r.output
        Mock.return_value.create_integration.assert_called_once_with(
            1,
            name="gh-push",
            template_id=5,
            auth_method="github",
            auth_header="",
            auth_secret_id=12,
        )

    def test_create_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.create_integration.return_value = _integration(id=8)
            r = CliRunner().invoke(
                main,
                [
                    "integration",
                    "-c",
                    str(cfg),
                    "--json",
                    "create",
                    "--name",
                    "gh-push",
                    "--template",
                    "5",
                ],
            )
        assert r.exit_code == 0
        assert json.loads(r.output)["id"] == 8


class TestIntegrationUpdate:
    def test_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(
                main,
                ["integration", "-c", str(cfg), "update", "4", "--template", "8"],
            )
        assert r.exit_code == 0
        assert "updated integration id=4" in r.output
        Mock.return_value.update_integration.assert_called_once_with(
            1,
            4,
            name=None,
            template_id=8,
            auth_method=None,
            auth_header=None,
            auth_secret_id=None,
        )


class TestIntegrationDelete:
    def test_delete_with_yes(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg), "delete", "4", "--yes"])
        assert r.exit_code == 0
        assert "deleted integration id=4" in r.output
        Mock.return_value.delete_integration.assert_called_once_with(1, 4)

    def test_delete_declined_prompt_aborts(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(
                main, ["integration", "-c", str(cfg), "delete", "4"], input="n\n"
            )
        assert r.exit_code == 0
        Mock.return_value.delete_integration.assert_not_called()


class TestIntegrationMatchers:
    def test_matchers_list_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_integration_matchers.return_value = [_matcher()]
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg), "matchers", "4"])
        assert r.exit_code == 0
        assert "only-main" in r.output
        assert "Total: 1 matcher(s)" in r.output
        Mock.return_value.list_integration_matchers.assert_called_once_with(1, 4)

    def test_matchers_list_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_integration_matchers.return_value = [_matcher()]
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg), "--json", "matchers", "4"])
        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload[0]["key"] == "ref"

    def test_matchers_empty_list(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_integration_matchers.return_value = []
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg), "matchers", "4"])
        assert r.exit_code == 0
        assert "No matchers found" in r.output

    def test_matchers_add(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.add_integration_matcher.return_value = _matcher(id=7)
            r = CliRunner().invoke(
                main,
                [
                    "integration",
                    "-c",
                    str(cfg),
                    "matchers",
                    "4",
                    "add",
                    "--name",
                    "only-main",
                    "--match-type",
                    "equals",
                    "--method",
                    "body",
                    "--key",
                    "ref",
                    "--value",
                    "refs/heads/main",
                ],
            )
        assert r.exit_code == 0
        assert "added matcher id=7" in r.output
        Mock.return_value.add_integration_matcher.assert_called_once_with(
            1,
            4,
            name="only-main",
            match_type="equals",
            method="body",
            key="ref",
            value="refs/heads/main",
        )

    def test_matchers_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(
                main,
                [
                    "integration",
                    "-c",
                    str(cfg),
                    "matchers",
                    "4",
                    "update",
                    "7",
                    "--value",
                    "refs/heads/release",
                ],
            )
        assert r.exit_code == 0
        assert "updated matcher id=7" in r.output
        Mock.return_value.update_integration_matcher.assert_called_once_with(
            1,
            4,
            7,
            name=None,
            match_type=None,
            method=None,
            key=None,
            value="refs/heads/release",
        )

    def test_matchers_remove_with_yes(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(
                main,
                ["integration", "-c", str(cfg), "matchers", "4", "remove", "7", "--yes"],
            )
        assert r.exit_code == 0
        assert "removed matcher id=7" in r.output
        Mock.return_value.remove_integration_matcher.assert_called_once_with(1, 4, 7)

    def test_matchers_remove_declined_prompt_aborts(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            r = CliRunner().invoke(
                main,
                ["integration", "-c", str(cfg), "matchers", "4", "remove", "7"],
                input="n\n",
            )
        assert r.exit_code == 0
        Mock.return_value.remove_integration_matcher.assert_not_called()


class TestIntegrationErrors:
    def test_api_error_exits_4(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli._crud.SemaphoreClient") as Mock:
            Mock.return_value.list_integrations.side_effect = SemaphoreAPIError("boom")
            r = CliRunner().invoke(main, ["integration", "-c", str(cfg)])
        assert r.exit_code == 4
