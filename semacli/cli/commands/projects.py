"""Projects command for CLI."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Project

from ..decorators import common_options, output_options
from ..handlers import OutputFormatter, handle_error


def _emit_projects_json(projects: list[Project]) -> None:
    output = [
        {"id": p.id, "name": p.name, "created": p.created}
        for p in projects
    ]
    click.echo(json.dumps(output, indent=2))


def _emit_projects_text(projects: list[Project]) -> None:
    if not projects:
        click.echo("No projects found")
        return
    for p in projects:
        click.echo(f"{p.id:>4}  {p.name}")
    click.echo(f"\nTotal: {len(projects)} project(s)")


def register_projects_commands(main_group: Any) -> None:
    """Register projects commands with the main CLI group."""

    @main_group.command("projects")
    @common_options
    @output_options
    def projects_cmd(
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
    ) -> None:
        """List all Semaphore projects."""
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)

            OutputFormatter.format_verbose(f"Listing projects from {cfg.url}", verbose)

            projects = client.get_projects()

            if output_json:
                _emit_projects_json(projects)
            elif quiet:
                pass
            else:
                _emit_projects_text(projects)

        except Exception as e:
            handle_error(e, verbose)
