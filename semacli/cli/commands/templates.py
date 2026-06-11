"""Templates commands (list + show)."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Template

from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import OutputFormatter, handle_error

TEMPLATE_HELP = """\
Templates: recipes that combine a repository, an inventory, an
environment and a playbook path. A template is what you actually run
via `sem task run` (or the shortcut `sem run`).

A template references:
  - 1 repository    (where the playbook lives)
  - 1 inventory     (which hosts to target)
  - 0/1 environment (extra_vars + secrets)
  - playbook path   (relative to the repo)

Calling `sem template` without a subcommand lists templates.
"""

TEMPLATE_EPILOG = """\
Examples:
  sem template                          # list
  sem template show 5
  sem template create --name deploy-prod \\
       --playbook deploy/prod.yml \\
       --repository 4 --inventory 42 --environment 7
  sem template update 5 --environment 8
  sem template delete 5
  sem run mtree                         # run by name (shortcut)
"""


def _emit_list_json(templates: list[Template]) -> None:
    click.echo(json.dumps([t.model_dump() for t in templates], indent=2))


def _emit_list_text(templates: list[Template]) -> None:
    if not templates:
        click.echo("No templates found")
        return
    for t in templates:
        click.echo(f"{t.id:>4}  {t.name}  ({t.playbook or '?'})")
    click.echo(f"\nTotal: {len(templates)} template(s)")


def _emit_show_json(t: Template) -> None:
    click.echo(json.dumps(t.model_dump(), indent=2))


def _emit_show_text(t: Template) -> None:
    click.echo(f"id:             {t.id}")
    click.echo(f"name:           {t.name}")
    click.echo(f"project_id:     {t.project_id}")
    click.echo(f"playbook:       {t.playbook}")
    click.echo(f"inventory_id:   {t.inventory_id}")
    click.echo(f"repository_id:  {t.repository_id}")
    click.echo(f"environment_id: {t.environment_id}")
    if t.app:
        click.echo(f"app:            {t.app}")
    p = t.task_params
    allowed = [
        label
        for label, ok in (
            ("limit", p.allow_override_limit),
            ("tags", p.allow_override_tags),
            ("skip-tags", p.allow_override_skip_tags),
            ("debug", p.allow_debug),
            ("inventory", p.allow_override_inventory),
        )
        if ok
    ]
    click.echo(f"overrides:      {', '.join(allowed) if allowed else 'none (run flags refused)'}")
    if t.description:
        click.echo(f"description:    {t.description}")


def _run_list(opts: dict[str, Any]) -> None:
    """Fetch and emit the template list (bare group form and hidden `list`)."""
    verbose = opts["verbose"]
    try:
        cfg = load_config(opts["config"])
        client = SemaphoreClient(cfg, verbose=verbose)
        pid = resolve_project(cfg, opts["project_override"])
        OutputFormatter.format_verbose(f"GET /project/{pid}/templates", verbose)
        templates = client.get_templates(pid)
        if opts["output_json"]:
            _emit_list_json(templates)
        elif not opts["quiet"]:
            _emit_list_text(templates)
    except Exception as e:
        handle_error(e, verbose)


def register_templates_commands(main_group: Any) -> None:
    """Register the `templates` command group."""

    @main_group.group(
        "template", invoke_without_command=True, help=TEMPLATE_HELP, epilog=TEMPLATE_EPILOG
    )
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
        _run_list(ctx.obj)

    # Hidden alias for the bare form (UX.md § 4.1): `sem template list`
    # and `sem template ls` work but stay out of --help.
    @templates_group.command("list", hidden=True)
    @click.pass_context
    def list_cmd(ctx: click.Context) -> None:
        """List templates (alias of the bare `sem template`)."""
        _run_list(ctx.obj)

    templates_group.add_alias("ls", "list")

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
            OutputFormatter.format_verbose(f"GET /project/{pid}/templates/{template_id}", verbose)
            tpl = client.get_template(pid, template_id)
            if opts["output_json"]:
                _emit_show_json(tpl)
            elif not opts["quiet"]:
                _emit_show_text(tpl)
        except Exception as e:
            handle_error(e, verbose)

    @templates_group.command("create")
    @click.option("--name", required=True)
    @click.option("--playbook", required=True, help="Path of the playbook inside the repo.")
    @click.option(
        "--repository",
        "repository_id",
        required=True,
        type=int,
        help="Linked repository id.",
    )
    @click.option(
        "--inventory",
        "inventory_id",
        required=True,
        type=int,
        help="Linked inventory id.",
    )
    @click.option(
        "--environment",
        "environment_id",
        default=None,
        type=int,
        help="Optional environment id.",
    )
    @click.option("--description", default="")
    @click.option(
        "--arguments",
        default="",
        help='Default ansible-playbook arguments as a JSON array, e.g. \'["--limit", "web1"]\'.',
    )
    @click.option(
        "--app",
        default="ansible",
        show_default=True,
        help="Runner app of the template (ansible, terraform, bash, ...).",
    )
    @click.pass_context
    def create_cmd(
        ctx: click.Context,
        name: str,
        playbook: str,
        repository_id: int,
        inventory_id: int,
        environment_id: int | None,
        description: str,
        arguments: str,
        app: str,
    ) -> None:
        """Create a template."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            tpl = client.create_template(
                pid,
                name=name,
                playbook=playbook,
                inventory_id=inventory_id,
                repository_id=repository_id,
                environment_id=environment_id,
                description=description,
                arguments=arguments,
                app=app,
            )
            if opts["output_json"]:
                _emit_show_json(tpl)
            elif not opts["quiet"]:
                click.echo(f"created template id={tpl.id}")
        except Exception as e:
            handle_error(e, verbose)

    @templates_group.command("update")
    @click.argument("template_id", type=int)
    @click.option("--name", default=None)
    @click.option("--playbook", default=None)
    @click.option("--repository", "repository_id", default=None, type=int)
    @click.option("--inventory", "inventory_id", default=None, type=int)
    @click.option("--environment", "environment_id", default=None, type=int)
    @click.option("--description", default=None)
    @click.option("--arguments", default=None)
    @click.pass_context
    def update_cmd(
        ctx: click.Context,
        template_id: int,
        name: str | None,
        playbook: str | None,
        repository_id: int | None,
        inventory_id: int | None,
        environment_id: int | None,
        description: str | None,
        arguments: str | None,
    ) -> None:
        """Update mutable fields of a template."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            client.update_template(
                pid,
                template_id,
                name=name,
                playbook=playbook,
                repository_id=repository_id,
                inventory_id=inventory_id,
                environment_id=environment_id,
                description=description,
                arguments=arguments,
            )
            if not opts["quiet"]:
                click.echo(f"updated template id={template_id}")
        except Exception as e:
            handle_error(e, verbose)

    @templates_group.command("delete")
    @click.argument("template_id", type=int)
    @click.option("--yes", is_flag=True, help="Skip confirmation")
    @click.pass_context
    def delete_cmd(ctx: click.Context, template_id: int, yes: bool) -> None:
        """Delete a template. Fails if referenced by a schedule."""
        opts = ctx.obj
        verbose = opts["verbose"]
        if not yes and not click.confirm(f"Delete template id={template_id}?", default=False):
            click.echo("aborted.", err=True)
            return
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            client.delete_template(pid, template_id)
            if not opts["quiet"]:
                click.echo(f"deleted template id={template_id}")
        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["template"].category = "read"
    main_group.add_alias("templates", "template")
