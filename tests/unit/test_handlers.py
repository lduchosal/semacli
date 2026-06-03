"""Tests for semacli.cli.handlers."""

import pytest

from semacli.cli.handlers import OutputFormatter, handle_error
from semacli.core.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NotFoundError,
    SemaphoreAPIError,
)


class TestHandleError:
    def test_configuration_error_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            handle_error(ConfigurationError("missing url"))
        assert exc.value.code == 2
        assert "Configuration error" in capsys.readouterr().err

    def test_authentication_error_exits_3(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            handle_error(AuthenticationError("bad token"))
        assert exc.value.code == 3
        assert "Authentication error" in capsys.readouterr().err

    def test_api_error_exits_4(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            handle_error(SemaphoreAPIError("500"))
        assert exc.value.code == 4
        assert "API error" in capsys.readouterr().err

    def test_not_found_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            handle_error(NotFoundError("project 42"))
        assert exc.value.code == 2
        assert "error:" in capsys.readouterr().err

    def test_generic_error_exits_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            handle_error(RuntimeError("boom"))
        assert exc.value.code == 1
        assert "Error:" in capsys.readouterr().err

    def test_verbose_prints_debug(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            handle_error(ConfigurationError("oops"), verbose=1)
        err = capsys.readouterr().err
        assert "DEBUG: ConfigurationError" in err


class TestOutputFormatter:
    def test_format_verbose_suppressed_below_threshold(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        OutputFormatter.format_verbose("hello", verbose_level=0)
        assert capsys.readouterr().err == ""

    def test_format_verbose_emitted_at_threshold(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter.format_verbose("hello", verbose_level=1)
        assert "DEBUG: hello" in capsys.readouterr().err

    def test_format_verbose_custom_min_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        OutputFormatter.format_verbose("deep", verbose_level=2, min_level=3)
        assert capsys.readouterr().err == ""
        OutputFormatter.format_verbose("deep", verbose_level=3, min_level=3)
        assert "DEBUG: deep" in capsys.readouterr().err
