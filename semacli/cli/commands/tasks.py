"""Tasks commands (run + show + output + watch)."""

import json
import time
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Task

from .._envvars import normalize_environment
from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import OutputFormatter, handle_error

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
    click.echo(json.dumps(t.model_dump(), indent=2))


def _emit_task_text(t: Task) -> None:
    click.echo(f"id:          {t.id}")
    click.echo(f"template_id: {t.template_id}")
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


def register_tasks_commands(main_group: Any) -> None:
    """Register the `tasks` command group."""

    @main_group.group("task", help=TASK_HELP, epilog=TASK_EPILOG)
    @click.pass_context
    @common_options
    @output_options
    @project_option
    def tasks_group(
        ctx: click.Context,
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
        project_override: int | None,
    ) -> None:
        ctx.ensure_object(dict)
        ctx.obj.update(
            {
                "config": config,
                "verbose": verbose,
                "output_json": output_json,
                "quiet": quiet,
                "project_override": project_override,
            }
        )

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
        opts = ctx.obj
        verbose = opts["verbose"]
        environment = normalize_environment(environment)
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            OutputFormatter.format_verbose(
                f"POST /project/{pid}/tasks template_id={template_id}", verbose
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
        except Exception as e:
            handle_error(e, verbose)

    @tasks_group.command("show")
    @click.argument("task_id", type=int)
    @click.pass_context
    def show_cmd(ctx: click.Context, task_id: int) -> None:
        """Show task status + metadata."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            task = client.get_task(pid, task_id)
            if opts["output_json"]:
                _emit_task_json(task)
            elif not opts["quiet"]:
                _emit_task_text(task)
        except Exception as e:
            handle_error(e, verbose)

    @tasks_group.command("output")
    @click.argument("task_id", type=int)
    @click.pass_context
    def output_cmd(ctx: click.Context, task_id: int) -> None:
        """Dump the full task output."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            entries = client.get_task_output(pid, task_id)
            if opts["output_json"]:
                click.echo(json.dumps(entries, indent=2))
            elif not opts["quiet"]:
                _emit_output_lines(entries)
        except Exception as e:
            handle_error(e, verbose)

    @tasks_group.command("watch")
    @click.argument("task_id", type=int)
    @click.option("--interval", default=2.0, type=float, help="Polling interval in seconds")
    @click.pass_context
    def watch_cmd(ctx: click.Context, task_id: int, interval: float) -> None:
        """Tail task output until the task reaches a final state."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])

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
        except Exception as e:
            handle_error(e, verbose)

    @tasks_group.command("list")
    @click.pass_context
    def list_cmd(ctx: click.Context) -> None:
        """List task history of the project."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            tasks = client.list_tasks(pid)
            if opts["output_json"]:
                click.echo(
                    json.dumps(
                        [
                            {
                                "id": t.id,
                                "template_id": t.template_id,
                                "status": t.status,
                                "created": t.created,
                            }
                            for t in tasks
                        ],
                        indent=2,
                    )
                )
            elif not opts["quiet"]:
                if not tasks:
                    click.echo("No tasks found")
                else:
                    for t in tasks:
                        click.echo(
                            f"{t.id:>5}  tpl={t.template_id:<4}  {t.status:<10}  {t.created}"
                        )
                    click.echo(f"\nTotal: {len(tasks)} task(s)")
        except Exception as e:
            handle_error(e, verbose)

    @tasks_group.command("stop")
    @click.argument("task_id", type=int)
    @click.pass_context
    def stop_cmd(ctx: click.Context, task_id: int) -> None:
        """Stop a running task."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            client.stop_task(pid, task_id)
            if not opts["quiet"]:
                click.echo(f"stop requested for task {task_id}")
        except Exception as e:
            handle_error(e, verbose)

    @tasks_group.command("raw-output")
    @click.argument("task_id", type=int)
    @click.pass_context
    def raw_output_cmd(ctx: click.Context, task_id: int) -> None:
        """Dump task output without timestamps."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            raw = client.get_task_raw_output(pid, task_id)
            if opts["output_json"]:
                click.echo(json.dumps({"output": raw}))
            elif not opts["quiet"]:
                click.echo(raw, nl=False)
        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["task"].category = "execution"
    main_group.add_alias("tasks", "task")
