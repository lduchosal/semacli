"""Ping command for CLI."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config

from .._groups import RawEpilogCommand
from ..decorators import common_options, output_options
from ..handlers import OutputFormatter, fail_on_error

PING_HELP = """\
Check that the Semaphore server is reachable.

No authentication required — useful as a first sanity check before
generating a token, or to verify the URL in semacli.ini. Exits 0 on
success, non-zero on failure.
"""

PING_EPILOG = """\
Examples:
  sem ping
  sem ping --json
  sem -c ./staging.ini ping
  sem -vv ping
  sem ping -q && echo OK
"""


@click.command("ping", cls=RawEpilogCommand, help=PING_HELP, epilog=PING_EPILOG)
@common_options
@output_options
@fail_on_error
def ping_cmd(
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
) -> None:
    """Check server reachability via the public ping endpoint."""
    cfg = load_config(config)
    client = SemaphoreClient(cfg, verbose=verbose)

    OutputFormatter.format_verbose(f"Pinging {cfg.url}", verbose)

    pong = client.ping()

    if output_json:
        click.echo(json.dumps({"ping": pong}))
    elif not quiet:
        click.echo(pong)


def register_ping_commands(main_group: Any) -> None:
    """Register ping commands with the main CLI group."""
    main_group.add_command(ping_cmd)
    main_group.commands["ping"].category = "connection"
