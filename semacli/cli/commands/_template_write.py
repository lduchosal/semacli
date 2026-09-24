"""`sem template create` / `update` — the write half of the template group.

Split out of ``templates.py`` to keep both files inside the 300-line
budget of the quality gate.
"""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.guards import validate_template_arguments
from semacli.core.models import Template
from semacli.core.overrides import ALL_OVERRIDES, OVERRIDE_TOGGLES, parse_allow_override
from semacli.core.resolve import (
    resolve_environment,
    resolve_inventory,
    resolve_repository,
    resolve_template,
    resolve_view,
)

from .._crud import opts_from_ctx, setup
from ..handlers import fail_on_error

_OVERRIDE_HELP = (
    "Overrides the template lets a run pass: comma list of "
    f"{'/'.join(OVERRIDE_TOGGLES)}, or 'all' / 'none'. "
    "Semaphore drops a forbidden override silently, so anything left out "
    "here makes `sem run --<flag>` refuse to run."
)
_ARGUMENTS_HELP = "Static ansible-playbook flags as a JSON array, e.g. '[\"--diff\"]'."


def _parse_survey_vars(
    _ctx: click.Context, _param: click.Parameter, value: str | None
) -> list[dict[str, Any]] | None:
    """Click callback: parse --survey-vars as a JSON array of objects."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as err:
        msg = f"not valid JSON ({err.msg})"
        raise click.BadParameter(msg) from err
    if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
        msg = "expected a JSON array of objects"
        raise click.BadParameter(msg)
    return parsed


_RESOLVERS = {
    "repository": resolve_repository,
    "inventory": resolve_inventory,
    "environment": resolve_environment,
    "view": resolve_view,
}


def _resolve_refs(client: SemaphoreClient, pid: int, **refs: str | None) -> dict[str, int | None]:
    """Resolve the name-or-id references of a template to ``<kind>_id`` keys."""
    return {
        f"{kind}_id": _RESOLVERS[kind](client, pid, value) if value else None
        for kind, value in refs.items()
    }


def _emit_created(opts: dict[str, Any], tpl: Template) -> None:
    """Report a freshly created template as JSON or one line of text."""
    if opts["output_json"]:
        click.echo(json.dumps(tpl.model_dump(), indent=2))
    elif not opts["quiet"]:
        click.echo(f"created template id={tpl.id}")


def _write_options(func: Any) -> Any:  # noqa: ANN401  # click decorator stack
    """Attach the options shared by `template create` and `template update`."""
    for option in (
        click.option("--environment", default=None, help="Environment name or id."),
        click.option("--view", default=None, help="Board view (column) name or id."),
        click.option("--description", default=None),
        click.option("--arguments", default=None, help=_ARGUMENTS_HELP),
        click.option("--allow-override", default=None, help=_OVERRIDE_HELP),
        click.option(
            "--allow-override-args/--no-allow-override-args",
            "allow_override_args",
            default=None,
            help="Let a run pass its own ansible arguments.",
        ),
        click.option(
            "--survey-vars",
            default=None,
            callback=_parse_survey_vars,
            help="Survey variables as a JSON array of objects.",
        ),
    ):
        func = option(func)
    return func


@click.command("create")
@click.option("--name", required=True)
@click.option("--playbook", required=True, help="Path of the playbook inside the repo.")
@click.option("--repository", required=True, help="Repository name or id.")
@click.option("--inventory", required=True, help="Inventory name or id.")
@click.option(
    "--app", default="ansible", show_default=True, help="Runner app (ansible, bash, ...)."
)
@_write_options
@click.pass_context
@fail_on_error
def create_cmd(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    *,
    name: str,
    playbook: str,
    repository: str,
    inventory: str,
    app: str,
    environment: str | None,
    view: str | None,
    description: str | None,
    arguments: str | None,
    allow_override: str | None,
    allow_override_args: bool | None,
    survey_vars: list[dict[str, Any]] | None,
) -> None:
    """Create a template.

    Every override is allowed unless --allow-override narrows it: a
    template that forbids --limit makes `sem run --limit` fail closed.
    """
    opts = opts_from_ctx(ctx)
    validate_template_arguments(arguments)
    client, pid = setup(opts)
    refs = _resolve_refs(
        client, pid, repository=repository, inventory=inventory, environment=environment, view=view
    )
    tpl = client.create_template(
        pid,
        name=name,
        playbook=playbook,
        inventory_id=refs["inventory_id"] or 0,
        repository_id=refs["repository_id"] or 0,
        environment_id=refs["environment_id"],
        description=description or "",
        arguments=arguments or "",
        app=app,
        view_id=refs["view_id"],
        task_params=parse_allow_override(allow_override or ALL_OVERRIDES),
        allow_override_args=allow_override_args is not False,
        survey_vars=survey_vars,
    )
    _emit_created(opts, tpl)


@click.command("update")
@click.argument("template")
@click.option("--name", default=None)
@click.option("--playbook", default=None)
@click.option("--repository", default=None, help="Repository name or id.")
@click.option("--inventory", default=None, help="Inventory name or id.")
@click.option("--app", default=None, help="Runner app (ansible, bash, ...).")
@_write_options
@click.pass_context
@fail_on_error
def update_cmd(  # noqa: PLR0913  # one parameter per --option (click callback)
    ctx: click.Context,
    template: str,
    *,
    name: str | None,
    playbook: str | None,
    repository: str | None,
    inventory: str | None,
    app: str | None,
    environment: str | None,
    view: str | None,
    description: str | None,
    arguments: str | None,
    allow_override: str | None,
    allow_override_args: bool | None,
    survey_vars: list[dict[str, Any]] | None,
) -> None:
    """Update mutable fields of a template (read-modify-write).

    The current payload is fetched and only the fields passed here are
    patched onto it, so an update never drops `app`, `task_params`,
    `view_id` or `survey_vars` (ken #1118).
    """
    opts = opts_from_ctx(ctx)
    validate_template_arguments(arguments)
    client, pid = setup(opts)
    template_id = resolve_template(client, pid, template)
    refs = _resolve_refs(
        client, pid, repository=repository, inventory=inventory, environment=environment, view=view
    )
    patch: dict[str, Any] = {
        "name": name,
        "playbook": playbook,
        "app": app,
        "description": description,
        "arguments": arguments,
        "allow_override_args_in_task": allow_override_args,
        "task_params": parse_allow_override(allow_override),
        "survey_vars": survey_vars,
    } | refs
    client.update_template(pid, template_id, **patch)
    if not opts["quiet"]:
        changed = ", ".join(sorted(k for k, v in patch.items() if v is not None)) or "nothing"
        click.echo(f"updated template id={template_id} ({changed})")
