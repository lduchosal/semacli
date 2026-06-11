"""Tasks commands (run + show + output + watch)."""

import json
import time
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.guards import ensure_overrides_allowed
from semacli.core.models import Task

from .._crud import opts_from_ctx, store_opts
from .._envvars import normalize_environment
from .._groups import AliasedGroup
from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import OutputFormatter, fail_on_error

_FINAL_STATES = {"success", "error", "stopped"}

TASK_HELP = """\
Tasks: concrete executions of a template.

Lifecycle:
  run         starts a task (returns a task id)
  watch       tails its output until it reaches a final state
  show        reads metadata
  output      dumps the full output (with timestamps)
  raw-output  dumps the output without timestamps
  stop        cancels a running task
  list        history of recent tasks

For day-to-day use, prefer the top-level shortcut `sem run <name>`
which resolves a template by name and runs it.
"""

TASK_EPILOG = """\
Examples:
  sem task list                                 # recent runs
  sem task run 5 --limit web1                   # run by template id
  sem task run 5 --check --diff                 # ansible --check --diff
  sem task run 5 --tags ntp,users               # ansible --tags
  sem task watch 142                            # follow output
  sem task show 142
  sem task raw-output 142 > task-142.log
  sem task stop 142
"""


def _emit_task_json(t: Task) -> None:
    """Emit one task as a full JSON dump."""
    click.echo(json.dumps(t.model_dump(), indent=2))


def _emit_task_text(t: Task) -> None:
    """Emit one task as key-value lines, skipping fields the API left empty."""
    click.echo(f"id:          {t.id}")
    click.echo(f"template_id: {t.template_id}")
    if t.tpl_alias:
        click.echo(f"template:    {t.tpl_alias}")
    click.echo(f"status:      {t.status}")
    if t.playbook:
        click.echo(f"playbook:    {t.playbook}")
    if t.environment:
        click.echo(f"environment: {t.environment}")
    click.echo(f"created:     {t.created}")
    if t.start:
        click.echo(f"start:       {t.start}")
    if t.end:
        click.echo(f"end:         {t.end}")


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


@click.group("task", cls=AliasedGroup, help=TASK_HELP, epilog=TASK_EPILOG)
@click.pass_context
@common_options
@output_options
@project_option
def tasks_group(
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """Store shared options for the task subcommands."""
    store_opts(
        ctx,
        config=config,
        verbose=verbose,
        output_json=output_json,
        quiet=quiet,
        project_override=project_override,
    )


@fail_on_error
def _post_run(
    ctx: click.Context,
    *,
    template_id: int,
    limit: str | None,
    tags: str | None,
    skip_tags: str | None,
    playbook: str | None,
    environment: str | None,
    debug: int,
    dry_run: bool,
    diff: bool,
) -> None:
    """Validate overrides, POST the task and emit the result."""
    opts = opts_from_ctx(ctx)
    client, pid = _setup(opts)
    OutputFormatter.format_verbose(
        f"POST /project/{pid}/tasks template_id={template_id}", opts["verbose"]
    )
    # Fail closed BEFORE posting: Semaphore silently drops
    # forbidden overrides (ken #827).
    if limit or tags or skip_tags or debug:
        ensure_overrides_allowed(
            client.get_template(pid, template_id),
            limit=limit,
            tags=tags,
            skip_tags=skip_tags,
            debug=debug,
        )
    task = client.run_task(
        pid,
        template_id,
        playbook=playbook,
        environment=environment,
        limit=limit,
        tags=tags,
        skip_tags=skip_tags,
        debug=debug,
        dry_run=dry_run,
        diff=diff,
    )
    if opts["output_json"]:
        _emit_task_json(task)
    elif not opts["quiet"]:
        _emit_task_text(task)


@tasks_group.command("run")
@click.argument("template_id", type=int)
@click.option("--limit", default=None, help="ansible --limit pattern")
@click.option("--tags", default=None, help="ansible --tags (comma-separated list)")
@click.option("--skip-tags", default=None, help="ansible --skip-tags (comma-separated list)")
@click.option("--playbook", default=None, help="Override template playbook")
@click.option("--environment", default=None, help="JSON env vars override")
@click.option(
    "--debug",
    type=click.IntRange(0, 4),
    default=0,
    show_default=True,
    help="Ansible verbosity level (0=off, 1=-v, 2=-vv, 3=-vvv, 4=-vvvv).",
)
@click.option(
    "--check",
    "dry_run",
    is_flag=True,
    help="Run in check mode (ansible --check) — no changes applied.",
)
@click.option("--diff", is_flag=True, help="Show diff of file changes (ansible --diff)")
@click.pass_context
def run_cmd(
    ctx: click.Context,
    *,
    template_id: int,
    limit: str | None,
    tags: str | None,
    skip_tags: str | None,
    playbook: str | None,
    environment: str | None,
    debug: int,
    dry_run: bool,
    diff: bool,
) -> None:
    """Launch a task from a template."""
    # Normalize --environment outside the error funnel so UsageError
    # surfaces as a clean exit 2 rather than being swallowed by
    # handle_error and reported as an opaque error.
    environment = normalize_environment(environment)
    _post_run(
        ctx,
        template_id=template_id,
        limit=limit,
        tags=tags,
        skip_tags=skip_tags,
        playbook=playbook,
        environment=environment,
        debug=debug,
        dry_run=dry_run,
        diff=diff,
    )


@tasks_group.command("show")
@click.argument("task_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, task_id: int) -> None:
    """Show task status + metadata."""
    opts = opts_from_ctx(ctx)
    client, pid = _setup(opts)
    task = client.get_task(pid, task_id)
    if opts["output_json"]:
        _emit_task_json(task)
    elif not opts["quiet"]:
        _emit_task_text(task)


@tasks_group.command("output")
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


@tasks_group.command("watch")
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


@tasks_group.command("list")
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


@tasks_group.command("stop")
@click.argument("task_id", type=int)
@click.pass_context
@fail_on_error
def stop_cmd(ctx: click.Context, task_id: int) -> None:
    """Stop a running task."""
    opts = opts_from_ctx(ctx)
    client, pid = _setup(opts)
    client.stop_task(pid, task_id)
    if not opts["quiet"]:
        click.echo(f"stop requested for task {task_id}")


@tasks_group.command("raw-output")
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


def register_tasks_commands(main_group: Any) -> None:
    """Register the `tasks` command group."""
    main_group.add_command(tasks_group)
    main_group.commands["task"].category = "execution"
    main_group.add_alias("tasks", "task")
