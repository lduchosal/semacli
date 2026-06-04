"""Top-level `sem run <template>` shortcut.

Resolves a template by name (or id) and launches a task from it.
Default behavior tails the task output until it reaches a final state
and propagates the task's exit status. See UX.md § 3.1.A.
"""

import time
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.resolve import resolve_template

from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import OutputFormatter, handle_error

_FINAL_STATES = {"success", "error", "stopped"}

RUN_HELP = """\
Shortcut: run a template by name (or id).

Resolves <template> against the project's templates by case-insensitive
substring match. An exact match wins over substring matches when both
are present. Pass --exact to require a strict name match. Pass a
numeric id to skip the lookup.

By default the command tails the task output until it reaches a final
state (success / error / stopped) and exits with the corresponding
code (0 / 1). Pass --no-watch to return immediately after submission.
"""

RUN_EPILOG = """\
Examples:
  sem run mtree                              # default: run + watch
  sem run mtree --limit ans2.0.2113.ch
  sem run mtree --dry-run --debug
  sem run mtree --no-watch                   # fire and return id
  sem run 5 --limit web1.0.2113.ch           # by id
  sem run --exact mtree                      # disallow substring fuzz
"""


def _emit_output_lines(entries: list[Any], start: int) -> int:
    for entry in entries[start:]:
        line = entry.get("output", "") if isinstance(entry, dict) else getattr(entry, "output", "")
        click.echo(line)
    return len(entries)


def _watch_task(client: SemaphoreClient, pid: int, task_id: int, interval: float) -> str:
    seen = 0
    while True:
        entries = client.get_task_output(pid, task_id)
        seen = _emit_output_lines(entries, start=seen)
        task = client.get_task(pid, task_id)
        if task.status in _FINAL_STATES:
            return task.status
        time.sleep(interval)


def register_run_commands(main_group: Any) -> None:
    """Register the top-level `run` shortcut."""

    @main_group.command("run", help=RUN_HELP, epilog=RUN_EPILOG)
    @click.argument("template")
    @click.option("--limit", default=None, help="ansible --limit pattern")
    @click.option("--playbook", default=None, help="Override template playbook path")
    @click.option("--environment", default=None, help="JSON env vars override")
    @click.option("--debug", is_flag=True, help="Enable debug mode (ansible -vv)")
    @click.option("--dry-run", is_flag=True, help="Run in check mode (ansible --check)")
    @click.option(
        "--exact",
        is_flag=True,
        help="Require an exact template name match (no substring fuzz).",
    )
    @click.option(
        "--watch/--no-watch",
        "watch",
        default=True,
        help="Tail the task output until it finishes (default: on).",
    )
    @click.option("--interval", default=2.0, type=float, help="Watch polling interval in seconds")
    @common_options
    @output_options
    @project_option
    def run_cmd(
        template: str,
        limit: str | None,
        playbook: str | None,
        environment: str | None,
        debug: bool,
        dry_run: bool,
        exact: bool,
        watch: bool,
        interval: float,
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
        project_override: int | None,
    ) -> None:
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, project_override)

            template_id = resolve_template(client, pid, template, exact=exact)
            OutputFormatter.format_verbose(
                f"resolved template '{template}' -> id {template_id}", verbose
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

            if not quiet and not output_json:
                click.echo(f"task id: {task.id}")
            if output_json and not watch:
                click.echo(f'{{"task_id": {task.id}}}')

            if watch:
                final = _watch_task(client, pid, task.id, interval)
                if not quiet:
                    click.echo(f"\n-> status: {final}", err=True)
                if final != "success":
                    raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["run"].category = "execution"
