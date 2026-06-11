"""User-self commands: `whoami` + API token management.

These talk to the `/api/user` and `/api/user/tokens` endpoints — the
currently-authenticated user, not the admin /users surface.
"""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import User, UserToken

from .._groups import AliasedGroup
from ..decorators import common_options, output_options
from ..handlers import fail_on_error

USER_HELP = """\
User: information about the currently-authenticated user, plus admin
actions on other users.

`whoami` returns the user the token belongs to. `tokens` manages the
API tokens of that user. `admin` is the admin-only surface to list /
create / delete / promote other users (requires an admin token).

Calling `sem user` without a subcommand prints `whoami`.
"""

USER_EPILOG = """\
Examples:
  sem user                                # whoami
  sem user whoami
  sem user tokens                         # list tokens
  sem user tokens create                  # mint a new token (printed once!)
  sem user tokens delete <token-id>
  sem user admin list                     # admin: all users
  sem user admin create --username alice \\
       --name "Alice" --email alice@example.com
"""

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

TOKENS_HELP = """\
Manage the API tokens of the currently-authenticated user.

`tokens` lists; `create` mints a new token and prints it once (the
secret is irrecoverable thereafter); `delete <id>` revokes one.
"""

TOKENS_EPILOG = """\
Examples:
  sem user tokens                         # list
  sem user tokens create                  # mint
  sem user tokens delete sem-abc123
"""


def _emit_user_text(u: User) -> None:
    click.echo(f"id:       {u.id}")
    click.echo(f"username: {u.username}")
    click.echo(f"name:     {u.name}")
    click.echo(f"email:    {u.email}")
    click.echo(f"admin:    {u.admin}")
    click.echo(f"created:  {u.created}")


def _emit_tokens_text(tokens: list[UserToken]) -> None:
    if not tokens:
        click.echo("No tokens found")
        return
    for t in tokens:
        flag = "expired" if t.expired else "active "
        click.echo(f"{t.id:<24}  {flag}  {t.created}")
    click.echo(f"\nTotal: {len(tokens)} token(s)")


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
    "user",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=USER_HELP,
    epilog=USER_EPILOG,
)
@click.pass_context
@common_options
@output_options
@fail_on_error
def user_group(
    ctx: click.Context,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
) -> None:
    """Print `whoami` when invoked without a subcommand."""
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
    user = SemaphoreClient(cfg, verbose=verbose).whoami()
    if output_json:
        click.echo(json.dumps(user.model_dump(), indent=2))
    elif not quiet:
        _emit_user_text(user)


@user_group.command("whoami")
@click.pass_context
@fail_on_error
def whoami_cmd(ctx: click.Context) -> None:
    """Print metadata about the currently-authenticated user."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    user = SemaphoreClient(cfg, verbose=opts["verbose"]).whoami()
    if opts["output_json"]:
        click.echo(json.dumps(user.model_dump(), indent=2))
    elif not opts["quiet"]:
        _emit_user_text(user)


@user_group.group("tokens", invoke_without_command=True, help=TOKENS_HELP, epilog=TOKENS_EPILOG)
@click.pass_context
@fail_on_error
def tokens_group(ctx: click.Context) -> None:
    """List tokens when invoked without a subcommand."""
    opts = ctx.obj
    if ctx.invoked_subcommand is not None:
        return
    cfg = load_config(opts["config"])
    tokens = SemaphoreClient(cfg, verbose=opts["verbose"]).list_user_tokens()
    if opts["output_json"]:
        click.echo(json.dumps([t.model_dump() for t in tokens], indent=2))
    elif not opts["quiet"]:
        _emit_tokens_text(tokens)


@tokens_group.command("create")
@click.pass_context
@fail_on_error
def tokens_create_cmd(ctx: click.Context) -> None:
    """Mint a new API token. The secret is printed once and unrecoverable."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    token = SemaphoreClient(cfg, verbose=opts["verbose"]).create_user_token()
    if opts["output_json"]:
        click.echo(json.dumps(token.model_dump(), indent=2))
    elif not opts["quiet"]:
        click.echo(f"token id: {token.id}")
        click.echo("Save it — this is the only time it is shown.")


@tokens_group.command("delete")
@click.argument("token_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
@fail_on_error
def tokens_delete_cmd(ctx: click.Context, token_id: str, yes: bool) -> None:
    """Revoke an API token by id."""
    opts = ctx.obj
    if not yes and not click.confirm(f"Revoke token {token_id}?", default=False):
        click.echo("aborted.", err=True)
        return
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    client.delete_user_token(token_id)
    if not opts["quiet"]:
        click.echo(f"deleted token {token_id}")


@user_group.group("admin", invoke_without_command=True, help=ADMIN_HELP, epilog=ADMIN_EPILOG)
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
def admin_delete_cmd(ctx: click.Context, user_id: int, yes: bool) -> None:
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


def register_user_commands(main_group: Any) -> None:
    """Register `sem user` and its subcommands."""
    main_group.add_command(user_group)
    main_group.commands["user"].category = "connection"
