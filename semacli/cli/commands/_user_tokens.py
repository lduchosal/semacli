"""`sem user tokens` — API tokens of the authenticated user."""

import json

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import UserToken

from .._groups import AliasedGroup
from ..handlers import fail_on_error

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


def _emit_tokens_text(tokens: list[UserToken]) -> None:
    """Emit the token list in compact text form, with an empty fallback + total line."""
    if not tokens:
        click.echo("No tokens found")
        return
    for t in tokens:
        flag = "expired" if t.expired else "active "
        click.echo(f"{t.id:<24}  {flag}  {t.created}")
    click.echo(f"\nTotal: {len(tokens)} token(s)")


@click.group(
    "tokens",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=TOKENS_HELP,
    epilog=TOKENS_EPILOG,
)
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
def tokens_delete_cmd(ctx: click.Context, token_id: str, *, yes: bool) -> None:
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
