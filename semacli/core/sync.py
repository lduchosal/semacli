"""Planner for `sem template sync` — pure, offline, no HTTP.

Takes what the manifest declares plus what the server already has, and
returns the list of actions: create / update / skip, with a field-level
diff for the updates. Nothing here deletes: a template carries its task
history, so a name that disappears from the manifest is reported and
left alone.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .exceptions import NotFoundError
from .guards import validate_template_arguments
from .manifest import TemplateSpec
from .overrides import OVERRIDE_TOGGLES, parse_allow_override, permissive_task_params

CREATE = "create"
UPDATE = "update"
SKIP = "skip"

# Fields `sync` owns. Anything else the server stores is left untouched.
MANAGED_FIELDS = (
    "name",
    "playbook",
    "app",
    "repository_id",
    "inventory_id",
    "environment_id",
    "view_id",
    "description",
    "arguments",
    "allow_override_args_in_task",
)


@dataclass(frozen=True)
class NameIndex:
    """Name → id lookups for the objects a template points at."""

    repositories: dict[str, int] = field(default_factory=dict)
    inventories: dict[str, int] = field(default_factory=dict)
    environments: dict[str, int] = field(default_factory=dict)
    views: dict[str, int] = field(default_factory=dict)

    def _table(self, kind: str) -> dict[str, int]:
        """The name→id table for one kind of referenced object."""
        return {
            "repositories": self.repositories,
            "inventories": self.inventories,
            "environments": self.environments,
            "views": self.views,
        }[kind]

    def lookup(self, kind: str, value: str | int | None) -> int | None:
        """Resolve one manifest reference; digits pass through as an id.

        Strict: an unknown repository / inventory / environment name
        changes what would actually run, so it stops the sync.
        """
        found = self.lookup_optional(kind, value)
        if found is None and value is not None:
            known = ", ".join(sorted(self._table(kind))) or "none"
            msg = f"no {kind[:-1]} named '{value}' (known: {known})"
            raise NotFoundError(msg)
        return found

    def lookup_optional(self, kind: str, value: str | int | None) -> int | None:
        """Same lookup, but an unknown name is None instead of an error.

        Used for views: the board column is cosmetic, so a view that does
        not exist yet leaves the template unclassified (and is reported)
        rather than blocking every other template.
        """
        if value is None:
            return None
        if isinstance(value, int) or str(value).isdigit():
            return int(value)
        return self._table(kind).get(str(value).casefold())


@dataclass(frozen=True)
class Change:
    """One field the server would have to change."""

    field: str
    old: Any
    new: Any

    def __str__(self) -> str:
        """Render as ``field: old -> new`` for the cli diff."""
        return f"{self.field}: {self.old!r} -> {self.new!r}"


@dataclass(frozen=True)
class SyncAction:
    """What sync would do about one declared template."""

    verb: str
    spec: TemplateSpec
    body: dict[str, Any]
    template_id: int | None = None
    changes: tuple[Change, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class SyncPlan:
    """The full plan: one action per spec, plus the untouched leftovers."""

    actions: tuple[SyncAction, ...]
    orphans: tuple[str, ...]
    unknown_views: tuple[str, ...] = ()

    def count(self, verb: str) -> int:
        """Number of actions carrying this verb."""
        return sum(1 for a in self.actions if a.verb == verb)


def desired_body(spec: TemplateSpec, index: NameIndex, project_id: int) -> dict[str, Any]:
    """Build the API payload a spec asks for, with names already resolved."""
    validate_template_arguments(spec.arguments)
    task_params = parse_allow_override(spec.allow_override) or permissive_task_params()
    body: dict[str, Any] = {
        "project_id": project_id,
        "name": spec.name,
        "playbook": spec.playbook,
        "app": spec.app,
        "repository_id": index.lookup("repositories", spec.repository),
        "inventory_id": index.lookup("inventories", spec.inventory),
        "view_id": index.lookup_optional("views", spec.view) or 0,
        "description": spec.description,
        "arguments": spec.arguments or "[]",
        "allow_override_args_in_task": spec.allow_override_args,
        "task_params": task_params,
    }
    environment_id = index.lookup("environments", spec.environment)
    if environment_id is not None:
        body["environment_id"] = environment_id
    return body


def _normalise(value: Any) -> Any:  # noqa: ANN401  # compares raw JSON values
    """Treat the server's null and semacli's zero/empty as the same thing."""
    return 0 if value is None else value


def diff_body(existing: Mapping[str, Any], desired: Mapping[str, Any]) -> tuple[Change, ...]:
    """List the managed fields where the server differs from the manifest."""
    changes = [
        Change(name, _normalise(existing.get(name)), desired[name])
        for name in MANAGED_FIELDS
        if name in desired and _normalise(existing.get(name)) != desired[name]
    ]
    current = existing.get("task_params") or {}
    changes += [
        Change(f"task_params.{toggle}", bool(current.get(toggle)), desired["task_params"][toggle])
        for toggle in OVERRIDE_TOGGLES.values()
        if bool(current.get(toggle)) != desired["task_params"][toggle]
    ]
    return tuple(changes)


def plan_sync(
    specs: Sequence[TemplateSpec],
    existing: Sequence[Mapping[str, Any]],
    index: NameIndex,
    project_id: int,
    *,
    update: bool,
) -> SyncPlan:
    """Decide create / update / skip for every spec, and report orphans.

    Without ``update`` an existing name is skipped untouched — the safe
    default, since a template's identity on the board is its name. With
    ``update`` only the specs that actually differ are PUT back.
    """
    by_name = {str(t.get("name")): t for t in existing}
    actions = []
    for spec in specs:
        body = desired_body(spec, index, project_id)
        current = by_name.get(spec.name)
        if current is None:
            actions.append(SyncAction(CREATE, spec, body))
            continue
        template_id = int(current.get("id", 0))
        changes = diff_body(current, body)
        if not update:
            actions.append(SyncAction(SKIP, spec, body, template_id, changes, "exists"))
        elif changes:
            actions.append(SyncAction(UPDATE, spec, body, template_id, changes))
        else:
            actions.append(SyncAction(SKIP, spec, body, template_id, (), "unchanged"))
    declared = {spec.name for spec in specs}
    orphans = tuple(sorted(name for name in by_name if name not in declared))
    unknown_views = tuple(
        sorted(
            {
                str(spec.view)
                for spec in specs
                if spec.view and index.lookup_optional("views", spec.view) is None
            }
        )
    )
    return SyncPlan(tuple(actions), orphans, unknown_views)
