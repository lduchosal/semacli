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

from ..decorators import common_options, output_options
from ..handlers import handle_error

USER_HELP = """\
User: information about the currently-authenticated user.

`whoami` returns the user the token belongs to. `tokens` manages the
API tokens of that user (list / create / delete). To manage other users
(admin-only) see the `users` command in a future release.

Calling `semacli user` without a subcommand prints `whoami`.
"""

USER_EPILOG = """\
Examples:
  semacli user                                # whoami
  semacli user whoami
  semacli user tokens                         # list tokens
  semacli user tokens create                  # mint a new token (printed once!)
  semacli user tokens delete <token-id>
"""

TOKENS_HELP = """\
Manage the API tokens of the currently-authenticated user.

`tokens` lists; `create` mints a new token and prints it once (the
secret is irrecoverable thereafter); `delete <id>` revokes one.
"""

TOKENS_EPILOG = """\
Examples:
  semacli user tokens                         # list
  semacli user tokens create                  # mint
  semacli user tokens delete sem-abc123
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


def register_user_commands(main_group: Any) -> None:
    """Register `semacli user` and its subcommands."""

    @main_group.group("user", invoke_without_command=True, help=USER_HELP, epilog=USER_EPILOG)
    @click.pass_context
    @common_options
    @output_options
    def user_group(
        ctx: click.Context,
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
    ) -> None:
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
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)
            user = client.whoami()
            if output_json:
                click.echo(json.dumps(user.model_dump(), indent=2))
            elif not quiet:
                _emit_user_text(user)
        except Exception as e:
            handle_error(e, verbose)

    @user_group.command("whoami")
    @click.pass_context
    def whoami_cmd(ctx: click.Context) -> None:
        """Print metadata about the currently-authenticated user."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            user = client.whoami()
            if opts["output_json"]:
                click.echo(json.dumps(user.model_dump(), indent=2))
            elif not opts["quiet"]:
                _emit_user_text(user)
        except Exception as e:
            handle_error(e, verbose)

    @user_group.group("tokens", invoke_without_command=True, help=TOKENS_HELP, epilog=TOKENS_EPILOG)
    @click.pass_context
    def tokens_group(ctx: click.Context) -> None:
        opts = ctx.obj
        if ctx.invoked_subcommand is not None:
            return
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            tokens = client.list_user_tokens()
            if opts["output_json"]:
                click.echo(json.dumps([t.model_dump() for t in tokens], indent=2))
            elif not opts["quiet"]:
                _emit_tokens_text(tokens)
        except Exception as e:
            handle_error(e, verbose)

    @tokens_group.command("create")
    @click.pass_context
    def tokens_create_cmd(ctx: click.Context) -> None:
        """Mint a new API token. The secret is printed once and unrecoverable."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            token = client.create_user_token()
            if opts["output_json"]:
                click.echo(json.dumps(token.model_dump(), indent=2))
            elif not opts["quiet"]:
                click.echo(f"token id: {token.id}")
                click.echo("Save it — this is the only time it is shown.")
        except Exception as e:
            handle_error(e, verbose)

    @tokens_group.command("delete")
    @click.argument("token_id")
    @click.option("--yes", is_flag=True, help="Skip confirmation")
    @click.pass_context
    def tokens_delete_cmd(ctx: click.Context, token_id: str, yes: bool) -> None:
        """Revoke an API token by id."""
        opts = ctx.obj
        verbose = opts["verbose"]
        if not yes and not click.confirm(f"Revoke token {token_id}?", default=False):
            click.echo("aborted.", err=True)
            return
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            client.delete_user_token(token_id)
            if not opts["quiet"]:
                click.echo(f"deleted token {token_id}")
        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["user"].category = "connection"
