"""Read-only viewers of the `sem task` group: output, watch, list, raw-output.

Satellite of `tasks.py` (same pattern as `_user_admin.py` / `_project_members.py`):
the commands are declared standalone here and attached to `tasks_group` by the
parent module. Shared helpers (`_setup`, `_emit_output_lines`) live here and are
imported back by `tasks.py` to avoid a circular import.
"""

import json
import time
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Task

from .._crud import opts_from_ctx
from ..decorators import resolve_project
from ..handlers import fail_on_error

_FINAL_STATES = {"success", "error", "stopped"}


def _emit_output_lines(entries: list[dict[str, Any]], start: int = 0) -> int:
    """Print output entries starting from index `start`; return new index."""
    for entry in entries[start:]:
        line = entry.get("output", "")
        if line:
            click.echo(line)
    return len(entries)


def _setup(opts: dict[str, Any]) -> tuple[SemaphoreClient, int]:
    """Build the API client and resolve the project id from the stored opts."""
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, opts["project_override"])
    return client, pid


def _emit_tasks_list_json(tasks: list[Task]) -> None:
    """Emit the task history as a JSON array of summary objects."""
    click.echo(
        json.dumps(
            [
                {
                    "id": t.id,
                    "template_id": t.template_id,
                    "tpl_alias": t.tpl_alias,
                    "tpl_playbook": t.tpl_playbook,
                    "status": t.status,
                    "created": t.created,
                }
                for t in tasks
            ],
            indent=2,
        )
    )


def _emit_tasks_list_text(tasks: list[Task]) -> None:
    """Emit the task history in compact text form, with an empty fallback + total line."""
    if not tasks:
        click.echo("No tasks found")
        return
    alias_width = max((len(t.tpl_alias) for t in tasks), default=0)
    for t in tasks:
        click.echo(
            f"{t.id:>5}  tpl={t.template_id:<4}  "
            f"{t.tpl_alias:<{alias_width}}  {t.status:<10}  {t.created}"
        )
    click.echo(f"\nTotal: {len(tasks)} task(s)")


@click.command("output")
@click.argument("task_id", type=int)
@click.pass_context
@fail_on_error
def output_cmd(ctx: click.Context, task_id: int) -> None:
    """Dump the full task output."""
    opts = opts_from_ctx(ctx)
    client, pid = _setup(opts)
    entries = client.get_task_output(pid, task_id)
    if opts["output_json"]:
        click.echo(json.dumps(entries, indent=2))
    elif not opts["quiet"]:
        _emit_output_lines(entries)


@click.command("watch")
@click.argument("task_id", type=int)
@click.option("--interval", default=2.0, type=float, help="Polling interval in seconds")
@click.pass_context
@fail_on_error
def watch_cmd(ctx: click.Context, task_id: int, interval: float) -> None:
    """Tail task output until the task reaches a final state."""
    opts = opts_from_ctx(ctx)
    client, pid = _setup(opts)

    seen = 0
    while True:
        entries = client.get_task_output(pid, task_id)
        seen = _emit_output_lines(entries, start=seen)
        task = client.get_task(pid, task_id)
        if task.status in _FINAL_STATES:
            if not opts["quiet"]:
                click.echo(f"\n→ status: {task.status}", err=True)
            return
        time.sleep(interval)


@click.command("list")
@click.pass_context
@fail_on_error
def list_cmd(ctx: click.Context) -> None:
    """List task history of the project."""
    opts = opts_from_ctx(ctx)
    client, pid = _setup(opts)
    tasks = client.list_tasks(pid)
    if opts["output_json"]:
        _emit_tasks_list_json(tasks)
    elif not opts["quiet"]:
        _emit_tasks_list_text(tasks)


@click.command("raw-output")
@click.argument("task_id", type=int)
@click.pass_context
@fail_on_error
def raw_output_cmd(ctx: click.Context, task_id: int) -> None:
    """Dump task output without timestamps."""
    opts = opts_from_ctx(ctx)
    client, pid = _setup(opts)
    raw = client.get_task_raw_output(pid, task_id)
    if opts["output_json"]:
        click.echo(json.dumps({"output": raw}))
    elif not opts["quiet"]:
        click.echo(raw, nl=False)
