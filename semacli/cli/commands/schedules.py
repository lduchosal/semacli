"""Cron schedules CRUD commands."""

import click

from semacli.core.resolve import resolve_inventory, resolve_template

from .._crud import (
    confirm_delete,
    emit_json_list,
    emit_json_single,
    emit_text_list,
    opts_from_ctx,
    setup,
    store_opts,
)
from .._groups import AliasedGroup, SectionedRootGroup
from .._schedule_helpers import (
    CreateSpec,
    Overrides,
    UpdateSpec,
    emit_show_text,
    fmt_row,
    override_options,
    trigger_for_create,
    trigger_for_update,
)
from ..decorators import common_options, output_options, project_option
from ..handlers import fail_on_error

SCHED_HELP = """\
Schedules: triggers that launch a template automatically.

A schedule fires a template on a recurring cron expression (--cron) or
once at a future instant (--run-at). It can carry the same ansible
overrides as `sem run` — inventory, --limit, --tags, --skip-tags and raw
CLI args — so a planned run can target a subset of hosts WITHOUT a
dedicated template. --once makes the schedule delete itself after it
fires (a true one-shot).

Cron and run-at times are evaluated in the server's schedule timezone
(default UTC; set via SEMAPHORE_SCHEDULE_TIMEZONE or config schedule.timezone).

Calling `sem sched` without a subcommand lists schedules.
"""

SCHED_EPILOG = """\
Examples:
  sem sched                                          # list
  sem sched show 12
  sem sched create --template mtree --cron '0 3 * * *'  # nightly 3 am UTC
  sem sched create --template mtree --cron '0 3 * * *' \\
      --limit host1,host2 --tags pkg --inventory prod   # limited recurring run
  sem sched create --template mtree --run-at '2026-06-25 02:00' --once
  sem sched update 12 --limit host3 --skip-tags slow
  sem sched delete 12
"""


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
def schedules(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    *,
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
        emit_text_list(items, "schedule(s)", fmt_row)


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
        emit_show_text(item)


@fail_on_error
def _do_create(ctx: click.Context, spec: CreateSpec) -> None:
    """Resolve names and POST a new schedule (inside the error funnel)."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    template_id = resolve_template(client, pid, spec.template)
    ov = spec.overrides
    inv_id = resolve_inventory(client, pid, ov.inventory) if ov.inventory is not None else None
    item = client.create_schedule(
        pid,
        template_id=template_id,
        cron_format=spec.trigger.cron_format or "",
        name=spec.name,
        active=spec.active,
        schedule_type=spec.trigger.schedule_type,
        run_at=spec.trigger.run_at,
        delete_after_run=spec.delete_after_run,
        message=ov.message,
        inventory_id=inv_id,
        cli_args=ov.cli_args,
        limit=ov.limit,
        tags=ov.tags,
        skip_tags=ov.skip_tags,
    )
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        click.echo(f"created schedule id={item.id}")


@schedules.command("create")
@click.option(
    "--template",
    "template",
    required=True,
    help="Template name or numeric id (resolved against the project).",
)
@click.option("--cron", "cron_format", default=None, help="Cron expression e.g. '0 3 * * *'.")
@click.option(
    "--run-at",
    "run_at",
    default=None,
    help="One-shot trigger: RFC3339 or 'YYYY-MM-DD HH:MM' (UTC). Mutually exclusive with --cron.",
)
@click.option("--once", is_flag=True, help="Delete the schedule after it fires once.")
@click.option("--name", default="")
@click.option("--inactive", is_flag=True, help="Create disabled")
@override_options
@click.pass_context
def create_cmd(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    *,
    template: str,
    cron_format: str | None,
    run_at: str | None,
    once: bool,
    name: str,
    inactive: bool,
    inventory: str | None,
    limit: str | None,
    tags: str | None,
    skip_tags: str | None,
    cli_args: str | None,
    message: str | None,
) -> None:
    """Create a schedule (recurring --cron or one-shot --run-at)."""
    # Validate/normalize OUTSIDE the funnel so a UsageError stays a clean exit 2.
    trigger = trigger_for_create(cron_format, run_at)
    _do_create(
        ctx,
        CreateSpec(
            template=template,
            trigger=trigger,
            delete_after_run=once,
            name=name,
            active=not inactive,
            overrides=Overrides(inventory, limit, tags, skip_tags, cli_args, message),
        ),
    )


@fail_on_error
def _do_update(ctx: click.Context, spec: UpdateSpec) -> None:
    """Resolve names and PUT a schedule update (inside the error funnel)."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    ov = spec.overrides
    inv_id = resolve_inventory(client, pid, ov.inventory) if ov.inventory is not None else None
    client.update_schedule(
        pid,
        spec.sched_id,
        name=spec.name,
        cron_format=spec.trigger.cron_format,
        active=spec.active,
        schedule_type=spec.trigger.schedule_type,
        run_at=spec.trigger.run_at,
        delete_after_run=spec.delete_after_run,
        message=ov.message,
        inventory_id=inv_id,
        cli_args=ov.cli_args,
        limit=ov.limit,
        tags=ov.tags,
        skip_tags=ov.skip_tags,
    )
    if not opts["quiet"]:
        click.echo(f"updated schedule id={spec.sched_id}")


@schedules.command("update")
@click.argument("sched_id", type=int)
@click.option("--name", default=None)
@click.option("--cron", "cron_format", default=None, help="Cron expression e.g. '0 3 * * *'.")
@click.option(
    "--run-at",
    "run_at",
    default=None,
    help="Switch to one-shot: RFC3339 or 'YYYY-MM-DD HH:MM' (UTC). Mutually exclusive with --cron.",
)
@click.option("--active/--inactive", "active", default=None, help="Enable or disable the schedule")
@click.option("--once/--no-once", "once", default=None, help="Toggle delete-after-run (one-shot).")
@override_options
@click.pass_context
def update_cmd(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    *,
    sched_id: int,
    name: str | None,
    cron_format: str | None,
    run_at: str | None,
    active: bool | None,
    once: bool | None,
    inventory: str | None,
    limit: str | None,
    tags: str | None,
    skip_tags: str | None,
    cli_args: str | None,
    message: str | None,
) -> None:
    """Update a schedule (any subset of its fields)."""
    # Validate/normalize OUTSIDE the funnel so a UsageError stays a clean exit 2.
    trigger = trigger_for_update(cron_format, run_at)
    _do_update(
        ctx,
        UpdateSpec(
            sched_id=sched_id,
            trigger=trigger,
            name=name,
            active=active,
            delete_after_run=once,
            overrides=Overrides(inventory, limit, tags, skip_tags, cli_args, message),
        ),
    )


@schedules.command("delete")
@click.argument("sched_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, sched_id: int, *, yes: bool) -> None:
    """Delete a schedule."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    confirm_delete("schedule", sched_id, yes=yes)
    client.delete_schedule(pid, sched_id)
    if not opts["quiet"]:
        click.echo(f"deleted schedule id={sched_id}")


def register_schedules_commands(main_group: SectionedRootGroup) -> None:
    """Register the `sched` command group."""
    main_group.add_command(schedules)
    main_group.set_category("sched", "read")
    main_group.add_alias("schedules", "sched")
