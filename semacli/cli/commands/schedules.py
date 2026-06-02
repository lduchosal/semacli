"""Cron schedules CRUD commands."""

from typing import Any

import click

from semacli.core.models import Schedule

from .._crud import (
    confirm_delete,
    emit_json_list,
    emit_json_single,
    emit_text_list,
    opts_from_ctx,
    setup,
    store_opts,
)
from ..decorators import common_options, output_options, project_option
from ..handlers import handle_error


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


def register_schedules_commands(main_group: Any) -> None:
    """Register the `schedules` command group."""

    @main_group.group("schedules", invoke_without_command=True)
    @click.pass_context
    @common_options
    @output_options
    @project_option
    def schedules(
        ctx: click.Context,
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
        project_override: int | None,
    ) -> None:
        """List, show, create, update, delete cron schedules."""
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
        try:
            client, pid = setup(opts_from_ctx(ctx))
            items = client.list_schedules(pid)
            if output_json:
                emit_json_list(items)
            elif not quiet:
                emit_text_list(items, "schedule(s)", _fmt_row)
        except Exception as e:
            handle_error(e, verbose)

    @schedules.command("show")
    @click.argument("sched_id", type=int)
    @click.pass_context
    def show_cmd(ctx: click.Context, sched_id: int) -> None:
        """Show one schedule."""
        opts = opts_from_ctx(ctx)
        try:
            client, pid = setup(opts)
            item = client.get_schedule(pid, sched_id)
            if opts["output_json"]:
                emit_json_single(item)
            elif not opts["quiet"]:
                _emit_show_text(item)
        except Exception as e:
            handle_error(e, opts["verbose"])

    @schedules.command("create")
    @click.option("--template-id", required=True, type=int)
    @click.option(
        "--cron", "cron_format", required=True,
        help="Cron expression e.g. '0 3 * * *'",
    )
    @click.option("--name", default="")
    @click.option("--inactive", is_flag=True, help="Create disabled")
    @click.pass_context
    def create_cmd(
        ctx: click.Context,
        template_id: int,
        cron_format: str,
        name: str,
        inactive: bool,
    ) -> None:
        """Create a cron schedule."""
        opts = opts_from_ctx(ctx)
        try:
            client, pid = setup(opts)
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
        except Exception as e:
            handle_error(e, opts["verbose"])

    @schedules.command("update")
    @click.argument("sched_id", type=int)
    @click.option("--name", default=None)
    @click.option("--cron", "cron_format", default=None)
    @click.option(
        "--active/--inactive", "active", default=None,
        help="Enable or disable the schedule",
    )
    @click.pass_context
    def update_cmd(
        ctx: click.Context,
        sched_id: int,
        name: str | None,
        cron_format: str | None,
        active: bool | None,
    ) -> None:
        """Update a schedule."""
        opts = opts_from_ctx(ctx)
        try:
            client, pid = setup(opts)
            client.update_schedule(
                pid, sched_id,
                name=name,
                cron_format=cron_format,
                active=active,
            )
            if not opts["quiet"]:
                click.echo(f"updated schedule id={sched_id}")
        except Exception as e:
            handle_error(e, opts["verbose"])

    @schedules.command("delete")
    @click.argument("sched_id", type=int)
    @click.option("--yes", is_flag=True)
    @click.pass_context
    def delete_cmd(ctx: click.Context, sched_id: int, yes: bool) -> None:
        """Delete a schedule."""
        opts = opts_from_ctx(ctx)
        try:
            client, pid = setup(opts)
            confirm_delete(yes, "schedule", sched_id)
            client.delete_schedule(pid, sched_id)
            if not opts["quiet"]:
                click.echo(f"deleted schedule id={sched_id}")
        except Exception as e:
            handle_error(e, opts["verbose"])
