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
