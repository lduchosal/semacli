"""Shared helpers for the CRUD command groups (inventories, environments,
repositories, keys, schedules)."""

import json
from collections.abc import Callable
from typing import Any

import click
from pydantic import BaseModel

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config

from .decorators import resolve_project


def setup(opts: dict[str, Any]) -> tuple[SemaphoreClient, int]:
    """Resolve config, client, and project_id from the Click context's stored opts."""
    cfg = load_config(opts["config"])
    client = SemaphoreClient(cfg, verbose=opts["verbose"])
    pid = resolve_project(cfg, opts["project_override"])
    return client, pid


def emit_json_single(obj: Any) -> None:
    """Emit a single pydantic model (or dict) as JSON."""
    payload = obj.model_dump(by_alias=True) if isinstance(obj, BaseModel) else obj
    click.echo(json.dumps(payload, indent=2))


def emit_json_list(items: list[Any]) -> None:
    """Emit a list of pydantic models as JSON."""
    payload = [o.model_dump(by_alias=True) if isinstance(o, BaseModel) else o for o in items]
    click.echo(json.dumps(payload, indent=2))


def emit_text_list(
    items: list[Any],
    label: str,
    text_formatter: Callable[[Any], str],
) -> None:
    """Emit a list in compact text form, with an empty fallback + total line."""
    if not items:
        click.echo(f"No {label} found")
        return
    for item in items:
        click.echo(text_formatter(item))
    click.echo(f"\nTotal: {len(items)} {label}")


def confirm_delete(yes: bool, resource: str, resource_id: int) -> None:
    """Prompt the user to confirm a destructive delete unless --yes is set."""
    if not yes:
        click.confirm(
            f"Delete {resource} {resource_id}? This cannot be undone.",
            abort=True,
        )


def opts_from_ctx(ctx: click.Context) -> dict[str, Any]:
    """Pull the shared options dict that the group stored on ctx.obj."""
    return ctx.obj  # type: ignore[no-any-return]


def store_opts(
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """Stash the group-level options into ctx.obj for subcommands."""
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
