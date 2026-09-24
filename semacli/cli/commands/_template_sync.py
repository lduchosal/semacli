"""`sem template sync` — reconcile a manifest with the project's templates.

Idempotent and additive: one template per declared playbook, existing
names skipped unless --update, and never a delete (a template carries
its whole task history). The site-specific mapping — which view, which
repo, which playbooks to ignore — lives in the manifest, not here.
"""

import json
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.exceptions import SemaCliError
from semacli.core.manifest import build_specs, load_manifest
from semacli.core.sync import CREATE, SKIP, UPDATE, NameIndex, SyncAction, SyncPlan, plan_sync

from .._crud import opts_from_ctx, setup
from .._groups import RawEpilogCommand
from ..handlers import fail_on_error

SYNC_HELP = """\
Reconcile a declarative manifest with the project's templates.

The manifest lists the playbooks that must exist as templates and the
defaults they share (repository, inventory, environment, board view,
allowed overrides). Names are resolved against the server, so the file
stays readable and portable.

Existing templates are left untouched unless --update is passed, and
nothing is ever deleted: a template owns its task history. Start with
--dry-run — it prints exactly what would change, field by field.
"""

SYNC_EPILOG = """\
Examples:
  sem template sync --manifest templates.yml --dry-run
  sem template sync --manifest templates.yml
  sem template sync --manifest templates.yml --update
  sem template sync --manifest templates.yml --playbooks ../ansible

Manifest:
  defaults:
    repository: 2113-ansible
    inventory: hosts
    environment: default
    description: "Run ansible playbook {playbook}"
  playbooks: ansible
  ignore: [requirements.yml, site.yml]
  views:
    mtree: BSD
  templates:
    - name: book_base
      playbook: book_base.yml
      view: BOOK
"""

_VERB_LABEL = {CREATE: "CREATE", UPDATE: "UPDATE", SKIP: "SKIP  "}


def _build_index(client: SemaphoreClient, pid: int) -> NameIndex:
    """Fetch the name→id tables a manifest reference can point at."""
    return NameIndex(
        repositories={r.name.casefold(): r.id for r in client.list_repositories(pid)},
        inventories={i.name.casefold(): i.id for i in client.list_inventories(pid)},
        environments={e.name.casefold(): e.id for e in client.list_environments(pid)},
        views={v.title.casefold(): v.id for v in client.list_views(pid)},
    )


def _describe(action: SyncAction) -> str:
    """One report line for an action: verb, name, view, and what differs."""
    view = f" [{action.spec.view}]" if action.spec.view else ""
    line = f"  {_VERB_LABEL[action.verb]}  {action.spec.name}{view}"
    if action.verb == UPDATE:
        return f"{line}  {'; '.join(str(c) for c in action.changes)}"
    if action.verb == SKIP and action.changes:
        return f"{line} ({action.reason}; {len(action.changes)} field(s) differ — pass --update)"
    if action.verb == SKIP:
        return f"{line} ({action.reason})"
    return line


def _create(client: SemaphoreClient, pid: int, body: dict[str, Any]) -> None:
    """POST one planned template through the regular create path."""
    client.create_template(
        pid,
        name=body["name"],
        playbook=body["playbook"],
        inventory_id=body["inventory_id"] or 0,
        repository_id=body["repository_id"] or 0,
        environment_id=body.get("environment_id"),
        description=body["description"],
        arguments=body["arguments"],
        app=body["app"],
        view_id=body["view_id"],
        task_params=body["task_params"],
        allow_override_args=body["allow_override_args_in_task"],
    )


def _apply(client: SemaphoreClient, pid: int, action: SyncAction, *, quiet: bool) -> bool:
    """Execute one action; report and swallow a per-template failure."""
    try:
        if action.verb == CREATE:
            _create(client, pid, action.body)
        elif action.verb == UPDATE:
            patch = {k: v for k, v in action.body.items() if k != "project_id"}
            client.update_template(pid, action.template_id or 0, **patch)
    except SemaCliError as err:
        click.echo(f"  FAILED  {action.spec.name}: {err}", err=True)
        return False
    if not quiet:
        click.echo(_describe(action))
    return True


def _execute(client: SemaphoreClient, pid: int, plan: SyncPlan, *, quiet: bool) -> int:
    """Run every non-skip action, keep going on failure, return the failure count.

    A skipped template is still reported, so a real run prints the same
    lines as the --dry-run that was reviewed beforehand.
    """
    failed = 0
    for action in plan.actions:
        if action.verb == SKIP:
            if not quiet:
                click.echo(_describe(action))
        elif not _apply(client, pid, action, quiet=quiet):
            failed += 1
    return failed


def _emit_summary(plan: SyncPlan, failed: int, *, dry_run: bool) -> None:
    """Print the counts, the orphans, and the dry-run reminder."""
    created, updated = ("to create", "to update") if dry_run else ("created", "updated")
    click.echo(
        f"\nSummary: {plan.count(CREATE)} {created}, {plan.count(UPDATE)} {updated}, "
        f"{plan.count(SKIP)} skipped" + (f", {failed} failed" if failed else "")
    )
    if plan.orphans:
        click.echo(
            f"{len(plan.orphans)} template(s) on the server are not in the manifest "
            "(left untouched)."
        )
    if plan.unknown_views:
        click.echo(
            f"views absent from the server: {', '.join(plan.unknown_views)} "
            "— those templates stay unclassified (visible under 'All')."
        )


def _plan_json(plan: SyncPlan) -> str:
    """Serialise the plan for --json consumers."""
    return json.dumps(
        {
            "actions": [
                {
                    "verb": a.verb,
                    "name": a.spec.name,
                    "playbook": a.spec.playbook,
                    "view": a.spec.view,
                    "template_id": a.template_id,
                    "reason": a.reason,
                    "changes": [{"field": c.field, "old": c.old, "new": c.new} for c in a.changes],
                }
                for a in plan.actions
            ],
            "orphans": list(plan.orphans),
        },
        indent=2,
    )


@click.command("sync", cls=RawEpilogCommand, help=SYNC_HELP, epilog=SYNC_EPILOG)
@click.option("--manifest", required=True, help="YAML manifest describing the templates.")
@click.option("--playbooks", default=None, help="Playbook directory (overrides the manifest key).")
@click.option("--dry-run", is_flag=True, help="Print the plan without touching the server.")
@click.option("--update", is_flag=True, help="Patch existing templates that differ.")
@click.pass_context
@fail_on_error
def sync_cmd(
    ctx: click.Context,
    *,
    manifest: str,
    playbooks: str | None,
    dry_run: bool,
    update: bool,
) -> None:
    """Create the templates a manifest declares; never delete any."""
    opts = opts_from_ctx(ctx)
    specs = build_specs(load_manifest(manifest), playbooks)
    client, pid = setup(opts)
    plan = plan_sync(
        specs, client.get_templates_raw(pid), _build_index(client, pid), pid, update=update
    )

    if opts["output_json"]:
        click.echo(_plan_json(plan))
    if dry_run:
        if not opts["quiet"] and not opts["output_json"]:
            for action in plan.actions:
                click.echo(_describe(action))
            _emit_summary(plan, 0, dry_run=True)
        return

    quiet = opts["quiet"] or opts["output_json"]
    failed = _execute(client, pid, plan, quiet=quiet)
    if not quiet:
        _emit_summary(plan, failed, dry_run=False)
    if failed:
        raise SystemExit(1)
