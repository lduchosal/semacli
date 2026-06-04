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

Calling `semacli project` without a subcommand lists projects.
"""

PROJECT_EPILOG = """\
Examples:
  semacli project                                       # list
  semacli project show 2
  semacli project create --name infra-prod
  semacli project update 2 --name infra-eu
  semacli project delete 2
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


def _emit_project_show_json(p: Project) -> None:
    click.echo(json.dumps(p.model_dump(), indent=2))


def _emit_project_show_text(p: Project) -> None:
    click.echo(f"id:                 {p.id}")
    click.echo(f"name:               {p.name}")
    click.echo(f"created:            {p.created}")
    click.echo(f"alert:              {p.alert}")
    click.echo(f"alert_chat:         {p.alert_chat}")
    click.echo(f"max_parallel_tasks: {p.max_parallel_tasks}")


def register_projects_commands(main_group: Any) -> None:
    """Register projects commands with the main CLI group."""

    @main_group.group(
        "project", invoke_without_command=True, help=PROJECT_HELP, epilog=PROJECT_EPILOG
    )
    @click.pass_context
    @common_options
    @output_options
    def project_group(
        ctx: click.Context,
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
    ) -> None:
        ctx.ensure_object(dict)
        ctx.obj.update(
            {
                "config": config,
                "verbose": verbose,
                "output_json": output_json,
                "quiet": quiet,
            }
        )
        if ctx.invoked_subcommand is not None:
            return
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

    @project_group.command("show")
    @click.argument("project_id", type=int)
    @click.pass_context
    def show_cmd(ctx: click.Context, project_id: int) -> None:
        """Show one project with full metadata."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            p = client.get_project(project_id)
            if opts["output_json"]:
                _emit_project_show_json(p)
            elif not opts["quiet"]:
                _emit_project_show_text(p)
        except Exception as e:
            handle_error(e, verbose)

    @project_group.command("create")
    @click.option("--name", required=True)
    @click.option("--alert/--no-alert", default=False)
    @click.option("--alert-chat", default="", help="Slack/chat target for alerts")
    @click.option("--max-parallel-tasks", default=0, type=int)
    @click.pass_context
    def create_cmd(
        ctx: click.Context,
        name: str,
        alert: bool,
        alert_chat: str,
        max_parallel_tasks: int,
    ) -> None:
        """Create a new project."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            p = client.create_project(
                name=name,
                alert=alert,
                alert_chat=alert_chat,
                max_parallel_tasks=max_parallel_tasks,
            )
            if opts["output_json"]:
                _emit_project_show_json(p)
            elif not opts["quiet"]:
                click.echo(f"created project id={p.id}")
        except Exception as e:
            handle_error(e, verbose)

    @project_group.command("update")
    @click.argument("project_id", type=int)
    @click.option("--name", default=None)
    @click.option("--alert/--no-alert", default=None)
    @click.option("--alert-chat", default=None)
    @click.option("--max-parallel-tasks", default=None, type=int)
    @click.pass_context
    def update_cmd(
        ctx: click.Context,
        project_id: int,
        name: str | None,
        alert: bool | None,
        alert_chat: str | None,
        max_parallel_tasks: int | None,
    ) -> None:
        """Update mutable fields of a project."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            client.update_project(
                project_id,
                name=name,
                alert=alert,
                alert_chat=alert_chat,
                max_parallel_tasks=max_parallel_tasks,
            )
            if not opts["quiet"]:
                click.echo(f"updated project id={project_id}")
        except Exception as e:
            handle_error(e, verbose)

    @project_group.command("delete")
    @click.argument("project_id", type=int)
    @click.option("--yes", is_flag=True, help="Skip confirmation")
    @click.pass_context
    def delete_cmd(ctx: click.Context, project_id: int, yes: bool) -> None:
        """Delete a project and all its content. Irreversible."""
        opts = ctx.obj
        verbose = opts["verbose"]
        if not yes and not click.confirm(
            f"Delete project id={project_id} and ALL its inventories / templates / tasks?",
            default=False,
        ):
            click.echo("aborted.", err=True)
            return
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            client.delete_project(project_id)
            if not opts["quiet"]:
                click.echo(f"deleted project id={project_id}")
        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["project"].category = "read"
    main_group.add_alias("projects", "project")
