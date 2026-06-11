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
from semacli.core.exceptions import HookError
from semacli.core.guards import ensure_overrides_allowed
from semacli.core.hooks import run_hook, warn_hook_failure
from semacli.core.resolve import resolve_template

from .._envvars import normalize_environment
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
  sem run mtree --limit ans2
  sem run mtree --check --diff               # ansible --check --diff
  sem run mtree --tags ntp,users             # ansible --tags
  sem run mtree --debug 2                    # ansible -vv
  sem run echo --environment 'msg=coucou'    # key=val (ansible -e style)
  sem run echo --environment '{"msg":"x"}'   # JSON (canonical form)
  sem run mtree --no-watch                   # fire and return id
  sem run 5 --limit web1           # by id
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
    @click.option("--tags", default=None, help="ansible --tags (comma-separated list)")
    @click.option("--skip-tags", default=None, help="ansible --skip-tags (comma-separated list)")
    @click.option("--playbook", default=None, help="Override template playbook path")
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
    @click.option(
        "--no-hooks",
        "no_hooks",
        is_flag=True,
        help="Skip any task_run_* hooks configured in [hook] (debug / replay).",
    )
    @common_options
    @output_options
    @project_option
    def run_cmd(
        template: str,
        limit: str | None,
        tags: str | None,
        skip_tags: str | None,
        playbook: str | None,
        environment: str | None,
        debug: int,
        dry_run: bool,
        diff: bool,
        exact: bool,
        watch: bool,
        interval: float,
        no_hooks: bool,
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
        project_override: int | None,
    ) -> None:
        # Normalize --environment outside the try-block so UsageError
        # surfaces as a clean exit 2 rather than being swallowed by
        # handle_error and reported as an opaque "API error".
        environment = normalize_environment(environment)
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, project_override)

            template_id = resolve_template(client, pid, template, exact=exact)
            OutputFormatter.format_verbose(
                f"resolved template '{template}' -> id {template_id}", verbose
            )

            # Fail closed BEFORE posting: Semaphore silently drops
            # forbidden overrides (a refused --limit runs on the full
            # inventory, ken #827).
            if limit or tags or skip_tags or debug:
                ensure_overrides_allowed(
                    client.get_template(pid, template_id),
                    limit=limit,
                    tags=tags,
                    skip_tags=skip_tags,
                    debug=debug,
                )

            hook_env_base = {
                "SEMACLI_COMMAND": "run",
                "SEMACLI_GROUP": "task",
                "SEMACLI_VERB": "run",
                "SEMACLI_CONFIG": config,
                "SEMACLI_PROJECT": str(pid),
                "SEMACLI_TEMPLATE": template,
                "SEMACLI_TEMPLATE_ID": str(template_id),
                "SEMACLI_LIMIT": limit or "",
                "SEMACLI_TAGS": tags or "",
            }
            hooks_enabled = not no_hooks

            run_hook(
                cfg.hooks,
                "task_run_prehook",
                hook_env_base,
                verbose=verbose,
                enabled=hooks_enabled,
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

            if not quiet and not output_json:
                click.echo(f"task id: {task.id}")
            if output_json and not watch:
                click.echo(f'{{"task_id": {task.id}}}')

            if watch:
                final = _watch_task(client, pid, task.id, interval)
                if not quiet:
                    click.echo(f"\n-> status: {final}", err=True)
                hook_env_after = {
                    **hook_env_base,
                    "SEMACLI_TASK_ID": str(task.id),
                    "SEMACLI_STATUS": final,
                }
                for hook_key in ("task_run_posthook",) + (
                    ("task_run_failhook",) if final != "success" else ()
                ):
                    try:
                        run_hook(
                            cfg.hooks,
                            hook_key,
                            hook_env_after,
                            verbose=verbose,
                            enabled=hooks_enabled,
                        )
                    except HookError as hook_err:
                        warn_hook_failure(hook_err, hook_key)
                if final != "success":
                    raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["run"].category = "execution"
