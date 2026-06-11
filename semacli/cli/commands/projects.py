"""Projects command for CLI."""

import json

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Project

from .._groups import AliasedGroup, SectionedRootGroup
from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import OutputFormatter, fail_on_error
from ._project_members import members_group

PROJECT_HELP = """\
Projects visible to your token.

A project is the top-level container — every inventory, repository,
environment, key, template, schedule and task belongs to exactly one
project. Set the default project once in semacli.ini ([semaphore]
project = <id>) so the other commands don't need -p each time.

Calling `sem project` without a subcommand lists projects.
"""

PROJECT_EPILOG = """\
Examples:
  sem project                                       # list
  sem project show 2
  sem project create --name infra-prod
  sem project update 2 --name infra-eu
  sem project delete 2
  sem project members -p 2                          # list members
  sem project members add --user 7 --role manager
  sem project --json | jq -r '.[].name'

Next steps:
  sem inv -p 2                inventories of project 2
  sem template -p 2           templates of project 2
"""


def _emit_projects_json(projects: list[Project]) -> None:
    """Emit the project list as a JSON array of id/name/created objects."""
    output = [{"id": p.id, "name": p.name, "created": p.created} for p in projects]
    click.echo(json.dumps(output, indent=2))


def _emit_projects_text(projects: list[Project]) -> None:
    """Emit the project list in compact text form, with an empty fallback + total line."""
    if not projects:
        click.echo("No projects found")
        return
    for p in projects:
        click.echo(f"{p.id:>4}  {p.name}")
    click.echo(f"\nTotal: {len(projects)} project(s)")


def _emit_project_show_json(p: Project) -> None:
    """Emit one project as a full JSON dump."""
    click.echo(json.dumps(p.model_dump(), indent=2))


def _emit_project_show_text(p: Project) -> None:
    """Emit one project as key-value lines."""
    click.echo(f"id:                 {p.id}")
    click.echo(f"name:               {p.name}")
    click.echo(f"created:            {p.created}")
    click.echo(f"alert:              {p.alert}")
    click.echo(f"alert_chat:         {p.alert_chat}")
    click.echo(f"max_parallel_tasks: {p.max_parallel_tasks}")


@click.group(
    "project",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=PROJECT_HELP,
    epilog=PROJECT_EPILOG,
)
@click.pass_context
@common_options
@output_options
@fail_on_error
def project_group(
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
) -> None:
    """List projects when invoked without a subcommand."""
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
    cfg = load_config(config)
    client = SemaphoreClient(cfg, verbose=verbose)
    OutputFormatter.format_verbose(f"Listing projects from {cfg.url}", verbose)
    projects = client.get_projects()
    if output_json:
        _emit_projects_json(projects)
    elif not quiet:
        _emit_projects_text(projects)


@project_group.command("show")
@click.argument("project_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, project_id: int) -> None:
    """Show one project with full metadata."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    p = SemaphoreClient(cfg, verbose=opts["verbose"]).get_project(project_id)
    if opts["output_json"]:
        _emit_project_show_json(p)
    elif not opts["quiet"]:
        _emit_project_show_text(p)


@project_group.command("create")
@click.option("--name", required=True)
@click.option("--alert/--no-alert", default=False)
@click.option("--alert-chat", default="", help="Slack/chat target for alerts")
@click.option("--max-parallel-tasks", default=0, type=int)
@click.pass_context
@fail_on_error
def create_cmd(
    ctx: click.Context,
    *,
    name: str,
    alert: bool,
    alert_chat: str,
    max_parallel_tasks: int,
) -> None:
    """Create a new project."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    p = SemaphoreClient(cfg, verbose=opts["verbose"]).create_project(
        name=name,
        alert=alert,
        alert_chat=alert_chat,
        max_parallel_tasks=max_parallel_tasks,
    )
    if opts["output_json"]:
        _emit_project_show_json(p)
    elif not opts["quiet"]:
        click.echo(f"created project id={p.id}")


@project_group.command("update")
@click.argument("project_id", type=int)
@click.option("--name", default=None)
@click.option("--alert/--no-alert", default=None)
@click.option("--alert-chat", default=None)
@click.option("--max-parallel-tasks", default=None, type=int)
@click.pass_context
@fail_on_error
def update_cmd(  # noqa: PLR0913 — one parameter per --option (click callback)
    ctx: click.Context,
    *,
    project_id: int,
    name: str | None,
    alert: bool | None,
    alert_chat: str | None,
    max_parallel_tasks: int | None,
) -> None:
    """Update mutable fields of a project."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    client.update_project(
        project_id,
        name=name,
        alert=alert,
        alert_chat=alert_chat,
        max_parallel_tasks=max_parallel_tasks,
    )
    if not opts["quiet"]:
        click.echo(f"updated project id={project_id}")


@project_group.command("delete")
@click.argument("project_id", type=int)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, project_id: int, *, yes: bool) -> None:
    """Delete a project and all its content. Irreversible."""
    opts = ctx.obj
    if not yes and not click.confirm(
        f"Delete project id={project_id} and ALL its inventories / templates / tasks?",
        default=False,
    ):
        click.echo("aborted.", err=True)
        return
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    client.delete_project(project_id)
    if not opts["quiet"]:
        click.echo(f"deleted project id={project_id}")


project_group.add_command(members_group)


@project_group.command("events")
@project_option
@click.pass_context
@fail_on_error
def events_cmd(ctx: click.Context, project_override: int | None) -> None:
    """List recent audit-log events of the project."""
    opts = ctx.obj
    opts["project_override"] = project_override
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, project_override)
    events = client.list_project_events(pid)
    if opts["output_json"]:
        click.echo(json.dumps([e.model_dump() for e in events], indent=2))
    elif not opts["quiet"]:
        if not events:
            click.echo("No events found")
            return
        for e in events:
            click.echo(
                f"{e.created}  user={e.user_id:<4}  " f"{e.object_type:<10}  {e.description}"
            )
        click.echo(f"\nTotal: {len(events)} event(s)")


@project_group.command("backup")
@project_option
@click.pass_context
@fail_on_error
def backup_cmd(ctx: click.Context, project_override: int | None) -> None:
    """Export the full project as a JSON document on stdout.

    The output is always JSON (regardless of --json). Redirect to a
    file to keep the backup; the format is what `semacli` would
    ingest in a future `restore` command.
    """
    opts = ctx.obj
    opts["project_override"] = project_override
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, project_override)
    data = client.export_project_backup(pid)
    click.echo(json.dumps(data, indent=2))


def register_projects_commands(main_group: SectionedRootGroup) -> None:
    """Register projects commands with the main CLI group."""
    main_group.add_command(project_group)
    main_group.set_category("project", "read")
    main_group.add_alias("projects", "project")
