"""`sem integration` — inbound webhooks + their matchers."""

import json

import click

from semacli.core.models import Integration

from .._crud import opts_from_ctx, setup, store_opts
from .._groups import AliasedGroup, SectionedRootGroup
from ..decorators import common_options, output_options, project_option
from ..handlers import fail_on_error
from ._integration_matchers import matchers_group

INTEGRATION_HELP = """\
Integrations: inbound webhooks that launch a template when an external
system POSTs to a Semaphore URL.

Each integration:
  - belongs to one project,
  - targets one template,
  - has an auth_method (none / github / hmac / token),
  - exposes a webhook URL Semaphore generates server-side.

Use the `matchers` subgroup to gate which incoming payloads trigger
the template.

Calling `sem integration` without a subcommand lists integrations.
"""

INTEGRATION_EPILOG = """\
Examples:
  sem integration                                          # list
  sem integration show 4
  sem integration create --name gh-push --template 5 \\
       --auth-method github --auth-secret-id 12
  sem integration update 4 --template 8
  sem integration delete 4
  sem integration matchers 4                               # list matchers of integration 4
  sem integration matchers 4 add --name only-main \\
       --match-type equals --method body --key ref --value refs/heads/main
"""


def _emit_int_list_text(items: list[Integration]) -> None:
    """Emit the integration list in compact text form, with an empty fallback + total line."""
    if not items:
        click.echo("No integrations found")
        return
    for i in items:
        click.echo(f"{i.id:>4}  tpl={i.template_id}  auth={i.auth_method:<8}  {i.name}")
    click.echo(f"\nTotal: {len(items)} integration(s)")


def _emit_int_show_text(i: Integration) -> None:
    """Emit one integration as key-value lines."""
    click.echo(f"id:             {i.id}")
    click.echo(f"name:           {i.name}")
    click.echo(f"template_id:    {i.template_id}")
    click.echo(f"auth_method:    {i.auth_method}")
    click.echo(f"auth_header:    {i.auth_header}")
    click.echo(f"auth_secret_id: {i.auth_secret_id}")
    click.echo(f"project_id:     {i.project_id}")


@click.group(
    "integration",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=INTEGRATION_HELP,
    epilog=INTEGRATION_EPILOG,
)
@click.pass_context
@common_options
@output_options
@project_option
@fail_on_error
def integration_group(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    *,
    config: str,
    verbose: int,
    output_json: bool,
    quiet: bool,
    project_override: int | None,
) -> None:
    """List integrations when invoked without a subcommand."""
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
    client, pid = setup(opts_from_ctx(ctx))
    items = client.list_integrations(pid)
    if output_json:
        click.echo(json.dumps([i.model_dump() for i in items], indent=2))
    elif not quiet:
        _emit_int_list_text(items)


@integration_group.command("show")
@click.argument("integration_id", type=int)
@click.pass_context
@fail_on_error
def show_cmd(ctx: click.Context, integration_id: int) -> None:
    """Show one integration with its webhook URL and auth config."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    i = client.get_integration(pid, integration_id)
    if opts["output_json"]:
        click.echo(json.dumps(i.model_dump(), indent=2))
    elif not opts["quiet"]:
        _emit_int_show_text(i)


@integration_group.command("create")
@click.option("--name", required=True)
@click.option("--template", "template_id", required=True, type=int)
@click.option(
    "--auth-method",
    default="none",
    type=click.Choice(["none", "github", "hmac", "token"]),
)
@click.option(
    "--auth-header",
    default="",
    help="Header carrying the auth value (for auth-method=token).",
)
@click.option(
    "--auth-secret-id",
    default=0,
    type=int,
    help="Linked access key id holding the HMAC / token secret.",
)
@click.pass_context
@fail_on_error
def create_cmd(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    *,
    name: str,
    template_id: int,
    auth_method: str,
    auth_header: str,
    auth_secret_id: int,
) -> None:
    """Create an integration."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    i = client.create_integration(
        pid,
        name=name,
        template_id=template_id,
        auth_method=auth_method,
        auth_header=auth_header,
        auth_secret_id=auth_secret_id,
    )
    if opts["output_json"]:
        click.echo(json.dumps(i.model_dump(), indent=2))
    elif not opts["quiet"]:
        click.echo(f"created integration id={i.id}")


@integration_group.command("update")
@click.argument("integration_id", type=int)
@click.option("--name", default=None)
@click.option("--template", "template_id", default=None, type=int)
@click.option(
    "--auth-method",
    default=None,
    type=click.Choice(["none", "github", "hmac", "token"]),
)
@click.option("--auth-header", default=None)
@click.option("--auth-secret-id", default=None, type=int)
@click.pass_context
@fail_on_error
def update_cmd(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    *,
    integration_id: int,
    name: str | None,
    template_id: int | None,
    auth_method: str | None,
    auth_header: str | None,
    auth_secret_id: int | None,
) -> None:
    """Update mutable fields of an integration."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    client.update_integration(
        pid,
        integration_id,
        name=name,
        template_id=template_id,
        auth_method=auth_method,
        auth_header=auth_header,
        auth_secret_id=auth_secret_id,
    )
    if not opts["quiet"]:
        click.echo(f"updated integration id={integration_id}")


@integration_group.command("delete")
@click.argument("integration_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_context
@fail_on_error
def delete_cmd(ctx: click.Context, integration_id: int, *, yes: bool) -> None:
    """Delete an integration and its matchers."""
    opts = opts_from_ctx(ctx)
    if not yes and not click.confirm(f"Delete integration id={integration_id}?", default=False):
        click.echo("aborted.", err=True)
        return
    client, pid = setup(opts)
    client.delete_integration(pid, integration_id)
    if not opts["quiet"]:
        click.echo(f"deleted integration id={integration_id}")


integration_group.add_command(matchers_group)


def register_integrations_commands(main_group: SectionedRootGroup) -> None:
    """Register `sem integration` and its `matchers` subgroup."""
    main_group.add_command(integration_group)
    main_group.set_category("integration", "read")
    main_group.add_alias("integrations", "integration")
