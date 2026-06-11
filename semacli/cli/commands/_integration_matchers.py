"""`sem integration matchers` — payload matchers of an integration."""

import json

import click

from semacli.core.models import IntegrationMatcher

from .._crud import opts_from_ctx, setup
from .._groups import AliasedGroup
from ..handlers import fail_on_error

MATCHERS_HELP = """\
Matchers for a given integration.

A matcher filters incoming webhook payloads: only payloads whose
`{method}.{key}` field matches `{value}` (per `match_type`) trigger
the template.

  method      = body | header
  match_type  = equals | contains | regex

Calling `sem integration matchers <iid>` without a subcommand
lists the matchers attached to that integration.
"""

MATCHERS_EPILOG = """\
Examples:
  sem integration matchers 4                                # list
  sem integration matchers 4 add --name only-main \\
       --match-type equals --method body --key ref --value refs/heads/main
  sem integration matchers 4 add --name only-prod-tag \\
       --match-type regex --method body --key ref --value '^refs/tags/v[0-9]+'
  sem integration matchers 4 update 7 --value refs/heads/release
  sem integration matchers 4 remove 7
"""


def _emit_matchers_text(items: list[IntegrationMatcher]) -> None:
    """Emit the matcher list in compact text form, with an empty fallback + total line."""
    if not items:
        click.echo("No matchers found")
        return
    for m in items:
        click.echo(f"{m.id:>4}  {m.method:<6}  {m.match_type:<8}  {m.key}={m.value!r}  ({m.name})")
    click.echo(f"\nTotal: {len(items)} matcher(s)")


@click.group(
    "matchers",
    cls=AliasedGroup,
    invoke_without_command=True,
    help=MATCHERS_HELP,
    epilog=MATCHERS_EPILOG,
)
@click.argument("integration_id", type=int)
@click.pass_context
@fail_on_error
def matchers_group(ctx: click.Context, integration_id: int) -> None:
    """List matchers when invoked without a subcommand."""
    opts = opts_from_ctx(ctx)
    opts["integration_id"] = integration_id
    if ctx.invoked_subcommand is not None:
        return
    client, pid = setup(opts)
    items = client.list_integration_matchers(pid, integration_id)
    if opts["output_json"]:
        click.echo(json.dumps([m.model_dump() for m in items], indent=2))
    elif not opts["quiet"]:
        _emit_matchers_text(items)


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
@fail_on_error
def matchers_add_cmd(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    name: str,
    match_type: str,
    method: str,
    key: str,
    value: str,
) -> None:
    """Add a matcher to the integration."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
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


@matchers_group.command("update")
@click.argument("matcher_id", type=int)
@click.option("--name", default=None)
@click.option("--match-type", default=None, type=click.Choice(["equals", "contains", "regex"]))
@click.option("--method", default=None, type=click.Choice(["body", "header"]))
@click.option("--key", default=None)
@click.option("--value", default=None)
@click.pass_context
@fail_on_error
def matchers_update_cmd(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    matcher_id: int,
    name: str | None,
    match_type: str | None,
    method: str | None,
    key: str | None,
    value: str | None,
) -> None:
    """Update a matcher."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
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


@matchers_group.command("remove")
@click.argument("matcher_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_context
@fail_on_error
def matchers_remove_cmd(ctx: click.Context, matcher_id: int, *, yes: bool) -> None:
    """Remove a matcher."""
    opts = opts_from_ctx(ctx)
    if not yes and not click.confirm(f"Remove matcher id={matcher_id}?", default=False):
        click.echo("aborted.", err=True)
        return
    client, pid = setup(opts)
    client.remove_integration_matcher(pid, opts["integration_id"], matcher_id)
    if not opts["quiet"]:
        click.echo(f"removed matcher id={matcher_id}")
