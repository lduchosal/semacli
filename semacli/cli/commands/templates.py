"""Templates commands (list, show, delete + the create/update/audit/sync satellites)."""

import json
from typing import Any

import click

from semacli.core.models import Template
from semacli.core.overrides import ALL_OVERRIDES, NO_OVERRIDES, OVERRIDE_TOGGLES, allowed_words
from semacli.core.resolve import resolve_template

from .._crud import opts_from_ctx, setup, store_opts
from .._groups import AliasedGroup, SectionedRootGroup
from ..decorators import common_options, output_options, project_option
from ..handlers import OutputFormatter, fail_on_error
from ._template_audit import audit_cmd
from ._template_sync import sync_cmd
from ._template_write import create_cmd, update_cmd

TEMPLATE_HELP = """\
Templates: recipes that combine a repository, an inventory, an
environment and a playbook path. A template is what you actually run
via `sem task run` (or the shortcut `sem run`).

A template references:
  - 1 repository    (where the playbook lives)
  - 1 inventory     (which hosts to target)
  - 0/1 environment (extra_vars + secrets)
  - playbook path   (relative to the repo)

It also decides which per-run overrides are allowed (--limit, --tags,
...). An override left out is not an error on the server: Semaphore
drops it and runs anyway — `sem run` refuses instead, and
`sem template audit` finds those templates before you need one.

Calling `sem template` without a subcommand lists templates.
"""

TEMPLATE_EPILOG = """\
Examples:
  sem template                          # list
  sem template show mtree
  sem template create --name deploy-prod \\
       --playbook deploy/prod.yml \\
       --repository ansible --inventory prod --environment secrets
  sem template create --name reboot --playbook reboot.yml \\
       --repository ansible --inventory prod --allow-override limit
  sem template update mtree --environment staging
  sem template audit                    # who would ignore --limit?
  sem template sync --manifest templates.yml --dry-run
  sem template delete deploy-prod
  sem run mtree                         # run by name (shortcut)
"""


def _overrides_label(tpl: Template) -> str:
    """Compact summary of the per-run overrides a template allows."""
    allowed = allowed_words(tpl.task_params.model_dump())
    if len(allowed) == len(OVERRIDE_TOGGLES):
        return ALL_OVERRIDES
    return ",".join(allowed) if allowed else NO_OVERRIDES


def _emit_list_json(templates: list[Template]) -> None:
    """Emit the template list as a JSON array of full dumps."""
    click.echo(json.dumps([t.model_dump() for t in templates], indent=2))


def _emit_list_text(templates: list[Template]) -> None:
    """Emit the template list in compact text form, with an empty fallback + total line."""
    if not templates:
        click.echo("No templates found")
        return
    for t in templates:
        click.echo(f"{t.id:>4}  {t.name}  ({t.playbook or '?'})  [{_overrides_label(t)}]")
    click.echo(f"\nTotal: {len(templates)} template(s)")


def _emit_show_json(t: Template) -> None:
    """Emit one template as a full JSON dump."""
    click.echo(json.dumps(t.model_dump(), indent=2))


def _emit_show_text(t: Template) -> None:
    """Emit one template as key-value lines, including the allowed overrides summary."""
    click.echo(f"id:             {t.id}")
    click.echo(f"name:           {t.name}")
    click.echo(f"project_id:     {t.project_id}")
    click.echo(f"playbook:       {t.playbook}")
    click.echo(f"inventory_id:   {t.inventory_id}")
    click.echo(f"repository_id:  {t.repository_id}")
    click.echo(f"environment_id: {t.environment_id}")
    if t.view_id:
        click.echo(f"view_id:        {t.view_id}")
    if t.app:
        click.echo(f"app:            {t.app}")
    if t.arguments:
        click.echo(f"arguments:      {t.arguments}")
    allowed = allowed_words(t.task_params.model_dump())
    click.echo(f"overrides:      {', '.join(allowed) if allowed else 'none (run flags refused)'}")
    if t.survey_vars:
        click.echo(f"survey_vars:    {', '.join(v.name for v in t.survey_vars)}")
    if t.description:
        click.echo(f"description:    {t.description}")


def _run_list(opts: dict[str, Any]) -> None:
    """Fetch and emit the template list (bare group form and hidden `list`)."""
    client, pid = setup(opts)
    OutputFormatter.format_verbose(f"GET /project/{pid}/templates", opts["verbose"])
    templates = client.get_templates(pid)
    if opts["output_json"]:
        _emit_list_json(templates)
    elif not opts["quiet"]:
        _emit_list_text(templates)


@click.group(
    "template",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=TEMPLATE_HELP,
    epilog=TEMPLATE_EPILOG,
)
@click.pass_context
@common_options
@output_options
@project_option
@fail_on_error
def templates_group(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """List templates when invoked without a subcommand."""
    store_opts(
        ctx,
        config=config,
        verbose=verbose,
        output_json=output_json,
        quiet=quiet,
        project_override=project_override,
    )
    if ctx.invoked_subcommand is not None:
        return
    _run_list(ctx.obj)


# Hidden alias for the bare form (UX.md § 4.1): `sem template list`
# and `sem template ls` work but stay out of --help.
@templates_group.command("list", hidden=True)
@click.pass_context
@fail_on_error
def list_cmd(ctx: click.Context) -> None:
    """List templates (alias of the bare `sem template`)."""
    _run_list(ctx.obj)


templates_group.add_alias("ls", "list")


@templates_group.command("show")
@click.argument("template")
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, template: str) -> None:
    """Show full template details."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    template_id = resolve_template(client, pid, template)
    OutputFormatter.format_verbose(f"GET /project/{pid}/templates/{template_id}", opts["verbose"])
    tpl = client.get_template(pid, template_id)
    if opts["output_json"]:
        _emit_show_json(tpl)
    elif not opts["quiet"]:
        _emit_show_text(tpl)


@templates_group.command("delete")
@click.argument("template")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, template: str, *, yes: bool) -> None:
    """Delete a template. Fails if referenced by a schedule."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    tpl = client.get_template(pid, resolve_template(client, pid, template))
    if not yes and not click.confirm(f"Delete template '{tpl.name}' (id={tpl.id})?", default=False):
        click.echo("aborted.", err=True)
        return
    client.delete_template(pid, tpl.id)
    if not opts["quiet"]:
        click.echo(f"deleted template id={tpl.id}")


templates_group.add_command(create_cmd)
templates_group.add_command(update_cmd)
templates_group.add_command(audit_cmd)
templates_group.add_command(sync_cmd)


def register_templates_commands(main_group: SectionedRootGroup) -> None:
    """Register the `templates` command group."""
    main_group.add_command(templates_group)
    main_group.set_category("template", "read")
    main_group.add_alias("templates", "template")
