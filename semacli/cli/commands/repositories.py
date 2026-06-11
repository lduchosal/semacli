"""Repositories CRUD commands."""

from typing import Any

import click

from semacli.core.models import Repository

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

REPO_HELP = """\
Repositories: git sources from which Semaphore pulls playbooks.

Each repo belongs to one project and is bound to one SSH key (the key
Semaphore uses to clone). Templates reference a repo + a playbook path
inside it.

Calling `sem repo` without a subcommand lists repositories.
"""

REPO_EPILOG = """\
Examples:
  sem repo                                  # list
  sem repo show 4
  sem repo create --name infra \\
       --git-url git@github.com:org/infra.git \\
       --branch main --ssh-key-id 12
  sem repo update 4 --branch release/2026
  sem repo delete 4
"""


def _fmt_row(r: Repository) -> str:
    """One aligned text row for the repository list view."""
    return f"{r.id:>4}  {r.name}  {r.git_url}@{r.git_branch or 'HEAD'}"


def _emit_show_text(r: Repository) -> None:
    """Emit one repository as key-value lines."""
    click.echo(f"id:         {r.id}")
    click.echo(f"name:       {r.name}")
    click.echo(f"git_url:    {r.git_url}")
    click.echo(f"git_branch: {r.git_branch}")
    click.echo(f"ssh_key_id: {r.ssh_key_id}")
    click.echo(f"project_id: {r.project_id}")


@click.group(
    "repo",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=REPO_HELP,
    epilog=REPO_EPILOG,
)
@click.pass_context
@common_options
@output_options
@project_option
@fail_on_error
def repositories(
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """List repositories when invoked without a subcommand."""
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
    items = client.list_repositories(pid)
    if output_json:
        emit_json_list(items)
    elif not quiet:
        emit_text_list(items, "repository(ies)", _fmt_row)


@repositories.command("show")
@click.argument("repo_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, repo_id: int) -> None:
    """Show one repository."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    item = client.get_repository(pid, repo_id)
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        _emit_show_text(item)


@repositories.command("create")
@click.option("--name", required=True)
@click.option("--git-url", required=True)
@click.option("--branch", default="main", help="git branch (default: main)")
@click.option("--ssh-key-id", required=True, type=int)
@click.pass_context
@fail_on_error
def create_cmd(ctx: click.Context, name: str, git_url: str, branch: str, ssh_key_id: int) -> None:
    """Create a repository."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    item = client.create_repository(
        pid,
        name=name,
        git_url=git_url,
        git_branch=branch,
        ssh_key_id=ssh_key_id,
    )
    if opts["output_json"]:
        emit_json_single(item)
    elif not opts["quiet"]:
        click.echo(f"created repository id={item.id}")


@repositories.command("update")
@click.argument("repo_id", type=int)
@click.option("--name", default=None)
@click.option("--git-url", default=None)
@click.option("--branch", "git_branch", default=None)
@click.option("--ssh-key-id", type=int, default=None)
@click.pass_context
@fail_on_error
def update_cmd(
    ctx: click.Context,
    repo_id: int,
    name: str | None,
    git_url: str | None,
    git_branch: str | None,
    ssh_key_id: int | None,
) -> None:
    """Update a repository."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    client.update_repository(
        pid,
        repo_id,
        name=name,
        git_url=git_url,
        git_branch=git_branch,
        ssh_key_id=ssh_key_id,
    )
    if not opts["quiet"]:
        click.echo(f"updated repository id={repo_id}")


@repositories.command("delete")
@click.argument("repo_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, repo_id: int, *, yes: bool) -> None:
    """Delete a repository."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    confirm_delete("repository", repo_id, yes=yes)
    client.delete_repository(pid, repo_id)
    if not opts["quiet"]:
        click.echo(f"deleted repository id={repo_id}")


def register_repositories_commands(main_group: Any) -> None:
    """Register the `repo` command group."""
    main_group.add_command(repositories)
    main_group.commands["repo"].category = "read"
    main_group.add_alias("repositories", "repo")
