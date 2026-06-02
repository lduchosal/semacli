"""Templates commands (list + show)."""

import json
from dataclasses import asdict
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Template

from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import OutputFormatter, handle_error


def _emit_list_json(templates: list[Template]) -> None:
    click.echo(json.dumps([asdict(t) for t in templates], indent=2))


def _emit_list_text(templates: list[Template]) -> None:
    if not templates:
        click.echo("No templates found")
        return
    for t in templates:
        click.echo(f"{t.id:>4}  {t.name}  ({t.playbook or '?'})")
    click.echo(f"\nTotal: {len(templates)} template(s)")


def _emit_show_json(t: Template) -> None:
    click.echo(json.dumps(asdict(t), indent=2))


def _emit_show_text(t: Template) -> None:
    click.echo(f"id:             {t.id}")
    click.echo(f"name:           {t.name}")
    click.echo(f"project_id:     {t.project_id}")
    click.echo(f"playbook:       {t.playbook}")
    click.echo(f"inventory_id:   {t.inventory_id}")
    click.echo(f"repository_id:  {t.repository_id}")
    click.echo(f"environment_id: {t.environment_id}")
    if t.description:
        click.echo(f"description:    {t.description}")


def register_templates_commands(main_group: Any) -> None:
    """Register the `templates` command group."""

    @main_group.group("templates", invoke_without_command=True)
    @click.pass_context
    @common_options
    @output_options
    @project_option
    def templates_group(
        ctx: click.Context,
        config: str,
        verbose: int,
        output_json: bool,
        quiet: bool,
        project_override: int | None,
    ) -> None:
        """List or show Semaphore templates."""
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
        if ctx.invoked_subcommand is not None:
            return
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, project_override)
            OutputFormatter.format_verbose(f"GET /project/{pid}/templates", verbose)
            templates = client.get_templates(pid)
            if output_json:
                _emit_list_json(templates)
            elif not quiet:
                _emit_list_text(templates)
        except Exception as e:
            handle_error(e, verbose)

    @templates_group.command("show")
    @click.argument("template_id", type=int)
    @click.pass_context
    def show_cmd(ctx: click.Context, template_id: int) -> None:
        """Show full template details."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            OutputFormatter.format_verbose(
                f"GET /project/{pid}/templates/{template_id}", verbose
            )
            tpl = client.get_template(pid, template_id)
            if opts["output_json"]:
                _emit_show_json(tpl)
            elif not opts["quiet"]:
                _emit_show_text(tpl)
        except Exception as e:
            handle_error(e, verbose)
