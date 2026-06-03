"""CLI decorators for semacli."""

from collections.abc import Callable
from typing import Any

import click

from semacli.core.config import SemaphoreConfig
from semacli.core.exceptions import ConfigurationError


def common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for common CLI options."""
    func = click.option("-c", "--config", default="semacli.ini", help="Configuration file path")(
        func
    )
    func = click.option("-v", "--verbose", count=True, help="Increase verbosity")(func)

    return func


def output_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for output format options."""
    func = click.option("--json", "output_json", is_flag=True, help="Output as JSON")(func)
    func = click.option("-q", "--quiet", is_flag=True, help="Minimal output")(func)

    return func


def project_option(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for the --project flag (override config default)."""
    return click.option(
        "-p",
        "--project",
        "project_override",
        type=int,
        default=None,
        help="Project id (overrides [semaphore] project= in semacli.ini)",
    )(func)


def resolve_project(cfg: SemaphoreConfig, override: int | None) -> int:
    """Resolve the effective project id from CLI flag + config."""
    pid = override if override is not None else cfg.project
    if pid is None:
        raise ConfigurationError(
            "Project id required: pass --project N or set 'project = N' "
            "in the [semaphore] section of semacli.ini."
        )
    return pid
