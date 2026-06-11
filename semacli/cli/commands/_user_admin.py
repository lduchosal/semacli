"""`sem user admin` — admin-only management of other users."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import User

from .._groups import AliasedGroup
from ..handlers import fail_on_error

ADMIN_HELP = """\
Admin-only: list / show / create / update / delete / set-password
other users (the `/api/users` surface, not `/api/user`).

Requires an admin token. Non-admin tokens get a 403 on every command
of this subgroup.

Calling `sem user admin` without a subcommand lists all users.
"""

ADMIN_EPILOG = """\
Examples:
  sem user admin                                       # list (bare)
  sem user admin list
  sem user admin show 7
  sem user admin create --username alice \\
       --name "Alice Smith" --email alice@example.com
  sem user admin update 7 --email new@x.com
  sem user admin set-password 7
  sem user admin delete 7
"""


def _emit_user_text(u: User) -> None:
    """Render one user as key/value lines (shared with `sem user whoami`)."""
    click.echo(f"id:       {u.id}")
    click.echo(f"username: {u.username}")
    click.echo(f"name:     {u.name}")
    click.echo(f"email:    {u.email}")
    click.echo(f"admin:    {u.admin}")
    click.echo(f"created:  {u.created}")


def _do_list(opts: dict[str, Any]) -> None:
    """Shared list-users handler used by both `admin list` and bare `admin`."""
    cfg = load_config(opts["config"])
    users = SemaphoreClient(cfg, verbose=opts["verbose"]).list_users()
    if opts["output_json"]:
        click.echo(json.dumps([u.model_dump() for u in users], indent=2))
    elif not opts["quiet"]:
        if not users:
            click.echo("No users found")
            return
        for u in users:
            flag = "admin" if u.admin else "user "
            click.echo(f"{u.id:>4}  {flag}  {u.username:<20}  {u.name}")
        click.echo(f"\nTotal: {len(users)} user(s)")


@click.group(
    "admin",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=ADMIN_HELP,
    epilog=ADMIN_EPILOG,
)
@click.pass_context
@fail_on_error
def admin_group(ctx: click.Context) -> None:
    """List all users when invoked without a subcommand."""
    opts = ctx.obj
    if ctx.invoked_subcommand is not None:
        return
    # Bare invocation = list (matches the UX.md pattern).
    _do_list(opts)


@admin_group.command("list")
@click.pass_context
@fail_on_error
def admin_list_cmd(ctx: click.Context) -> None:
    """List all users (admin)."""
    _do_list(ctx.obj)


@admin_group.command("show")
@click.argument("user_id", type=int)
@click.pass_context
@fail_on_error
def admin_show_cmd(ctx: click.Context, user_id: int) -> None:
    """Show one user (admin)."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    u = SemaphoreClient(cfg, verbose=opts["verbose"]).get_user(user_id)
    if opts["output_json"]:
        click.echo(json.dumps(u.model_dump(), indent=2))
    elif not opts["quiet"]:
        _emit_user_text(u)


@admin_group.command("create")
@click.option("--username", required=True)
@click.option("--name", required=True, help="Display name (full name).")
@click.option("--email", required=True)
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Initial password (prompted if omitted).",
)
@click.option("--admin", is_flag=True, help="Grant admin privileges.")
@click.pass_context
@fail_on_error
def admin_create_cmd(
    ctx: click.Context,
    *,
    username: str,
    name: str,
    email: str,
    password: str,
    admin: bool,
) -> None:
    """Create a new user (admin)."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    u = SemaphoreClient(cfg, verbose=opts["verbose"]).create_user(
        username=username,
        name=name,
        email=email,
        password=password,
        admin=admin,
    )
    if opts["output_json"]:
        click.echo(json.dumps(u.model_dump(), indent=2))
    elif not opts["quiet"]:
        click.echo(f"created user id={u.id} username={u.username}")


@admin_group.command("update")
@click.argument("user_id", type=int)
@click.option("--username", default=None)
@click.option("--name", default=None)
@click.option("--email", default=None)
@click.option("--admin/--no-admin", default=None)
@click.pass_context
@fail_on_error
def admin_update_cmd(
    ctx: click.Context,
    *,
    user_id: int,
    username: str | None,
    name: str | None,
    email: str | None,
    admin: bool | None,
) -> None:
    """Update mutable fields of a user (admin)."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    client.update_user(
        user_id,
        username=username,
        name=name,
        email=email,
        admin=admin,
    )
    if not opts["quiet"]:
        click.echo(f"updated user id={user_id}")


@admin_group.command("delete")
@click.argument("user_id", type=int)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
@fail_on_error
def admin_delete_cmd(ctx: click.Context, user_id: int, *, yes: bool) -> None:
    """Delete a user (admin). Irreversible."""
    opts = ctx.obj
    if not yes and not click.confirm(
        f"Delete user id={user_id}? This is irreversible.", default=False
    ):
        click.echo("aborted.", err=True)
        return
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    client.delete_user(user_id)
    if not opts["quiet"]:
        click.echo(f"deleted user id={user_id}")


@admin_group.command("set-password")
@click.argument("user_id", type=int)
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="New password (prompted if omitted).",
)
@click.pass_context
@fail_on_error
def admin_set_password_cmd(ctx: click.Context, user_id: int, password: str) -> None:
    """Reset a user's password (admin)."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    client.set_user_password(user_id, password)
    if not opts["quiet"]:
        click.echo(f"reset password for user id={user_id}")
