"""CLI module for semacli."""

import click

from semacli import __version__

from .commands import register_all_commands


@click.group()
@click.version_option(version=__version__, prog_name="semacli")
def main() -> None:
    """Semaphore CLI - Manage Semaphore UI via HTTP REST API."""
    pass


register_all_commands(main)
