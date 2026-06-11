"""Inventories CRUD commands."""

from pathlib import Path

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
from .._groups import AliasedGroup, SectionedRootGroup
from ..decorators import common_options, output_options, project_option
from ..handlers import fail_on_error

INV_HELP = """\
Inventories: lists of ansible hosts a template will target.

Each inventory belongs to one project. Templates pick one inventory.
Supported types: static (inline INI/YAML), file (a path inside the
repository), and none.

Calling `sem inv` without a subcommand lists inventories.
"""

INV_EPILOG = """\
Examples:
  sem inv                                # list
  sem inv show 42
  sem inv create --name prod-hosts --type static \\
       --inventory '[prod]\\nweb1'
  sem inv create --name from-file --type file \\
       --inventory ./hosts.ini       # path inside the repo
  sem inv update 42 --name prod-hosts-eu
  sem inv delete 42
"""


def _read_content(path_or_text: str) -> str:
    """Resolve @file syntax: returns file contents if value starts with '@'."""
    if path_or_text.startswith("@"):
        with Path(path_or_text[1:]).open(encoding="utf-8") as f:
            return f.read()
    return path_or_text


def _fmt_row(i: Inventory) -> str:
    """One aligned text row for the inventory list view."""
    return f"{i.id:>4}  {i.name}  ({i.type or '?'})"


def _emit_show_text(i: Inventory) -> None:
    """Emit one inventory as key-value lines, content last."""
    click.echo(f"id:            {i.id}")
    click.echo(f"name:          {i.name}")
    click.echo(f"type:          {i.type}")
    click.echo(f"project_id:    {i.project_id}")
    click.echo(f"ssh_key_id:    {i.ssh_key_id}")
    click.echo(f"become_key_id: {i.become_key_id}")
    if i.content:
        click.echo("content:")
        click.echo(i.content)


@click.group(
    "inv",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=INV_HELP,
    epilog=INV_EPILOG,
)
@click.pass_context
@common_options
@output_options
@project_option
@fail_on_error
def inventories(  # noqa: PLR0913 — one parameter per --option (click callback)
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """List inventories when invoked without a subcommand."""
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
    items = client.list_inventories(pid)
    if output_json:
        emit_json_list(items)
    elif not quiet:
        emit_text_list(items, "inventory(ies)", _fmt_row)


@inventories.command("show")
@click.argument("inventory_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, inventory_id: int) -> None:
    """Show one inventory (including content)."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    item = client.get_inventory(pid, inventory_id)
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        _emit_show_text(item)


@inventories.command("create")
@click.option("--name", required=True, help="Inventory name")
@click.option(
    "--type",
    "inv_type",
    required=True,
    type=click.Choice(["static", "file"]),
    help="Inventory type",
)
@click.option(
    "--inventory",
    "inventory",
    required=True,
    help=(
        "Inventory body. For --type static: inline INI/YAML (use @file "
        "to read from a local file). For --type file: a path inside the "
        "repository (no @)."
    ),
)
@click.option("--ssh-key-id", type=int, default=0)
@click.option("--become-key-id", type=int, default=0)
@click.pass_context
@fail_on_error
def create_cmd(  # noqa: PLR0913 — one parameter per --option (click callback)
    ctx: click.Context,
    name: str,
    inv_type: str,
    inventory: str,
    ssh_key_id: int,
    become_key_id: int,
) -> None:
    """Create an inventory."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    item = client.create_inventory(
        pid,
        name=name,
        type=inv_type,
        content=_read_content(inventory),
        ssh_key_id=ssh_key_id,
        become_key_id=become_key_id,
    )
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        click.echo(f"created inventory id={item.id}")


@inventories.command("update")
@click.argument("inventory_id", type=int)
@click.option("--name", default=None)
@click.option("--type", "inv_type", default=None, type=click.Choice(["static", "file"]))
@click.option(
    "--inventory",
    "inventory",
    default=None,
    help="New inventory body. Use @file to read inline content from a local file.",
)
@click.option("--ssh-key-id", type=int, default=None)
@click.option("--become-key-id", type=int, default=None)
@click.pass_context
@fail_on_error
def update_cmd(  # noqa: PLR0913 — one parameter per --option (click callback)
    ctx: click.Context,
    inventory_id: int,
    name: str | None,
    inv_type: str | None,
    inventory: str | None,
    ssh_key_id: int | None,
    become_key_id: int | None,
) -> None:
    """Update an inventory."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    client.update_inventory(
        pid,
        inventory_id,
        name=name,
        type=inv_type,
        inventory=_read_content(inventory) if inventory else None,
        ssh_key_id=ssh_key_id,
        become_key_id=become_key_id,
    )
    if not opts["quiet"]:
        click.echo(f"updated inventory id={inventory_id}")


@inventories.command("delete")
@click.argument("inventory_id", type=int)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, inventory_id: int, *, yes: bool) -> None:
    """Delete an inventory."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    confirm_delete("inventory", inventory_id, yes=yes)
    client.delete_inventory(pid, inventory_id)
    if not opts["quiet"]:
        click.echo(f"deleted inventory id={inventory_id}")


def register_inventories_commands(main_group: SectionedRootGroup) -> None:
    """Register the `inv` command group."""
    main_group.add_command(inventories)
    main_group.set_category("inv", "read")
    main_group.add_alias("inventories", "inv")
