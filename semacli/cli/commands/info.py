"""`sem info` — read server metadata from /api/info."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config

from .._groups import RawEpilogCommand
from ..decorators import common_options, output_options
from ..handlers import fail_on_error

INFO_HELP = """\
Print Semaphore server metadata.

Returns the version string from the server's /api/info endpoint.
No authentication required — useful for compatibility checks before
configuring a token.
"""

INFO_EPILOG = """\
Examples:
  sem info
  sem info --json
  sem -c ./staging.ini info
"""


@click.command("info", cls=RawEpilogCommand, help=INFO_HELP, epilog=INFO_EPILOG)
@common_options
@output_options
@fail_on_error
def info_cmd(config: str, verbose: int, output_json: bool, quiet: bool) -> None:
    """Print the server version from /api/info."""
    cfg = load_config(config)
    info = SemaphoreClient(cfg, verbose=verbose).get_info()
    if output_json:
        click.echo(json.dumps(info.model_dump(), indent=2))
    elif not quiet:
        click.echo(f"version: {info.version}")


def register_info_commands(main_group: Any) -> None:
    """Register the `info` command."""
    main_group.add_command(info_cmd)
    main_group.commands["info"].category = "connection"
