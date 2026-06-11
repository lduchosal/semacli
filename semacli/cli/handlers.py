"""Error handlers and formatters for click CLI."""

import functools
import sys
from collections.abc import Callable
from typing import Any, NoReturn

import click

from semacli.core.exceptions import (
    AmbiguousNameError,
    AuthenticationError,
    ConfigurationError,
    HookError,
    NotFoundError,
    OverrideNotAllowedError,
    SemaphoreAPIError,
)


def handle_error(error: Exception, verbose: int = 0) -> NoReturn:
    """Handle exceptions and exit with appropriate code.

    Exit codes:
        1 - General error
        2 - Configuration error / user error (unknown name, ambiguous)
        3 - Authentication error
        4 - API error
        5 - Not found
        6 - Hook abort (pre-hook returned non-zero or timed out)
    """
    if verbose >= 1:
        click.echo(f"DEBUG: {type(error).__name__}: {error}", err=True)

    if isinstance(error, ConfigurationError):
        click.echo(f"Configuration error: {error}", err=True)
        sys.exit(2)
    elif isinstance(error, AuthenticationError):
        click.echo(f"Authentication error: {error}", err=True)
        sys.exit(3)
    elif isinstance(error, AmbiguousNameError):
        click.echo(f"error: {error}", err=True)
        sys.exit(2)
    elif isinstance(error, NotFoundError):
        click.echo(f"error: {error}", err=True)
        sys.exit(2)
    elif isinstance(error, OverrideNotAllowedError):
        click.echo(f"error: {error}", err=True)
        sys.exit(2)
    elif isinstance(error, SemaphoreAPIError):
        click.echo(f"API error: {error}", err=True)
        sys.exit(4)
    elif isinstance(error, HookError):
        click.echo(f"error: {error}", err=True)
        sys.exit(6)
    else:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)


def fail_on_error(func: Callable[..., None]) -> Callable[..., None]:
    """Route any command failure through ``handle_error``.

    Single funnel for the CLI's exit-code contract: command callbacks
    drop their per-command ``try/except`` and the one blanket catch
    lives here, so the BLE001 lint lock stays meaningful everywhere
    else. Verbosity is read from the callback kwargs when present,
    falling back to the group options stashed on ``ctx.obj``.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        """Run the wrapped callback, funneling any exception to ``handle_error``."""
        try:
            func(*args, **kwargs)
        except Exception as error:  # noqa: BLE001 — the CLI-wide funnel to handle_error
            ctx = click.get_current_context(silent=True)
            opts = (ctx.obj if ctx else None) or {}
            verbose = kwargs.get("verbose") or opts.get("verbose", 0)
            handle_error(error, verbose)

    return wrapper


class OutputFormatter:
    """Output formatters for different verbosity levels."""

    @staticmethod
    def format_verbose(message: str, verbose_level: int, min_level: int = 1) -> None:
        """Print message if verbosity is high enough."""
        if verbose_level >= min_level:
            click.echo(f"DEBUG: {message}", err=True)
