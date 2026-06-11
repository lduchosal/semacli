"""Access keys CRUD commands (SSH, login_password, none)."""

from pathlib import Path
from typing import Any

import click

from semacli.core.models import Key

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

KEY_HELP = """\
Access keys: credentials Semaphore stores to talk to repos, hosts and
vaults.

Three types:
  - ssh             SSH private key (used by repo clones, by hosts that
                    require key-based auth)
  - login_password  username + password (used by HTTPS deploy tokens,
                    registry logins)
  - none            secret-only key (vault password, become password)

Secrets (private key bodies, passwords) are write-only: they can be set
on create/update but are never returned by show.

Calling `sem key` without a subcommand lists keys.
"""

KEY_EPILOG = """\
Examples:
  sem key                                            # list
  sem key show 12                                    # metadata only
  sem key create --name deploy-ssh --type ssh \\
       --private-key @~/.ssh/id_ed25519
  sem key create --name vault-pw --type none --password 's3cr3t'
  sem key create --name reg-login --type login_password \\
       --login admin --password 's3cr3t'
  sem key delete 12
"""


def _read_private_key(path_or_text: str) -> str:
    """Resolve @file syntax: returns file contents if value starts with '@'."""
    if path_or_text.startswith("@"):
        with Path(path_or_text[1:]).open(encoding="utf-8") as f:
            return f.read()
    return path_or_text


def _split_login(login_password: str) -> tuple[str, str]:
    """Parse 'user:pass' into (user, pass). Empty string → ('', '')."""
    if ":" not in login_password:
        return login_password, ""
    user, _, pwd = login_password.partition(":")
    return user, pwd


def _fmt_row(k: Key) -> str:
    """One aligned text row for the key list view."""
    return f"{k.id:>4}  {k.name}  ({k.type})"


def _emit_show_text(k: Key) -> None:
    """Emit one key as key-value lines; secret values are never shown."""
    click.echo(f"id:         {k.id}")
    click.echo(f"name:       {k.name}")
    click.echo(f"type:       {k.type}")
    click.echo(f"project_id: {k.project_id}")
    click.echo("(secret values are never returned by the API)")


def _create_kwargs(
    name: str,
    key_type: str,
    ssh_key: str,
    login: str,
    password: str,
    passphrase: str,
) -> dict[str, Any]:
    """Build the create_key payload for the given key type."""
    kwargs: dict[str, Any] = {"name": name, "type": key_type}
    if key_type == "ssh":
        kwargs["login"] = login
        kwargs["passphrase"] = passphrase
        kwargs["private_key"] = _read_private_key(ssh_key)
    elif key_type == "login_password":
        # Prefer the explicit --password flag; fall back to splitting
        # a legacy 'user:pass' --login value if --password is empty.
        if password:
            kwargs["login"] = login
            kwargs["password"] = password
        else:
            user, pwd = _split_login(login)
            kwargs["login"] = user
            kwargs["password"] = pwd
    elif key_type == "none":
        kwargs["password"] = password
    return kwargs


@click.group(
    "key",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=KEY_HELP,
    epilog=KEY_EPILOG,
)
@click.pass_context
@common_options
@output_options
@project_option
@fail_on_error
def keys(
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """List keys when invoked without a subcommand."""
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
    items = client.list_keys(pid)
    if output_json:
        emit_json_list(items)
    elif not quiet:
        emit_text_list(items, "key(s)", _fmt_row)


@keys.command("show")
@click.argument("key_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, key_id: int) -> None:
    """Show one key (metadata only — secrets are never returned)."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    item = client.get_key(pid, key_id)
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        _emit_show_text(item)


@keys.command("create")
@click.option("--name", required=True)
@click.option(
    "--type",
    "key_type",
    required=True,
    type=click.Choice(["ssh", "login_password", "none"]),
)
@click.option(
    "--private-key",
    "ssh_key",
    default="",
    help="SSH private key body (or @file). Required for type=ssh.",
)
@click.option(
    "--login",
    default="",
    help=(
        "For type=ssh: ssh login. For type=login_password: username "
        "(legacy: 'user:pass' is split if --password is not given)."
    ),
)
@click.option(
    "--password",
    default="",
    help=(
        "For type=login_password: the password. For type=none: the "
        "stored secret (vault password / become password)."
    ),
)
@click.option("--passphrase", default="", help="SSH key passphrase")
@click.pass_context
@fail_on_error
def create_cmd(
    ctx: click.Context,
    name: str,
    key_type: str,
    ssh_key: str,
    login: str,
    password: str,
    passphrase: str,
) -> None:
    """Create an access key."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    kwargs = _create_kwargs(name, key_type, ssh_key, login, password, passphrase)
    item = client.create_key(pid, **kwargs)
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        click.echo(f"created key id={item.id}")


@keys.command("update")
@click.argument("key_id", type=int)
@click.option("--name", default=None)
@click.option(
    "--private-key", "ssh_key", default=None, help="Replacement private key body (or @file)."
)
@click.option("--login", default=None)
@click.option("--passphrase", default=None)
@click.pass_context
@fail_on_error
def update_cmd(
    ctx: click.Context,
    key_id: int,
    name: str | None,
    ssh_key: str | None,
    login: str | None,
    passphrase: str | None,
) -> None:
    """Update an access key."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if ssh_key is not None:
        payload["ssh"] = {
            "private_key": _read_private_key(ssh_key),
            "login": login or "",
            "passphrase": passphrase or "",
        }
    client.update_key(pid, key_id, **payload)
    if not opts["quiet"]:
        click.echo(f"updated key id={key_id}")


@keys.command("delete")
@click.argument("key_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, key_id: int, *, yes: bool) -> None:
    """Delete an access key."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    confirm_delete("key", key_id, yes=yes)
    client.delete_key(pid, key_id)
    if not opts["quiet"]:
        click.echo(f"deleted key id={key_id}")


def register_keys_commands(main_group: Any) -> None:
    """Register the `keys` command group."""
    main_group.add_command(keys)
    main_group.commands["key"].category = "read"
    main_group.add_alias("keys", "key")
