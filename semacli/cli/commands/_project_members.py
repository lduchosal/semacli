"""`sem project members` — project membership and roles."""

import json

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import ProjectMember

from .._groups import AliasedGroup
from ..decorators import project_option, resolve_project
from ..handlers import fail_on_error

MEMBERS_HELP = """\
Manage the users that have access to a project, and their role.

Roles (Semaphore RBAC): owner / manager / task_runner / guest. The
project owner cannot be removed.

Calling `sem project members` without a subcommand lists members.
"""

MEMBERS_EPILOG = """\
Examples:
  sem project members                              # list members of default project
  sem project members -p 2                         # list members of project 2
  sem project members add --user 7 --role manager
  sem project members update 7 --role task_runner
  sem project members remove 7
"""


def _emit_members_text(members: list[ProjectMember]) -> None:
    """Emit the member list in compact text form, with an empty fallback + total line."""
    if not members:
        click.echo("No members found")
        return
    for m in members:
        label = m.username or m.name or f"user_id={m.user_id}"
        click.echo(f"{m.user_id:>4}  {label:<20}  {m.role}")
    click.echo(f"\nTotal: {len(members)} member(s)")


@click.group(
    "members",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=MEMBERS_HELP,
    epilog=MEMBERS_EPILOG,
)
@click.pass_context
@project_option
@fail_on_error
def members_group(ctx: click.Context, project_override: int | None) -> None:
    """List project members when invoked without a subcommand."""
    opts = ctx.obj
    opts["project_override"] = project_override
    if ctx.invoked_subcommand is not None:
        return
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, project_override)
    members = client.list_project_members(pid)
    if opts["output_json"]:
        click.echo(json.dumps([m.model_dump() for m in members], indent=2))
    elif not opts["quiet"]:
        _emit_members_text(members)


@members_group.command("add")
@click.option("--user", "user_id", required=True, type=int, help="User id to add.")
@click.option(
    "--role",
    required=True,
    type=click.Choice(["owner", "manager", "task_runner", "guest"]),
)
@click.pass_context
@fail_on_error
def members_add_cmd(ctx: click.Context, user_id: int, role: str) -> None:
    """Grant a user access to the project."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, opts["project_override"])
    client.add_project_member(pid, user_id=user_id, role=role)
    if not opts["quiet"]:
        click.echo(f"added user id={user_id} as {role}")


@members_group.command("update")
@click.argument("user_id", type=int)
@click.option(
    "--role",
    required=True,
    type=click.Choice(["owner", "manager", "task_runner", "guest"]),
)
@click.pass_context
@fail_on_error
def members_update_cmd(ctx: click.Context, user_id: int, role: str) -> None:
    """Change a member's role."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, opts["project_override"])
    client.update_project_member(pid, user_id=user_id, role=role)
    if not opts["quiet"]:
        click.echo(f"updated user id={user_id} role={role}")


@members_group.command("remove")
@click.argument("user_id", type=int)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
@fail_on_error
def members_remove_cmd(ctx: click.Context, user_id: int, *, yes: bool) -> None:
    """Revoke a user's access to the project."""
    opts = ctx.obj
    if not yes and not click.confirm(f"Remove user id={user_id} from the project?", default=False):
        click.echo("aborted.", err=True)
        return
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, opts["project_override"])
    client.remove_project_member(pid, user_id=user_id)
    if not opts["quiet"]:
        click.echo(f"removed user id={user_id}")
