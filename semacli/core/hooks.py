"""Configurable shell hooks fired before/after CLI commands.

Hooks are declared in the `[hook]` section of `semacli.ini`. Keys follow
the convention `<group>_<verb>_<event>` (e.g. `task_run_prehook`,
`task_run_posthook`, `task_run_failhook`). The value is a command line
parsed by `shlex.split`; relative paths are resolved against the
directory containing `semacli.ini`, so `../scripts/sync.sh` works
regardless of the caller's cwd.

A non-zero exit (or a timeout) from a prehook aborts the parent command
with exit code 6. Post/fail hook failures are logged but never block the
parent command, since by then it has already succeeded or already
failed for an unrelated reason.

Contextual information is exposed to the hook script as environment
variables (git-hook style): `SEMACLI_COMMAND`, `SEMACLI_GROUP`,
`SEMACLI_VERB`, `SEMACLI_EVENT`, `SEMACLI_CONFIG`, plus event-specific
keys like `SEMACLI_TEMPLATE`, `SEMACLI_LIMIT`, `SEMACLI_PROJECT`,
`SEMACLI_TASK_ID`, `SEMACLI_STATUS`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import click

from .exceptions import HookError


@dataclass
class HookSpec:
    """One configured hook: parsed argv + the original config key."""

    key: str
    argv: list[str]


@dataclass
class HookConfig:
    """Hooks loaded from the `[hook]` section.

    `hooks` maps the canonical key (e.g. `task_run_prehook`) to its
    `HookSpec`. Absent keys mean "no hook configured for this event"
    and are silently ignored at runtime.
    """

    hooks: dict[str, HookSpec] = field(default_factory=dict)
    timeout: int = 60


_RESERVED_KEYS = {"timeout"}


def parse_hook_config(section: dict[str, str], config_file: Path) -> HookConfig:
    """Parse a raw `[hook]` mapping into a `HookConfig`.

    Relative paths in hook commands are resolved against the directory
    of `config_file`. `timeout` is read as an int with a 60s default.
    Unknown keys are accepted as hook keys; we don't whitelist event
    names so that phase-2 events (e.g. `template_create_prehook`) can
    be added without touching the parser.
    """
    config_dir = config_file.parent.resolve()
    hooks: dict[str, HookSpec] = {}
    timeout = 60

    for key, raw_value in section.items():
        if key in _RESERVED_KEYS:
            if key == "timeout":
                try:
                    timeout = int(raw_value)
                except ValueError as exc:
                    raise ValueError(
                        f"[hook] timeout must be an integer, got {raw_value!r}"
                    ) from exc
            continue

        value = raw_value.strip()
        if not value:
            continue

        argv = shlex.split(value)
        if not argv:
            continue

        argv[0] = _resolve_path(argv[0], config_dir)
        hooks[key] = HookSpec(key=key, argv=argv)

    return HookConfig(hooks=hooks, timeout=timeout)


def _resolve_path(path: str, config_dir: Path) -> str:
    """Resolve a hook command path relative to the config dir.

    Absolute paths are returned as-is. A bare command (no `/`) is left
    alone so the OS PATH lookup applies (e.g. `task_run_prehook = curl`).
    """
    if Path(path).is_absolute():
        return path
    if "/" not in path and "\\" not in path:
        return path
    return str((config_dir / path).resolve())


def run_hook(
    hook_cfg: HookConfig | None,
    key: str,
    env_extra: dict[str, str],
    *,
    verbose: int = 0,
    enabled: bool = True,
) -> None:
    """Run the hook named `key` if configured.

    `env_extra` is merged on top of `os.environ` and exposed to the
    subprocess. `verbose >= 1` streams the hook's stdout/stderr to the
    parent terminal; otherwise the output is captured and only printed
    on failure.

    Raises `HookError` when a prehook-style failure should abort the
    parent command. Callers that want fire-and-forget semantics (post
    and fail hooks) should catch and log this exception.
    """
    if not enabled or hook_cfg is None:
        return
    spec = hook_cfg.hooks.get(key)
    if spec is None:
        return

    env = os.environ.copy()
    env.update(env_extra)
    env["SEMACLI_EVENT"] = key

    if verbose >= 1:
        click.echo(f"DEBUG: hook {key} -> {shlex.join(spec.argv)}", err=True)

    try:
        result = subprocess.run(
            spec.argv,
            env=env,
            timeout=hook_cfg.timeout,
            capture_output=verbose < 1,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HookError(f"hook {key}: command not found: {spec.argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HookError(f"hook {key}: timed out after {hook_cfg.timeout}s") from exc

    if result.returncode != 0:
        captured = ""
        if verbose < 1:
            if result.stdout:
                captured += f"\n--- stdout ---\n{result.stdout.rstrip()}"
            if result.stderr:
                captured += f"\n--- stderr ---\n{result.stderr.rstrip()}"
        raise HookError(f"hook {key}: exit {result.returncode}{captured}")


def warn_hook_failure(error: HookError, key: str) -> None:
    """Report a non-blocking hook failure on stderr.

    Used for post/fail hooks where the parent command has already
    finished and shouldn't be derailed by hook misbehaviour.
    """
    click.echo(f"warning: hook {key} failed: {error}", err=True)
