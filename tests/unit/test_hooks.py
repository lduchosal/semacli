"""Tests for semacli.core.hooks."""

import os
import textwrap
from pathlib import Path

import pytest

from semacli.core.exceptions import HookError
from semacli.core.hooks import HookConfig, parse_hook_config, run_hook, warn_hook_failure


def _write_hook(tmp_path: Path, name: str, body: str, mode: int = 0o755) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body).lstrip())
    os.chmod(path, mode)
    return path


def _ini_file(tmp_path: Path) -> Path:
    """A placeholder semacli.ini used only for path-resolution context."""
    path = tmp_path / "semacli.ini"
    path.write_text("[semaphore]\nurl=https://x\n")
    return path


class TestParseHookConfig:
    def test_empty_section_yields_defaults(self, tmp_path: Path) -> None:
        cfg = parse_hook_config({}, _ini_file(tmp_path))
        assert cfg.hooks == {}
        assert cfg.timeout == 60

    def test_absolute_path_kept_as_is(self, tmp_path: Path) -> None:
        hook = _write_hook(tmp_path, "h.sh", "#!/bin/sh\nexit 0\n")
        cfg = parse_hook_config({"task_run_prehook": str(hook)}, _ini_file(tmp_path))
        assert cfg.hooks["task_run_prehook"].argv == [str(hook)]

    def test_relative_path_resolved_against_config_dir(self, tmp_path: Path) -> None:
        sub = tmp_path / "scripts"
        sub.mkdir()
        hook = _write_hook(sub, "sync.sh", "#!/bin/sh\nexit 0\n")
        cfg = parse_hook_config({"task_run_prehook": "scripts/sync.sh"}, _ini_file(tmp_path))
        assert cfg.hooks["task_run_prehook"].argv == [str(hook.resolve())]

    def test_parent_relative_path_resolved(self, tmp_path: Path) -> None:
        inner = tmp_path / "inner"
        inner.mkdir()
        ini = inner / "semacli.ini"
        ini.write_text("x")
        hook = _write_hook(tmp_path, "outer.sh", "#!/bin/sh\nexit 0\n")
        cfg = parse_hook_config({"task_run_prehook": "../outer.sh"}, ini)
        assert cfg.hooks["task_run_prehook"].argv[0] == str(hook.resolve())

    def test_shlex_splits_arguments(self, tmp_path: Path) -> None:
        cfg = parse_hook_config(
            {"task_run_prehook": "scripts/sync.sh --tier 2 'with space'"},
            _ini_file(tmp_path),
        )
        argv = cfg.hooks["task_run_prehook"].argv
        assert argv[1:] == ["--tier", "2", "with space"]

    def test_bare_command_left_for_path_lookup(self, tmp_path: Path) -> None:
        cfg = parse_hook_config(
            {"task_run_prehook": "curl --silent https://x"}, _ini_file(tmp_path)
        )
        assert cfg.hooks["task_run_prehook"].argv[0] == "curl"

    def test_empty_value_ignored(self, tmp_path: Path) -> None:
        cfg = parse_hook_config({"task_run_prehook": "   "}, _ini_file(tmp_path))
        assert "task_run_prehook" not in cfg.hooks

    def test_timeout_parsed(self, tmp_path: Path) -> None:
        cfg = parse_hook_config({"timeout": "15"}, _ini_file(tmp_path))
        assert cfg.timeout == 15

    def test_invalid_timeout_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="timeout"):
            parse_hook_config({"timeout": "fast"}, _ini_file(tmp_path))

    def test_unknown_keys_become_hooks(self, tmp_path: Path) -> None:
        # Forward-compatible: phase-2 keys parse without code changes.
        cfg = parse_hook_config({"template_create_prehook": "/bin/true"}, _ini_file(tmp_path))
        assert "template_create_prehook" in cfg.hooks


