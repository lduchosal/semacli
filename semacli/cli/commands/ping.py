"""Ping command for CLI."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config

from ..decorators import common_options, output_options
from ..handlers import OutputFormatter, handle_error


def register_ping_commands(main_group: Any) -> None:
    """Register ping commands with the main CLI group."""

    @main_group.command("ping")
    @common_options
    @output_options
    def ping_cmd(
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
    ) -> None:
        """Ping the Semaphore API (GET /api/ping)."""
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)

            OutputFormatter.format_verbose(f"Pinging {cfg.url}", verbose)

            pong = client.ping()

            if output_json:
                click.echo(json.dumps({"ping": pong}))
            elif not quiet:
                click.echo(pong)

        except Exception as e:
            handle_error(e, verbose)
