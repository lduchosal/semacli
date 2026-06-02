"""CLI decorators for semacli."""

from collections.abc import Callable
from typing import Any

import click


def common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for common CLI options."""
    func = click.option(
        "-c", "--config", default="semacli.ini", help="Configuration file path"
    )(func)
    func = click.option("-v", "--verbose", count=True, help="Increase verbosity")(func)

    return func


def output_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for output format options."""
    func = click.option("--json", "output_json", is_flag=True, help="Output as JSON")(func)
    func = click.option("-q", "--quiet", is_flag=True, help="Minimal output")(func)

    return func
