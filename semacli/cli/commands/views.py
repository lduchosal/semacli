"""`sem view` — saved filters / dashboards inside a project."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import View

from .._groups import AliasedGroup
from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import fail_on_error

VIEW_HELP = """\
Views: saved filters / dashboards scoped to a project.

A view groups templates and tasks together for quick navigation in the
Semaphore UI. Each view belongs to one project; the `position` field
controls display order.

Calling `sem view` without a subcommand lists views.
"""

VIEW_EPILOG = """\
Examples:
  sem view                                       # list
  sem view show 3
  sem view create --title 'Nightly jobs' --position 0
  sem view update 3 --position 1
  sem view delete 3
"""


def _emit_list_text(views: list[View]) -> None:
    """Emit the view list sorted by position, with an empty fallback + total line."""
    if not views:
        click.echo("No views found")
        return
    for v in sorted(views, key=lambda x: x.position):
        click.echo(f"{v.id:>4}  pos={v.position:<3}  {v.title}")
    click.echo(f"\nTotal: {len(views)} view(s)")


def _emit_show_text(v: View) -> None:
    """Emit one view as key-value lines."""
    click.echo(f"id:         {v.id}")
    click.echo(f"title:      {v.title}")
    click.echo(f"position:   {v.position}")
    click.echo(f"project_id: {v.project_id}")


def _setup(opts: dict[str, Any]) -> tuple[SemaphoreClient, int]:
    """Resolve config, client, and project_id from the stored group opts."""
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, opts["project_override"])
    return client, pid


@click.group(
    "view",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=VIEW_HELP,
    epilog=VIEW_EPILOG,
)
@click.pass_context
@common_options
@output_options
@project_option
@fail_on_error
def view_group(
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """List views when invoked without a subcommand."""
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "config": config,
            "verbose": verbose,
            "output_json": output_json,
            "quiet": quiet,
            "project_override": project_override,
        }
    )
    if ctx.invoked_subcommand is not None:
        return
    client, pid = _setup(ctx.obj)
    views = client.list_views(pid)
    if output_json:
        click.echo(json.dumps([v.model_dump() for v in views], indent=2))
    elif not quiet:
        _emit_list_text(views)


@view_group.command("show")
@click.argument("view_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, view_id: int) -> None:
    """Show one view."""
    opts = ctx.obj
    client, pid = _setup(opts)
    v = client.get_view(pid, view_id)
    if opts["output_json"]:
        click.echo(json.dumps(v.model_dump(), indent=2))
    elif not opts["quiet"]:
        _emit_show_text(v)


@view_group.command("create")
@click.option("--title", required=True)
@click.option("--position", default=0, type=int, help="Display order; lower comes first.")
@click.pass_context
@fail_on_error
def create_cmd(ctx: click.Context, title: str, position: int) -> None:
    """Create a view."""
    opts = ctx.obj
    client, pid = _setup(opts)
    v = client.create_view(pid, title=title, position=position)
    if opts["output_json"]:
        click.echo(json.dumps(v.model_dump(), indent=2))
    elif not opts["quiet"]:
        click.echo(f"created view id={v.id}")


@view_group.command("update")
@click.argument("view_id", type=int)
@click.option("--title", default=None)
@click.option("--position", default=None, type=int)
@click.pass_context
@fail_on_error
def update_cmd(
    ctx: click.Context,
    view_id: int,
    title: str | None,
    position: int | None,
) -> None:
    """Update mutable fields of a view."""
    opts = ctx.obj
    client, pid = _setup(opts)
    client.update_view(pid, view_id, title=title, position=position)
    if not opts["quiet"]:
        click.echo(f"updated view id={view_id}")


@view_group.command("delete")
@click.argument("view_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, view_id: int, *, yes: bool) -> None:
    """Delete a view."""
    opts = ctx.obj
    if not yes and not click.confirm(f"Delete view id={view_id}?", default=False):
        click.echo("aborted.", err=True)
        return
    client, pid = _setup(opts)
    client.delete_view(pid, view_id)
    if not opts["quiet"]:
        click.echo(f"deleted view id={view_id}")


def register_views_commands(main_group: Any) -> None:
    """Register `sem view`."""
    main_group.add_command(view_group)
    main_group.commands["view"].category = "read"
    main_group.add_alias("views", "view")
