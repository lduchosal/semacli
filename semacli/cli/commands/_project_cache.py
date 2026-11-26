"""`sem project cache` — the server-side checkouts of a project."""

import json

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.guards import ensure_no_active_tasks
from semacli.core.models import Task

from .._groups import AliasedGroup
from ..decorators import project_option, resolve_project
from ..handlers import fail_on_error

CACHE_HELP = """\
Cache: the repository checkouts Semaphore keeps for a project.

Semaphore clones each repository into <tmp_path>/project_<id> on the
server and reuses it between runs. Clearing the cache empties that
directory; the next task checks its repository out again.
"""

CACHE_EPILOG = """\
Examples:
  sem project cache clear --dry-run         # would it be allowed?
  sem project cache clear -p 1
  sem project cache clear -p 1 --force      # a zombie task blocks it
"""

CLEAR_EPILOG = """\
Refused (exit 2) while a task of the project is still active (waiting,
starting, running, stopping...): the purge would remove the files it
runs in. --dry-run lists the active tasks and exits 1 when the purge
would be refused, 0 when it would go ahead.

Examples:
  sem project cache clear
  sem project cache clear -p 1 --dry-run
  sem project cache clear -p 1 --force
  sem project cache clear --json | jq .cleared
"""


def _task_label(t: Task) -> str:
    """One aligned row for an active task."""
    return f"{t.id:>6}  {t.status:<20}  {t.tpl_alias or f'template {t.template_id}'}"


def _emit_text(pid: int, active: list[Task], *, dry_run: bool, force: bool) -> None:
    """Report what the clear did (or would do) in plain text."""
    if active:
        click.echo(f"active tasks in project {pid}:", err=not dry_run)
        for t in active:
            click.echo(f"  {_task_label(t)}", err=not dry_run)
    if dry_run:
        if not active:
            click.echo(f"no active task in project {pid}: cache clear would go ahead")
        elif force:
            click.echo(f"cache clear would go ahead (--force over {len(active)} active task(s))")
        else:
            click.echo(f"cache clear would be refused: {len(active)} active task(s)")
        return
    suffix = f" (--force over {len(active)} active task(s))" if active else ""
    click.echo(f"cleared cache of project {pid}{suffix}")


@click.group("cache", cls=AliasedGroup, help=CACHE_HELP, epilog=CACHE_EPILOG)
def cache_group() -> None:
    """Group for the project cache subcommands."""


@cache_group.command("clear", epilog=CLEAR_EPILOG)
@project_option
@click.option("--dry-run", is_flag=True, help="List active tasks; clear nothing.")
@click.option("--force", is_flag=True, help="Clear even with active tasks (zombie task).")
@click.pass_context
@fail_on_error
def clear_cmd(
    ctx: click.Context,
    *,
    project_override: int | None,
    dry_run: bool,
    force: bool,
) -> None:
    """Delete the project's repository checkouts on the server."""
    opts = ctx.obj
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, project_override)
    active = client.list_active_tasks(pid)
    allowed = force or not active
    if not dry_run:
        if not force:
            ensure_no_active_tasks(pid, active)
        client.clear_project_cache(pid)
    if opts["output_json"]:
        payload = {
            "project_id": pid,
            "dry_run": dry_run,
            "forced": force and bool(active),
            "allowed": allowed,
            "cleared": not dry_run,
            "active_tasks": [t.model_dump() for t in active],
        }
        click.echo(json.dumps(payload, indent=2))
    elif not opts["quiet"]:
        _emit_text(pid, active, dry_run=dry_run, force=force)
    if dry_run and not allowed:
        # SystemExit, not ctx.exit: click's Exit is an Exception and would
        # fall into fail_on_error's funnel (same idiom as template audit).
        raise SystemExit(1)
