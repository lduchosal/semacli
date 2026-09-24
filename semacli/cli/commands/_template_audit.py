"""`sem template audit` — find templates that would ignore a run override.

A template whose ``task_params`` forbids an override does not make the
run fail on the server: Semaphore drops the flag and runs anyway. Since
ken #827 semacli refuses such a run, so auditing tells you up front
which templates cannot be targeted with --limit before someone needs it
at 3am. Exit code 1 when at least one template is missing an override,
so the command works as a periodic check.
"""

import json

import click

from semacli.core.models import Template
from semacli.core.overrides import OVERRIDE_TOGGLES, missing_words

from .._crud import opts_from_ctx, setup
from ..handlers import fail_on_error

AUDIT_EPILOG = """\
Examples:
  sem template audit                       # who ignores --limit?
  sem template audit --require limit,tags
  sem template --json audit
"""


def _offenders(templates: list[Template], required: list[str]) -> list[tuple[Template, list[str]]]:
    """Pair each template with the required overrides it forbids."""
    pairs = ((t, missing_words(t.task_params.model_dump(), required)) for t in templates)
    return [(t, missing) for t, missing in pairs if missing]


def _emit_text(found: list[tuple[Template, list[str]]], total: int, required: list[str]) -> None:
    """Print the offenders, or a one-line all-clear."""
    if not found:
        click.echo(f"All {total} template(s) allow: {', '.join(required)}")
        return
    for tpl, missing in found:
        click.echo(f"{tpl.id:>4}  {tpl.name}  missing: {', '.join(missing)}")
    click.echo(f"\nTotal: {len(found)} of {total} template(s) would ignore a run override")


def _parse_required(_ctx: click.Context, _param: click.Parameter, value: str) -> list[str]:
    """Click callback: split --require and reject unknown override words.

    Parsing here (not in the body) keeps a bad flag a clean exit 2:
    click raises UsageError before the fail_on_error funnel is entered.
    """
    words = [w.strip() for w in value.split(",") if w.strip()]
    unknown = sorted(set(words) - set(OVERRIDE_TOGGLES))
    if unknown:
        msg = f"unknown override(s): {', '.join(unknown)}"
        raise click.BadParameter(msg)
    return words


@click.command("audit", epilog=AUDIT_EPILOG)
@click.option(
    "--require",
    "required",
    default="limit",
    show_default=True,
    callback=_parse_required,
    help=f"Overrides every template must allow ({'/'.join(OVERRIDE_TOGGLES)}).",
)
@click.pass_context
@fail_on_error
def audit_cmd(ctx: click.Context, required: list[str]) -> None:
    """List templates whose task_params forbid a required override."""
    opts = opts_from_ctx(ctx)
    client, pid = setup(opts)
    templates = client.get_templates(pid)
    found = _offenders(templates, required)
    if opts["output_json"]:
        click.echo(
            json.dumps(
                [{"id": t.id, "name": t.name, "missing": m} for t, m in found],
                indent=2,
            )
        )
    elif not opts["quiet"]:
        _emit_text(found, len(templates), required)
    if found:
        raise SystemExit(1)
