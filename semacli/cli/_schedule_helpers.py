"""Shared option plumbing, input parsing and text rendering for ``sched``.

Kept out of ``commands/schedules.py`` so the command module stays a thin
orchestration layer (file-size ceiling, ken #828). Pure helpers: the shared
override-options decorator, trigger validation, run-at normalisation, and
the list/show formatters.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import click

from semacli.core.models import Schedule, ScheduleTaskParams


def override_options(func: click.decorators.FC) -> click.decorators.FC:
    """Attach the ansible-override options shared by `create` and `update`."""
    options = [
        click.option(
            "--inventory",
            default=None,
            help="Override inventory: name or numeric id (resolved against the project).",
        ),
        click.option("--limit", default=None, help="ansible --limit, e.g. 'h1,h2' (comma list)."),
        click.option("--tags", default=None, help="ansible --tags (comma list)."),
        click.option(
            "--skip-tags", "skip_tags", default=None, help="ansible --skip-tags (comma list)."
        ),
        click.option(
            "--cli-args",
            "cli_args",
            default=None,
            help='Raw extra CLI args as a JSON array, e.g. \'["--forks","10"]\'.',
        ),
        click.option(
            "--message", default=None, help="Optional free-text message stored on the schedule."
        ),
    ]
    for option in reversed(options):
        func = option(func)
    return func


@dataclass
class Trigger:
    """Resolved schedule trigger: cron, run-at, or unchanged (update)."""

    schedule_type: str | None
    cron_format: str | None
    run_at: str | None


@dataclass
class Overrides:
    """Ansible-flavoured overrides a schedule applies when it fires."""

    inventory: str | None
    limit: str | None
    tags: str | None
    skip_tags: str | None
    cli_args: str | None
    message: str | None


@dataclass
class CreateSpec:
    """Everything `sched create` needs, bundled to keep signatures small."""

    template: str
    trigger: Trigger
    delete_after_run: bool
    name: str
    active: bool
    overrides: Overrides


@dataclass
class UpdateSpec:
    """Everything `sched update` needs, bundled to keep signatures small."""

    sched_id: int
    trigger: Trigger
    name: str | None
    active: bool | None
    delete_after_run: bool | None
    overrides: Overrides


def normalize_run_at(value: str) -> str:
    """Normalise a --run-at input to an RFC3339 UTC timestamp.

    Accepts RFC3339 (``2026-06-25T02:00:00Z``, with or without offset) and
    the convenience form ``YYYY-MM-DD HH:MM`` (interpreted as UTC). Raises
    a click ``UsageError`` (exit 2) on anything unparseable.
    """
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        msg = f"--run-at: not an ISO-8601 / RFC3339 time: {value!r}"
        raise click.UsageError(msg) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def trigger_for_create(cron_format: str | None, run_at: str | None) -> Trigger:
    """Resolve the (mutually exclusive, required) trigger for `sched create`."""
    if cron_format and run_at:
        msg = "pass either --cron or --run-at, not both"
        raise click.UsageError(msg)
    if run_at is not None:
        return Trigger("run_at", "", normalize_run_at(run_at))
    if cron_format:
        return Trigger(None, cron_format, None)
    msg = "a schedule needs a trigger: pass --cron '<expr>' or --run-at '<time>'"
    raise click.UsageError(msg)


def trigger_for_update(cron_format: str | None, run_at: str | None) -> Trigger:
    """Resolve the (both optional, mutually exclusive) trigger for `sched update`."""
    if cron_format and run_at:
        msg = "pass either --cron or --run-at, not both"
        raise click.UsageError(msg)
    if run_at is not None:
        return Trigger("run_at", None, normalize_run_at(run_at))
    return Trigger(None, cron_format, None)


def fmt_row(s: Schedule) -> str:
    """One aligned text row for the schedule list view."""
    flag = "active" if s.active else "inactive"
    trigger = "run-at" if s.type == "run_at" else s.cron_format
    return f"{s.id:>4}  tpl={s.template_id}  {trigger:<15}  {flag}  {s.name}"


def _emit_task_params(tp: ScheduleTaskParams) -> None:
    """Emit the override lines of a schedule's task_params, when present."""
    if tp.inventory_id is not None:
        click.echo(f"inventory_id: {tp.inventory_id}")
    if tp.params.limit:
        click.echo(f"limit:       {','.join(tp.params.limit)}")
    if tp.params.tags:
        click.echo(f"tags:        {','.join(tp.params.tags)}")
    if tp.params.skip_tags:
        click.echo(f"skip_tags:   {','.join(tp.params.skip_tags)}")
    if tp.arguments:
        click.echo(f"cli_args:    {tp.arguments}")
    if tp.message:
        click.echo(f"message:     {tp.message}")


def emit_show_text(s: Schedule) -> None:
    """Emit one schedule as key-value lines."""
    click.echo(f"id:          {s.id}")
    click.echo(f"name:        {s.name}")
    click.echo(f"template_id: {s.template_id}")
    click.echo(f"type:        {s.type or 'cron'}")
    if s.type == "run_at":
        click.echo(f"run_at:      {s.run_at or ''}")
    else:
        click.echo(f"cron_format: {s.cron_format}")
    click.echo(f"active:      {s.active}")
    if s.delete_after_run:
        click.echo(f"once:        {s.delete_after_run}")
    if s.task_params is not None:
        _emit_task_params(s.task_params)
    click.echo(f"project_id:  {s.project_id}")
