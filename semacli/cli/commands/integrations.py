"""`semacli integration` — inbound webhooks + their matchers."""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import load_config
from semacli.core.models import Integration, IntegrationMatcher

from ..decorators import common_options, output_options, project_option, resolve_project
from ..handlers import handle_error

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

Calling `semacli integration` without a subcommand lists integrations.
"""

INTEGRATION_EPILOG = """\
Examples:
  semacli integration                                          # list
  semacli integration show 4
  semacli integration create --name gh-push --template 5 \\
       --auth-method github --auth-secret-id 12
  semacli integration update 4 --template 8
  semacli integration delete 4
  semacli integration matchers 4                               # list matchers of integration 4
  semacli integration matchers 4 add --name only-main \\
       --match-type equals --method body --key ref --value refs/heads/main
"""

MATCHERS_HELP = """\
Matchers for a given integration.

A matcher filters incoming webhook payloads: only payloads whose
`{method}.{key}` field matches `{value}` (per `match_type`) trigger
the template.

  method      = body | header
  match_type  = equals | contains | regex

Calling `semacli integration matchers <iid>` without a subcommand
lists the matchers attached to that integration.
"""

MATCHERS_EPILOG = """\
Examples:
  semacli integration matchers 4                                # list
  semacli integration matchers 4 add --name only-main \\
       --match-type equals --method body --key ref --value refs/heads/main
  semacli integration matchers 4 add --name only-prod-tag \\
       --match-type regex --method body --key ref --value '^refs/tags/v[0-9]+'
  semacli integration matchers 4 update 7 --value refs/heads/release
  semacli integration matchers 4 remove 7
