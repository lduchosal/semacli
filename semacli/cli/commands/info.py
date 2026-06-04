"""`semacli info` — read server metadata from /api/info."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config

from ..decorators import common_options, output_options
from ..handlers import handle_error

INFO_HELP = """\
Print Semaphore server metadata.

Returns the version string from the server's /api/info endpoint.
No authentication required — useful for compatibility checks before
configuring a token.
"""

INFO_EPILOG = """\
Examples:
  semacli info
  semacli info --json
  semacli -c ./staging.ini info
"""


def register_info_commands(main_group: Any) -> None:
    """Register the `info` command."""

    @main_group.command("info", help=INFO_HELP, epilog=INFO_EPILOG)
    @common_options
    @output_options
    def info_cmd(config: str, verbose: int, output_json: bool, quiet: bool) -> None:
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)
            info = client.get_info()
            if output_json:
                click.echo(json.dumps(info.model_dump(), indent=2))
            elif not quiet:
                click.echo(f"version: {info.version}")
        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["info"].category = "connection"
