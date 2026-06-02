"""Tasks commands (run + show + output + watch)."""

import json
import time
from dataclasses import asdict
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Task

from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import OutputFormatter, handle_error

_FINAL_STATES = {"success", "error", "stopped"}


def _emit_task_json(t: Task) -> None:
    click.echo(json.dumps(asdict(t), indent=2))


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

    @main_group.group("tasks")
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
        """Run, inspect, and watch Semaphore tasks."""
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
    @click.option("--playbook", default=None, help="Override template playbook")
    @click.option("--environment", default=None, help="JSON env vars override")
    @click.option("--debug", is_flag=True, help="Enable debug mode")
    @click.option("--dry-run", is_flag=True, help="Run in check mode")
    @click.pass_context
    def run_cmd(
        ctx: click.Context,
        template_id: int,
        limit: str | None,
        playbook: str | None,
        environment: str | None,
        debug: bool,
        dry_run: bool,
    ) -> None:
        """Launch a task from a template."""
        opts = ctx.obj
        verbose = opts["verbose"]
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
                debug=debug,
                dry_run=dry_run,
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
    @click.option(
        "--interval", default=2.0, type=float, help="Polling interval in seconds"
    )
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
