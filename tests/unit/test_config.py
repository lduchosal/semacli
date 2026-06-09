"""Tests for semacli.core.config."""

import os
import textwrap
from pathlib import Path

import pytest

from semacli.core.config import SemaphoreConfig, load_config
from semacli.core.exceptions import ConfigurationError


def _write_ini(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "semacli.ini"
    path.write_text(textwrap.dedent(body).lstrip())
    return path


class TestLoadConfig:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError):
            load_config(str(tmp_path / "nope.ini"))

    def test_bearer_token_method(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example/

            [auth]
            method = bearer_token
            bearer_token = abc123

            [settings]
            timeout = 42
            verify_ssl = false
            """,
        )
        cfg = load_config(str(ini))
        assert isinstance(cfg, SemaphoreConfig)
        assert cfg.url == "https://semaphore.example"
        assert cfg.bearer_token == "abc123"
        assert cfg.timeout == 42
        assert cfg.verify_ssl is False

    def test_env_var_method(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEMA_TOKEN_X", "from-env")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example

            [auth]
            method = env_var
            env_var = SEMA_TOKEN_X
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.bearer_token == "from-env"

    def test_missing_url_raises(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            project = 1
            """,
        )
        with pytest.raises(ConfigurationError):
            load_config(str(ini))

    def test_project_parsed_as_int(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            project = 7
            bearer_token = t
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.project == 7

    def test_allow_http_default_false(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.allow_http is False
        assert cfg.verify_ssl is True

    def test_http_url_rejected_by_default(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = http://semaphore.example
            bearer_token = t
            """,
        )
        with pytest.raises(ConfigurationError, match="Plain HTTP"):
            load_config(str(ini))

    def test_hook_section_parsed(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t

            [hook]
            task_run_prehook = /bin/true
            task_run_posthook = /bin/false
            timeout = 15
            """,
        )
        cfg = load_config(str(ini))
        assert "task_run_prehook" in cfg.hooks.hooks
        assert "task_run_posthook" in cfg.hooks.hooks
        assert cfg.hooks.timeout == 15

    def test_hook_section_absent_yields_empty_config(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.hooks.hooks == {}
        assert cfg.hooks.timeout == 60

    def test_hook_invalid_timeout_raises_configuration_error(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t

            [hook]
            timeout = soon
            """,
        )
        with pytest.raises(ConfigurationError, match="timeout"):
            load_config(str(ini))

    def test_load_dotenv_disabled_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SEMA_FROM_DOTENV", raising=False)
        (tmp_path / ".env").write_text("SEMA_FROM_DOTENV=should-not-load\n")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t
            """,
        )
        load_config(str(ini))
        assert "SEMA_FROM_DOTENV" not in os.environ

    def test_load_dotenv_true_injects_from_adjacent_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SEMA_FROM_DOTENV", raising=False)
        (tmp_path / ".env").write_text("SEMA_FROM_DOTENV=loaded-value\n")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example

            [auth]
            method = env_var
            env_var = SEMA_FROM_DOTENV

            [settings]
            load_dotenv = true
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.bearer_token == "loaded-value"

    def test_load_dotenv_missing_file_is_silent_noop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SEMA_FROM_DOTENV", raising=False)
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t

            [settings]
            load_dotenv = true
            """,
        )
        load_config(str(ini))  # no .env present, no error

    def test_load_dotenv_does_not_override_existing_shell_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SEMA_FROM_DOTENV", "from-shell")
        (tmp_path / ".env").write_text("SEMA_FROM_DOTENV=from-dotenv\n")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example

            [auth]
            method = env_var
            env_var = SEMA_FROM_DOTENV

            [settings]
            load_dotenv = true
            """,
        )
        cfg = load_config(str(ini))
        # shell wins (override=False)
        assert cfg.bearer_token == "from-shell"

    def test_load_dotenv_file_relative_to_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SEMA_FROM_DOTENV", raising=False)
        sub = tmp_path / "secrets"
        sub.mkdir()
        (sub / "team.env").write_text("SEMA_FROM_DOTENV=team-value\n")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example

            [auth]
            method = env_var
            env_var = SEMA_FROM_DOTENV

            [settings]
            load_dotenv = true
            load_dotenv_file = secrets/team.env
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.bearer_token == "team-value"

    def test_load_dotenv_file_absolute_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SEMA_FROM_DOTENV", raising=False)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        env_file = elsewhere / "abs.env"
        env_file.write_text("SEMA_FROM_DOTENV=absolute-value\n")
        ini = _write_ini(
            tmp_path,
            f"""
            [semaphore]
            url = https://semaphore.example

            [auth]
            method = env_var
            env_var = SEMA_FROM_DOTENV

            [settings]
            load_dotenv = true
            load_dotenv_file = {env_file}
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.bearer_token == "absolute-value"

    def test_load_dotenv_warns_on_world_readable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("SEMA_FROM_DOTENV", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("SEMA_FROM_DOTENV=v\n")
        os.chmod(env_file, 0o644)  # group/world-readable
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t

            [settings]
            load_dotenv = true
            """,
        )
        load_config(str(ini))
        err = capsys.readouterr().err
        assert "chmod 600" in err

    def test_use_system_ca_auto_off_on_linux(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.platform", "linux")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.use_system_ca is False

    def test_use_system_ca_auto_on_on_windows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.platform", "win32")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.use_system_ca is True

    def test_use_system_ca_auto_explicit_on_linux(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.platform", "linux")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t

            [settings]
            use_system_ca = auto
            """,
        )
        cfg = load_config(str(ini))
        # `auto` matches absent-key behaviour.
        assert cfg.use_system_ca is False

    def test_use_system_ca_true_forces_on_anywhere(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.platform", "linux")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t

            [settings]
            use_system_ca = true
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.use_system_ca is True

    def test_use_system_ca_false_forces_off_on_windows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.platform", "win32")
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t

            [settings]
            use_system_ca = false
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.use_system_ca is False

    def test_use_system_ca_invalid_value_raises(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = https://semaphore.example
            bearer_token = t

            [settings]
            use_system_ca = maybe
            """,
        )
        with pytest.raises(ConfigurationError, match="use_system_ca"):
            load_config(str(ini))

    def test_http_url_allowed_with_flag(self, tmp_path: Path) -> None:
        ini = _write_ini(
            tmp_path,
            """
            [semaphore]
            url = http://semaphore.example
            bearer_token = t

            [settings]
            allow_http = true
            """,
        )
        cfg = load_config(str(ini))
        assert cfg.allow_http is True
        assert cfg.url == "http://semaphore.example"
