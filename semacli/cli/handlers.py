"""Error handlers and formatters for click CLI."""

import sys
from typing import NoReturn

import click

from semacli.core.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NotFoundError,
    SemaphoreAPIError,
)


def handle_error(error: Exception, verbose: int = 0) -> NoReturn:
    """Handle exceptions and exit with appropriate code.

    Exit codes:
        1 - General error
        2 - Configuration error
        3 - Authentication error
        4 - API error
        5 - Not found
    """
    if verbose >= 1:
        click.echo(f"DEBUG: {type(error).__name__}: {error}", err=True)

    if isinstance(error, ConfigurationError):
        click.echo(f"Configuration error: {error}", err=True)
        sys.exit(2)
    elif isinstance(error, AuthenticationError):
        click.echo(f"Authentication error: {error}", err=True)
        sys.exit(3)
    elif isinstance(error, SemaphoreAPIError):
        click.echo(f"API error: {error}", err=True)
        sys.exit(4)
    elif isinstance(error, NotFoundError):
        click.echo(f"Not found: {error}", err=True)
        sys.exit(5)
    else:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)


class OutputFormatter:
    """Output formatters for different verbosity levels."""

    @staticmethod
    def format_verbose(message: str, verbose_level: int, min_level: int = 1) -> None:
        """Print message if verbosity is high enough."""
        if verbose_level >= min_level:
            click.echo(f"DEBUG: {message}", err=True)
