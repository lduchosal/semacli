"""CLI decorators for semacli."""

from collections.abc import Callable
from typing import Any

import click

from semacli.core.config import SemaphoreConfig
from semacli.core.exceptions import ConfigurationError


def _inherit_verbose(ctx: click.Context, _param: click.Parameter, value: int) -> int:
    """Pull the root group's ``-v`` count if the subcommand received none.

    ``sem -vv ping`` → root captures 2, subcommand's own ``-v`` defaults to
    0, this callback returns 2.
    ``sem ping -vv``     → subcommand captures 2, returned as-is.
    ``sem -v ping -vv``  → subcommand value wins (2).
    """
    if value:
        return value
    parent = ctx.parent
    while parent is not None:
        if parent.obj and "verbose" in parent.obj:
            return int(parent.obj["verbose"])
        parent = parent.parent
    return 0


def common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for common CLI options."""
    func = click.option("-c", "--config", default="semacli.ini", help="Configuration file path")(
        func
    )
    func = click.option(
        "-v",
        "--verbose",
        count=True,
        callback=_inherit_verbose,
        help="Increase verbosity (inherits the root -v if not given here).",
    )(func)

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
