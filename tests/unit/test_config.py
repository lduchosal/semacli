"""Tests for semacli.core.config."""

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
