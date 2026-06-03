"""Projects command for CLI."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Project

from ..decorators import common_options, output_options
from ..handlers import OutputFormatter, handle_error

PROJECT_HELP = """\
Projects visible to your token.

A project is the top-level container — every inventory, repository,
environment, key, template, schedule and task belongs to exactly one
project. Set the default project once in semacli.ini ([semaphore]
project = <id>) so the other commands don't need -p each time.
"""

PROJECT_EPILOG = """\
Examples:
  semacli project
  semacli project --json
  semacli project --json | jq -r '.[].name'

Next steps:
  semacli inv -p 2                inventories of project 2
  semacli template -p 2           templates of project 2
"""


def _emit_projects_json(projects: list[Project]) -> None:
    output = [{"id": p.id, "name": p.name, "created": p.created} for p in projects]
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

    @main_group.command("project", help=PROJECT_HELP, epilog=PROJECT_EPILOG)
    @common_options
    @output_options
    def project_cmd(
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
    ) -> None:
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)

            OutputFormatter.format_verbose(f"Listing projects from {cfg.url}", verbose)

            projects = client.get_projects()

            if output_json:
                _emit_projects_json(projects)
            elif not quiet:
                _emit_projects_text(projects)

        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["project"].category = "read"
    main_group.add_alias("projects", "project")
