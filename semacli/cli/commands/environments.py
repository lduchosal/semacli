"""Environments CRUD commands."""

from pathlib import Path
from typing import Any

import click

from semacli.core.models import Environment

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

ENV_HELP = """\
Environments: extra_vars and secrets passed to a playbook at runtime.

Each environment belongs to one project. Templates may reference one.
Variables are stored as a JSON object — use '@file.json' to load from
disk. The optional --password field is the vault password Semaphore
injects as VAULT_PASSWORD when the playbook runs.

Calling `sem env` without a subcommand lists environments.
"""

ENV_EPILOG = """\
Examples:
  sem env                                    # list
  sem env show 7
  sem env create --name prod \\
       --vars '{"region":"eu-west-1"}'
  sem env create --name prod --vars @vars.json --password 'vault-pw'
  sem env update 7 --vars @vars.json
  sem env delete 7
"""


def _read_json(path_or_text: str) -> str:
    """Resolve @file syntax: returns file contents if value starts with '@'."""
    if path_or_text.startswith("@"):
        with Path(path_or_text[1:]).open(encoding="utf-8") as f:
            return f.read()
    return path_or_text


def _fmt_row(e: Environment) -> str:
    """One aligned text row for the environment list view."""
    return f"{e.id:>4}  {e.name}"


def _emit_show_text(e: Environment) -> None:
    """Emit one environment as key-value lines, secrets masked, vars JSON last."""
    click.echo(f"id:         {e.id}")
    click.echo(f"name:       {e.name}")
    click.echo(f"project_id: {e.project_id}")
    if e.password:
        click.echo("password:   <set>")
    if e.vars_json:
        click.echo("json:")
        click.echo(e.vars_json)


@click.group(
    "env",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=ENV_HELP,
    epilog=ENV_EPILOG,
)
@click.pass_context
@common_options
@output_options
@project_option
@fail_on_error
def environments(
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """List environments when invoked without a subcommand."""
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
    items = client.list_environments(pid)
    if output_json:
        emit_json_list(items)
    elif not quiet:
        emit_text_list(items, "environment(s)", _fmt_row)


@environments.command("show")
@click.argument("env_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, env_id: int) -> None:
    """Show one environment."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    item = client.get_environment(pid, env_id)
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        _emit_show_text(item)


@environments.command("create")
@click.option("--name", required=True)
@click.option(
    "--vars",
    "json_vars",
    required=True,
    help="Variables as a JSON object. Prefix with @ to read from a file.",
)
@click.option("--password", default="")
@click.pass_context
@fail_on_error
def create_cmd(ctx: click.Context, name: str, json_vars: str, password: str) -> None:
    """Create an environment."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    item = client.create_environment(
        pid,
        name=name,
        json_vars=_read_json(json_vars),
        password=password,
    )
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        click.echo(f"created environment id={item.id}")


@environments.command("update")
@click.argument("env_id", type=int)
@click.option("--name", default=None)
@click.option(
    "--vars",
    "json_vars",
    default=None,
    help="Variables as a JSON object. Prefix with @ to read from file. Replaces wholesale.",
)
@click.option("--password", default=None)
@click.pass_context
@fail_on_error
def update_cmd(
    ctx: click.Context,
    env_id: int,
    name: str | None,
    json_vars: str | None,
    password: str | None,
) -> None:
    """Update an environment."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    client.update_environment(
        pid,
        env_id,
        name=name,
        json=_read_json(json_vars) if json_vars else None,
        password=password,
    )
    if not opts["quiet"]:
        click.echo(f"updated environment id={env_id}")


@environments.command("delete")
@click.argument("env_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, env_id: int, *, yes: bool) -> None:
    """Delete an environment."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    confirm_delete("environment", env_id, yes=yes)
    client.delete_environment(pid, env_id)
    if not opts["quiet"]:
        click.echo(f"deleted environment id={env_id}")


def register_environments_commands(main_group: Any) -> None:
    """Register the `env` command group."""
    main_group.add_command(environments)
    main_group.commands["env"].category = "read"
    main_group.add_alias("environments", "env")
