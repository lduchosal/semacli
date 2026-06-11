"""Tasks commands (run + show + output + watch)."""

import json

import click

from semacli.core.guards import ensure_overrides_allowed
from semacli.core.models import Task

from .._crud import opts_from_ctx, store_opts
from .._envvars import normalize_environment
from .._groups import AliasedGroup, SectionedRootGroup
from ..decorators import common_options, output_options, project_option
from ..handlers import OutputFormatter, fail_on_error
from ._task_views import _setup, list_cmd, output_cmd, raw_output_cmd, watch_cmd

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


@click.group("task", cls=AliasedGroup, help=TASK_HELP, epilog=TASK_EPILOG)
@click.pass_context
@common_options
@output_options
@project_option
def tasks_group(  # noqa: PLR0913 — one parameter per --option (click callback)
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
def _post_run(  # noqa: PLR0913 — one keyword per forwarded --option
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
def run_cmd(  # noqa: PLR0913 — one parameter per --option (click callback)
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


for _viewer in (output_cmd, watch_cmd, list_cmd, raw_output_cmd):
    tasks_group.add_command(_viewer)


def register_tasks_commands(main_group: SectionedRootGroup) -> None:
    """Register the `tasks` command group."""
    main_group.add_command(tasks_group)
    main_group.set_category("task", "execution")
    main_group.add_alias("tasks", "task")