class TestRunHook:
    def test_none_config_is_no_op(self) -> None:
        run_hook(None, "task_run_prehook", {}, verbose=0)

    def test_disabled_short_circuits(self, tmp_path: Path) -> None:
        # Path that would fail if it actually ran — we expect early return.
        cfg = HookConfig(
            hooks={
                "task_run_prehook": _spec(["/does-not-exist/anywhere"]),
            }
        )
        run_hook(cfg, "task_run_prehook", {}, enabled=False)

    def test_missing_hook_is_no_op(self) -> None:
        run_hook(HookConfig(), "task_run_prehook", {})

    def test_zero_exit_runs_silently(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        hook = _write_hook(tmp_path, "ok.sh", "#!/bin/sh\necho hello; exit 0\n")
        cfg = HookConfig(hooks={"task_run_prehook": _spec([str(hook)])})
        run_hook(cfg, "task_run_prehook", {}, verbose=0)
        out = capsys.readouterr()
        # Output is captured at verbose=0 — stdout silent.
        assert "hello" not in out.out

    def test_nonzero_exit_raises_hook_error(self, tmp_path: Path) -> None:
        hook = _write_hook(tmp_path, "bad.sh", "#!/bin/sh\necho oops >&2; exit 7\n")
        cfg = HookConfig(hooks={"task_run_prehook": _spec([str(hook)])})
        with pytest.raises(HookError) as exc:
            run_hook(cfg, "task_run_prehook", {})
        assert "exit 7" in str(exc.value)
        assert "oops" in str(exc.value)

    def test_command_not_found_raises_hook_error(self) -> None:
        cfg = HookConfig(hooks={"task_run_prehook": _spec(["/no/such/binary/here"])})
        with pytest.raises(HookError, match="command not found"):
            run_hook(cfg, "task_run_prehook", {})

    def test_timeout_raises_hook_error(self, tmp_path: Path) -> None:
        hook = _write_hook(tmp_path, "slow.sh", "#!/bin/sh\nsleep 5\n")
        cfg = HookConfig(hooks={"task_run_prehook": _spec([str(hook)])}, timeout=1)
        with pytest.raises(HookError, match="timed out"):
            run_hook(cfg, "task_run_prehook", {})

    def test_env_extra_passed_to_subprocess(self, tmp_path: Path) -> None:
        out = tmp_path / "captured"
        hook = _write_hook(
            tmp_path,
            "env.sh",
            f"""
            #!/bin/sh
            printenv SEMACLI_TEMPLATE > {out}
            exit 0
            """,
        )
        cfg = HookConfig(hooks={"task_run_prehook": _spec([str(hook)])})
        run_hook(cfg, "task_run_prehook", {"SEMACLI_TEMPLATE": "mtree"})
        assert out.read_text().strip() == "mtree"

    def test_event_env_var_always_set(self, tmp_path: Path) -> None:
        out = tmp_path / "ev"
        hook = _write_hook(
            tmp_path,
            "ev.sh",
            f"""
            #!/bin/sh
            printenv SEMACLI_EVENT > {out}
            exit 0
            """,
        )
        cfg = HookConfig(hooks={"task_run_posthook": _spec([str(hook)])})
        run_hook(cfg, "task_run_posthook", {})
        assert out.read_text().strip() == "task_run_posthook"

    def test_verbose_streams_output(
        self, tmp_path: Path, capfd: pytest.CaptureFixture[str]
    ) -> None:
        # capfd (not capsys) — subprocess writes to inherited fds.
        hook = _write_hook(tmp_path, "out.sh", "#!/bin/sh\necho streamed; exit 0\n")
        cfg = HookConfig(hooks={"task_run_prehook": _spec([str(hook)])})
        run_hook(cfg, "task_run_prehook", {}, verbose=1)
        out = capfd.readouterr()
        assert "streamed" in out.out


def test_warn_hook_failure_writes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    warn_hook_failure(HookError("boom"), "task_run_posthook")
    out = capsys.readouterr()
    assert "task_run_posthook" in out.err
    assert "boom" in out.err


def _spec(argv: list[str]) -> object:
    """Minimal HookSpec stand-in (we import the real class lazily)."""
    from semacli.core.hooks import HookSpec

    return HookSpec(key="x", argv=argv)
