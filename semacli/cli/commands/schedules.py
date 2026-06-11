"""Cron schedules CRUD commands."""

from typing import Any

import click

from semacli.core.models import Schedule
from semacli.core.resolve import resolve_template

from .._crud import (
    confirm_delete,
    emit_json_list,
    emit_json_single,
    emit_text_list,
    opts_from_ctx,
    setup,
    store_opts,
)
from .._groups import AliasedGroup
from ..decorators import common_options, output_options, project_option
from ..handlers import fail_on_error

SCHED_HELP = """\
Schedules: cron triggers that launch a template on a recurring basis.

Each schedule points to exactly one template; deleting the template
invalidates the schedule. Cron format: standard 5-field POSIX, evaluated
in the server's timezone.

Calling `sem sched` without a subcommand lists schedules.
"""

SCHED_EPILOG = """\
Examples:
  sem sched                                          # list
  sem sched show 12
  sem sched create --template mtree --cron '0 3 * * *'  # nightly 3 am
  sem sched create --template 7 --cron '*/15 * * * *'   # by id
  sem sched update 12 --cron '0 4 * * *'
  sem sched delete 12
"""


def _fmt_row(s: Schedule) -> str:
    flag = "active" if s.active else "inactive"
    return f"{s.id:>4}  tpl={s.template_id}  {s.cron_format:<15}  {flag}  {s.name}"


def _emit_show_text(s: Schedule) -> None:
    click.echo(f"id:          {s.id}")
    click.echo(f"name:        {s.name}")
    click.echo(f"template_id: {s.template_id}")
    click.echo(f"cron_format: {s.cron_format}")
    click.echo(f"active:      {s.active}")
    click.echo(f"project_id:  {s.project_id}")


@click.group(
    "sched",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=SCHED_HELP,
    epilog=SCHED_EPILOG,
)
@click.pass_context
@common_options
@output_options
@project_option
@fail_on_error
def schedules(
    ctx: click.Context,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """List schedules when invoked without a subcommand."""
    store_opts(
        ctx,
        config=config,
        verbose=verbose,
        output_json=output_json,
        quiet=quiet,
        project_override=project_override,
    )
    if ctx.invoked_subcommand is not None:
        return
    client, pid = setup(opts_from_ctx(ctx))
    items = client.list_schedules(pid)
    if output_json:
        emit_json_list(items)
    elif not quiet:
        emit_text_list(items, "schedule(s)", _fmt_row)


@schedules.command("show")
@click.argument("sched_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, sched_id: int) -> None:
    """Show one schedule."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    item = client.get_schedule(pid, sched_id)
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        _emit_show_text(item)


@schedules.command("create")
@click.option(
    "--template",
    "template",
    required=True,
    help="Template name or numeric id (resolved against the project).",
)
@click.option(
    "--cron",
    "cron_format",
    required=True,
    help="Cron expression e.g. '0 3 * * *'",
)
@click.option("--name", default="")
@click.option("--inactive", is_flag=True, help="Create disabled")
@click.pass_context
@fail_on_error
def create_cmd(
    ctx: click.Context,
    template: str,
    cron_format: str,
    name: str,
    inactive: bool,
) -> None:
    """Create a cron schedule."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    template_id = resolve_template(client, pid, template)
    item = client.create_schedule(
        pid,
        template_id=template_id,
        cron_format=cron_format,
        name=name,
        active=not inactive,
    )
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        click.echo(f"created schedule id={item.id}")


@schedules.command("update")
@click.argument("sched_id", type=int)
@click.option("--name", default=None)
@click.option("--cron", "cron_format", default=None)
@click.option(
    "--active/--inactive",
    "active",
    default=None,
    help="Enable or disable the schedule",
)
@click.pass_context
@fail_on_error
def update_cmd(
    ctx: click.Context,
    sched_id: int,
    name: str | None,
    cron_format: str | None,
    active: bool | None,
) -> None:
    """Update a schedule."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    client.update_schedule(
        pid,
        sched_id,
        name=name,
        cron_format=cron_format,
        active=active,
    )
    if not opts["quiet"]:
        click.echo(f"updated schedule id={sched_id}")


@schedules.command("delete")
@click.argument("sched_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, sched_id: int, yes: bool) -> None:
    """Delete a schedule."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    confirm_delete(yes, "schedule", sched_id)
    client.delete_schedule(pid, sched_id)
    if not opts["quiet"]:
        click.echo(f"deleted schedule id={sched_id}")


def register_schedules_commands(main_group: Any) -> None:
    """Register the `sched` command group."""
    main_group.add_command(schedules)
    main_group.commands["sched"].category = "read"
    main_group.add_alias("schedules", "sched")
