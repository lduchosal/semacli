"""User-self commands: `whoami` + API token management.

These talk to the `/api/user` and `/api/user/tokens` endpoints — the
currently-authenticated user, not the admin /users surface.
"""

import json

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config

from .._groups import AliasedGroup, SectionedRootGroup
from ..decorators import common_options, output_options
from ..handlers import fail_on_error
from ._user_admin import _emit_user_text, admin_group
from ._user_tokens import tokens_group

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
    *,
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


user_group.add_command(tokens_group)
user_group.add_command(admin_group)


def register_user_commands(main_group: SectionedRootGroup) -> None:
    """Register `sem user` and its subcommands."""
    main_group.add_command(user_group)
    main_group.set_category("user", "connection")
