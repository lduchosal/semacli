"""Tests for the `sem project members` and `sem user admin` satellite groups."""

import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from semacli.cli import main
from semacli.core.exceptions import SemaphoreAPIError
from semacli.core.models import ProjectMember, User


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


def _member(uid: int = 7, role: str = "owner") -> ProjectMember:
    return ProjectMember(user_id=uid, project_id=1, role=role, name="Luc", username="luc")


class TestProjectMembers:
    def test_bare_group_lists_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._project_members.SemaphoreClient") as mock:
            mock.return_value.list_project_members.return_value = [_member()]
            r = CliRunner().invoke(main, ["project", "-c", str(cfg), "members"])
        assert r.exit_code == 0
        assert "luc" in r.output

    def test_bare_group_lists_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._project_members.SemaphoreClient") as mock:
            mock.return_value.list_project_members.return_value = [_member()]
            r = CliRunner().invoke(main, ["project", "-c", str(cfg), "--json", "members"])
        assert r.exit_code == 0
        assert '"role": "owner"' in r.output

    def test_bare_group_empty(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._project_members.SemaphoreClient") as mock:
            mock.return_value.list_project_members.return_value = []
            r = CliRunner().invoke(main, ["project", "-c", str(cfg), "members"])
        assert r.exit_code == 0
        assert "No members found" in r.output

    def test_add(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._project_members.SemaphoreClient") as mock:
            r = CliRunner().invoke(
                main,
                ["project", "-c", str(cfg), "members", "add", "--user", "7", "--role", "manager"],
            )
        assert r.exit_code == 0
        mock.return_value.add_project_member.assert_called_once_with(1, user_id=7, role="manager")

    def test_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._project_members.SemaphoreClient") as mock:
            r = CliRunner().invoke(
                main,
                ["project", "-c", str(cfg), "members", "update", "7", "--role", "guest"],
            )
        assert r.exit_code == 0
        mock.return_value.update_project_member.assert_called_once_with(1, user_id=7, role="guest")

    def test_remove_with_yes(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._project_members.SemaphoreClient") as mock:
            r = CliRunner().invoke(
                main, ["project", "-c", str(cfg), "members", "remove", "7", "--yes"]
            )
        assert r.exit_code == 0
        mock.return_value.remove_project_member.assert_called_once_with(1, user_id=7)

    def test_api_error_exits_4(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._project_members.SemaphoreClient") as mock:
            mock.return_value.list_project_members.side_effect = SemaphoreAPIError("boom")
            r = CliRunner().invoke(main, ["project", "-c", str(cfg), "members"])
        assert r.exit_code == 4


def _user(uid: int = 3, *, admin: bool = False) -> User:
    return User(id=uid, name="Luc D", username="luc", email="luc@example.org", admin=admin)


class TestUserAdmin:
    def test_bare_group_lists_text(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_admin.SemaphoreClient") as mock:
            mock.return_value.list_users.return_value = [_user(), _user(4, admin=True)]
            r = CliRunner().invoke(main, ["user", "-c", str(cfg), "admin"])
        assert r.exit_code == 0
        assert "luc" in r.output

    def test_list_cmd_json(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_admin.SemaphoreClient") as mock:
            mock.return_value.list_users.return_value = [_user()]
            r = CliRunner().invoke(main, ["user", "-c", str(cfg), "--json", "admin", "list"])
        assert r.exit_code == 0
        assert '"username": "luc"' in r.output

    def test_show(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_admin.SemaphoreClient") as mock:
            mock.return_value.get_user.return_value = _user()
            r = CliRunner().invoke(main, ["user", "-c", str(cfg), "admin", "show", "3"])
        assert r.exit_code == 0
        assert "luc@example.org" in r.output

    def test_create(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_admin.SemaphoreClient") as mock:
            mock.return_value.create_user.return_value = _user()
            r = CliRunner().invoke(
                main,
                [
                    "user",
                    "-c",
                    str(cfg),
                    "admin",
                    "create",
                    "--username",
                    "luc",
                    "--name",
                    "Luc D",
                    "--email",
                    "luc@example.org",
                    "--password",
                    "s3cret",
                    "--admin",
                ],
            )
        assert r.exit_code == 0
        mock.return_value.create_user.assert_called_once_with(
            username="luc", name="Luc D", email="luc@example.org", password="s3cret", admin=True
        )

    def test_update(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_admin.SemaphoreClient") as mock:
            r = CliRunner().invoke(
                main, ["user", "-c", str(cfg), "admin", "update", "3", "--email", "new@example.org"]
            )
        assert r.exit_code == 0
        assert mock.return_value.update_user.called

    def test_delete_with_yes(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_admin.SemaphoreClient") as mock:
            r = CliRunner().invoke(main, ["user", "-c", str(cfg), "admin", "delete", "3", "--yes"])
        assert r.exit_code == 0
        mock.return_value.delete_user.assert_called_once_with(3)

    def test_set_password(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_admin.SemaphoreClient") as mock:
            r = CliRunner().invoke(
                main,
                ["user", "-c", str(cfg), "admin", "set-password", "3"],
                input="np\nnp\n",
            )
        assert r.exit_code == 0
        assert mock.return_value.set_user_password.called

    def test_api_error_exits_4(self, tmp_path: Path) -> None:
        cfg = _write_cfg(tmp_path)
        with patch("semacli.cli.commands._user_admin.SemaphoreClient") as mock:
            mock.return_value.get_user.side_effect = SemaphoreAPIError("boom")
            r = CliRunner().invoke(main, ["user", "-c", str(cfg), "admin", "show", "3"])
        assert r.exit_code == 4