"""


def _emit_int_list_text(items: list[Integration]) -> None:
    if not items:
        click.echo("No integrations found")
        return
    for i in items:
        click.echo(f"{i.id:>4}  tpl={i.template_id}  auth={i.auth_method:<8}  {i.name}")
    click.echo(f"\nTotal: {len(items)} integration(s)")


def _emit_int_show_text(i: Integration) -> None:
    click.echo(f"id:             {i.id}")
    click.echo(f"name:           {i.name}")
    click.echo(f"template_id:    {i.template_id}")
    click.echo(f"auth_method:    {i.auth_method}")
    click.echo(f"auth_header:    {i.auth_header}")
    click.echo(f"auth_secret_id: {i.auth_secret_id}")
    click.echo(f"project_id:     {i.project_id}")


def _emit_matchers_text(items: list[IntegrationMatcher]) -> None:
    if not items:
        click.echo("No matchers found")
        return
    for m in items:
        click.echo(f"{m.id:>4}  {m.method:<6}  {m.match_type:<8}  {m.key}={m.value!r}  ({m.name})")
    click.echo(f"\nTotal: {len(items)} matcher(s)")


def register_integrations_commands(main_group: Any) -> None:
    """Register `semacli integration` and its `matchers` subgroup."""

    @main_group.group(
        "integration",
        invoke_without_command=True,
        help=INTEGRATION_HELP,
        epilog=INTEGRATION_EPILOG,
    )
    @click.pass_context
    @common_options
    @output_options
    @project_option
    def integration_group(
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
        try:
            cfg = load_config(config)
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, project_override)
            items = client.list_integrations(pid)
            if output_json:
                click.echo(json.dumps([i.model_dump() for i in items], indent=2))
            elif not quiet:
                _emit_int_list_text(items)
        except Exception as e:
            handle_error(e, verbose)

    @integration_group.command("show")
    @click.argument("integration_id", type=int)
    @click.pass_context
    def show_cmd(ctx: click.Context, integration_id: int) -> None:
        """Show one integration with its webhook URL and auth config."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            i = client.get_integration(pid, integration_id)
            if opts["output_json"]:
                click.echo(json.dumps(i.model_dump(), indent=2))
            elif not opts["quiet"]:
                _emit_int_show_text(i)
        except Exception as e:
            handle_error(e, verbose)

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
    def create_cmd(
        ctx: click.Context,
        name: str,
        template_id: int,
        auth_method: str,
        auth_header: str,
        auth_secret_id: int,
    ) -> None:
        """Create an integration."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
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
        except Exception as e:
            handle_error(e, verbose)

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
    def update_cmd(
        ctx: click.Context,
        integration_id: int,
        name: str | None,
        template_id: int | None,
        auth_method: str | None,
        auth_header: str | None,
        auth_secret_id: int | None,
    ) -> None:
        """Update mutable fields of an integration."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
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
        except Exception as e:
            handle_error(e, verbose)

    @integration_group.command("delete")
    @click.argument("integration_id", type=int)
    @click.option("--yes", is_flag=True)
    @click.pass_context
    def delete_cmd(ctx: click.Context, integration_id: int, yes: bool) -> None:
        """Delete an integration and its matchers."""
        opts = ctx.obj
        verbose = opts["verbose"]
        if not yes and not click.confirm(f"Delete integration id={integration_id}?", default=False):
            click.echo("aborted.", err=True)
            return
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            client.delete_integration(pid, integration_id)
            if not opts["quiet"]:
                click.echo(f"deleted integration id={integration_id}")
        except Exception as e:
            handle_error(e, verbose)

    @integration_group.group(
        "matchers",
        invoke_without_command=True,
        help=MATCHERS_HELP,
        epilog=MATCHERS_EPILOG,
    )
    @click.argument("integration_id", type=int)
    @click.pass_context
    def matchers_group(ctx: click.Context, integration_id: int) -> None:
        opts = ctx.obj
        opts["integration_id"] = integration_id
        if ctx.invoked_subcommand is not None:
            return
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            items = client.list_integration_matchers(pid, integration_id)
            if opts["output_json"]:
                click.echo(json.dumps([m.model_dump() for m in items], indent=2))
            elif not opts["quiet"]:
                _emit_matchers_text(items)
        except Exception as e:
            handle_error(e, verbose)

    @matchers_group.command("add")
    @click.option("--name", required=True)
    @click.option(
        "--match-type",
        required=True,
        type=click.Choice(["equals", "contains", "regex"]),
    )
    @click.option(
        "--method",
        required=True,
        type=click.Choice(["body", "header"]),
        help="Where in the request to look for the field.",
    )
    @click.option("--key", required=True, help="Field name to match.")
    @click.option("--value", required=True, help="Expected value (or regex).")
    @click.pass_context
    def matchers_add_cmd(
        ctx: click.Context,
        name: str,
        match_type: str,
        method: str,
        key: str,
        value: str,
    ) -> None:
        """Add a matcher to the integration."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            m = client.add_integration_matcher(
                pid,
                opts["integration_id"],
                name=name,
                match_type=match_type,
                method=method,
                key=key,
                value=value,
            )
            if opts["output_json"]:
                click.echo(json.dumps(m.model_dump(), indent=2))
            elif not opts["quiet"]:
                click.echo(f"added matcher id={m.id}")
        except Exception as e:
            handle_error(e, verbose)

    @matchers_group.command("update")
    @click.argument("matcher_id", type=int)
    @click.option("--name", default=None)
    @click.option(
        "--match-type",
        default=None,
        type=click.Choice(["equals", "contains", "regex"]),
    )
    @click.option("--method", default=None, type=click.Choice(["body", "header"]))
    @click.option("--key", default=None)
    @click.option("--value", default=None)
    @click.pass_context
    def matchers_update_cmd(
        ctx: click.Context,
        matcher_id: int,
        name: str | None,
        match_type: str | None,
        method: str | None,
        key: str | None,
        value: str | None,
    ) -> None:
        """Update a matcher."""
        opts = ctx.obj
        verbose = opts["verbose"]
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            client.update_integration_matcher(
                pid,
                opts["integration_id"],
                matcher_id,
                name=name,
                match_type=match_type,
                method=method,
                key=key,
                value=value,
            )
            if not opts["quiet"]:
                click.echo(f"updated matcher id={matcher_id}")
        except Exception as e:
            handle_error(e, verbose)

    @matchers_group.command("remove")
    @click.argument("matcher_id", type=int)
    @click.option("--yes", is_flag=True)
    @click.pass_context
    def matchers_remove_cmd(ctx: click.Context, matcher_id: int, yes: bool) -> None:
        """Remove a matcher."""
        opts = ctx.obj
        verbose = opts["verbose"]
        if not yes and not click.confirm(f"Remove matcher id={matcher_id}?", default=False):
            click.echo("aborted.", err=True)
            return
        try:
            cfg = load_config(opts["config"])
            client = SemaphoreClient(cfg, verbose=verbose)
            pid = resolve_project(cfg, opts["project_override"])
            client.remove_integration_matcher(pid, opts["integration_id"], matcher_id)
            if not opts["quiet"]:
                click.echo(f"removed matcher id={matcher_id}")
        except Exception as e:
            handle_error(e, verbose)

    main_group.commands["integration"].category = "read"
    main_group.add_alias("integrations", "integration")
