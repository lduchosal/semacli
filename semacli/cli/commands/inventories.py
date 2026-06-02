"""Inventories CRUD commands."""

from typing import Any

import click

from semacli.core.models import Inventory

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


def _read_content(path_or_text: str) -> str:
    """Resolve @file syntax: returns file contents if value starts with '@'."""
    if path_or_text.startswith("@"):
        with open(path_or_text[1:], encoding="utf-8") as f:
            return f.read()
    return path_or_text


def _fmt_row(i: Inventory) -> str:
    return f"{i.id:>4}  {i.name}  ({i.type or '?'})"


def _emit_show_text(i: Inventory) -> None:
    click.echo(f"id:            {i.id}")
    click.echo(f"name:          {i.name}")
    click.echo(f"type:          {i.type}")
    click.echo(f"project_id:    {i.project_id}")
    click.echo(f"ssh_key_id:    {i.ssh_key_id}")
    click.echo(f"become_key_id: {i.become_key_id}")
    if i.content:
        click.echo("content:")
        click.echo(i.content)


def register_inventories_commands(main_group: Any) -> None:
    """Register the `inventories` command group."""

    @main_group.group("inventories", invoke_without_command=True)
    @click.pass_context
    @common_options
    @output_options
    @project_option
    def inventories(
        ctx: click.Context,
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
        project_override: int | None,
    ) -> None:
        """List, show, create, update, delete inventories."""
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
            items = client.list_inventories(pid)
            if output_json:
                emit_json_list(items)
            elif not quiet:
                emit_text_list(items, "inventory(ies)", _fmt_row)
        except Exception as e:
            handle_error(e, verbose)

    @inventories.command("show")
    @click.argument("inventory_id", type=int)
    @click.pass_context
    def show_cmd(ctx: click.Context, inventory_id: int) -> None:
        """Show one inventory (including content)."""
        opts = opts_from_ctx(ctx)
        try:
            client, pid = setup(opts)
            item = client.get_inventory(pid, inventory_id)
            if opts["output_json"]:
                emit_json_single(item)
            elif not opts["quiet"]:
                _emit_show_text(item)
        except Exception as e:
            handle_error(e, opts["verbose"])

    @inventories.command("create")
    @click.option("--name", required=True, help="Inventory name")
    @click.option(
        "--type", "inv_type", required=True,
        type=click.Choice(["static", "file"]),
        help="Inventory type",
    )
    @click.option(
        "--content", required=True,
        help="Inventory content. Prefix with @ to read from a file.",
    )
    @click.option("--ssh-key-id", type=int, default=0)
    @click.option("--become-key-id", type=int, default=0)
    @click.pass_context
    def create_cmd(
        ctx: click.Context,
        name: str,
        inv_type: str,
        content: str,
        ssh_key_id: int,
        become_key_id: int,
    ) -> None:
        """Create an inventory."""
        opts = opts_from_ctx(ctx)
        try:
            client, pid = setup(opts)
            item = client.create_inventory(
                pid,
                name=name,
                type=inv_type,
                content=_read_content(content),
                ssh_key_id=ssh_key_id,
                become_key_id=become_key_id,
            )
            if opts["output_json"]:
                emit_json_single(item)
            elif not opts["quiet"]:
                click.echo(f"created inventory id={item.id}")
        except Exception as e:
            handle_error(e, opts["verbose"])

    @inventories.command("update")
    @click.argument("inventory_id", type=int)
    @click.option("--name", default=None)
    @click.option("--type", "inv_type", default=None, type=click.Choice(["static", "file"]))
    @click.option("--content", default=None, help="Prefix with @ to read from file.")
    @click.option("--ssh-key-id", type=int, default=None)
    @click.option("--become-key-id", type=int, default=None)
    @click.pass_context
    def update_cmd(
        ctx: click.Context,
        inventory_id: int,
        name: str | None,
        inv_type: str | None,
        content: str | None,
        ssh_key_id: int | None,
        become_key_id: int | None,
    ) -> None:
        """Update an inventory."""
        opts = opts_from_ctx(ctx)
        try:
            client, pid = setup(opts)
            client.update_inventory(
                pid,
                inventory_id,
                name=name,
                type=inv_type,
                inventory=_read_content(content) if content else None,
                ssh_key_id=ssh_key_id,
                become_key_id=become_key_id,
            )
            if not opts["quiet"]:
                click.echo(f"updated inventory id={inventory_id}")
        except Exception as e:
            handle_error(e, opts["verbose"])

    @inventories.command("delete")
    @click.argument("inventory_id", type=int)
    @click.option("--yes", is_flag=True, help="Skip confirmation prompt")
    @click.pass_context
    def delete_cmd(ctx: click.Context, inventory_id: int, yes: bool) -> None:
        """Delete an inventory."""
        opts = opts_from_ctx(ctx)
        try:
            client, pid = setup(opts)
            confirm_delete(yes, "inventory", inventory_id)
            client.delete_inventory(pid, inventory_id)
            if not opts["quiet"]:
                click.echo(f"deleted inventory id={inventory_id}")
        except Exception as e:
            handle_error(e, opts["verbose"])
