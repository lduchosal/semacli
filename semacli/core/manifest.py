"""Declarative template manifest for `sem template sync`.

The manifest is the site's own mapping — which playbooks become
templates, in which board view, with which repo / inventory /
environment. semacli never guesses it from the playbook tree: it reads
what the operator declared, so the site-specific rules live in a file
under the user's control rather than in this codebase.

Shape (every key optional except ``playbook``/``name``)::

    defaults:
      repository: 2113-ansible      # name or id
      inventory: hosts
      environment: default
      app: ansible
      arguments: '["--diff"]'
      allow_override: [limit, tags, skip-tags, inventory, debug]
      allow_override_args: true
      description: "Run ansible playbook {playbook}"
    playbooks: ansible              # scan <dir>/*.yml, relative to the manifest
    ignore: [requirements.yml, site.yml]
    views:                          # template name -> view title
      mtree: BSD
    templates:                      # explicit entries, merged over the scan
      - name: book_base
        playbook: book_base.yml
        view: BOOK
"""

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from .exceptions import ManifestError

_TOP_KEYS = frozenset({"defaults", "playbooks", "ignore", "views", "templates"})
_SPEC_KEYS = frozenset(
    {
        "name",
        "playbook",
        "view",
        "repository",
        "inventory",
        "environment",
        "app",
        "description",
        "arguments",
        "allow_override",
        "allow_override_args",
    }
)
_PLAYBOOK_GLOBS = ("*.yml", "*.yaml")


@dataclass(frozen=True)
class TemplateSpec:
    """One template the manifest declares, before name→id resolution."""

    name: str
    playbook: str
    view: str | None = None
    repository: str | None = None
    inventory: str | None = None
    environment: str | None = None
    app: str = "ansible"
    description: str = ""
    arguments: str = ""
    allow_override: str | list[str] | None = None
    allow_override_args: bool = True


@dataclass(frozen=True)
class Manifest:
    """A parsed manifest: defaults + scan rules + explicit entries."""

    path: Path
    defaults: dict[str, Any] = field(default_factory=dict)
    playbooks: str | None = None
    ignore: frozenset[str] = frozenset()
    views: dict[str, str] = field(default_factory=dict)
    entries: tuple[dict[str, Any], ...] = ()


def _as_mapping(value: Any, path: Path, what: str) -> dict[str, Any]:  # noqa: ANN401  # raw YAML
    """Return ``value`` as a dict or raise a ManifestError naming ``what``."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        reason = f"{what} must be a mapping, got {type(value).__name__}"
        raise ManifestError(str(path), reason)
    return value


def _check_keys(keys: Any, allowed: frozenset[str], path: Path, what: str) -> None:  # noqa: ANN401
    """Reject unknown keys — a typo in a manifest must never pass silently."""
    unknown = sorted(set(keys) - allowed)
    if unknown:
        reason = f"unknown key(s) in {what}: {', '.join(unknown)}"
        raise ManifestError(str(path), reason)


def _load_entries(raw: Any, path: Path) -> tuple[dict[str, Any], ...]:  # noqa: ANN401  # raw YAML
    """Validate the ``templates:`` list and return it as tuples of dicts."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        reason = f"templates must be a list, got {type(raw).__name__}"
        raise ManifestError(str(path), reason)
    entries = []
    for item in raw:
        entry = _as_mapping(item, path, "each templates entry")
        _check_keys(entry, _SPEC_KEYS, path, "templates entry")
        if not entry.get("playbook") and not entry.get("name"):
            reason = "each templates entry needs at least a playbook or a name"
            raise ManifestError(str(path), reason)
        entries.append(entry)
    return tuple(entries)


def load_manifest(path: str | Path) -> Manifest:
    """Read and validate a YAML manifest."""
    manifest_path = Path(path)
    try:
        raw = yaml.safe_load(manifest_path.read_text())
    except OSError as err:
        reason = f"cannot read ({err.strerror})"
        raise ManifestError(str(manifest_path), reason) from err
    except yaml.YAMLError as err:
        reason = f"invalid YAML ({err})"
        raise ManifestError(str(manifest_path), reason) from err

    doc = _as_mapping(raw, manifest_path, "manifest root")
    _check_keys(doc, _TOP_KEYS, manifest_path, "manifest root")
    defaults = _as_mapping(doc.get("defaults"), manifest_path, "defaults")
    _check_keys(defaults, _SPEC_KEYS, manifest_path, "defaults")
    views = _as_mapping(doc.get("views"), manifest_path, "views")
    return Manifest(
        path=manifest_path,
        defaults=defaults,
        playbooks=doc.get("playbooks"),
        ignore=frozenset(doc.get("ignore") or ()),
        views={k: str(v) for k, v in views.items()},
        entries=_load_entries(doc.get("templates"), manifest_path),
    )


def _spec_from(entry: dict[str, Any], defaults: dict[str, Any]) -> TemplateSpec:
    """Build one spec from an entry layered over the manifest defaults."""
    merged = {**defaults, **{k: v for k, v in entry.items() if v is not None}}
    playbook = str(merged.get("playbook") or f"{merged['name']}.yml")
    name = str(merged.get("name") or Path(playbook).stem)
    description = str(merged.get("description", "")).format(name=name, playbook=playbook)
    return TemplateSpec(
        name=name,
        playbook=playbook,
        view=merged.get("view"),
        repository=merged.get("repository"),
        inventory=merged.get("inventory"),
        environment=merged.get("environment"),
        app=str(merged.get("app", "ansible")),
        description=description,
        arguments=str(merged.get("arguments", "")),
        allow_override=merged.get("allow_override"),
        allow_override_args=bool(merged.get("allow_override_args", True)),
    )


def _scanned_playbooks(directory: Path, ignore: frozenset[str]) -> list[Path]:
    """List the playbook files of a directory, minus the ignored names."""
    if not directory.is_dir():
        reason = f"playbooks directory not found: {directory}"
        raise ManifestError(str(directory), reason)
    found = {p for glob in _PLAYBOOK_GLOBS for p in directory.glob(glob)}
    return sorted(p for p in found if p.name not in ignore)


def build_specs(manifest: Manifest, playbooks_dir: str | Path | None = None) -> list[TemplateSpec]:
    """Expand a manifest into the template specs it declares.

    One template per playbook found in the scanned directory (if any),
    with ``views:`` deciding the board column, then the explicit
    ``templates:`` entries merged on top — same name replaces, new name
    adds. Sorted by name, so two runs always print the same order.
    """
    specs: dict[str, TemplateSpec] = {}
    scan = playbooks_dir if playbooks_dir is not None else manifest.playbooks
    if scan is not None:
        directory = Path(scan)
        if not directory.is_absolute() and playbooks_dir is None:
            directory = manifest.path.parent / directory
        for playbook in _scanned_playbooks(directory, manifest.ignore):
            spec = _spec_from({"playbook": playbook.name}, manifest.defaults)
            specs[spec.name] = replace(spec, view=manifest.views.get(spec.name, spec.view))
    for entry in manifest.entries:
        spec = _spec_from(entry, manifest.defaults)
        if spec.view is None:
            spec = replace(spec, view=manifest.views.get(spec.name))
        specs[spec.name] = spec
    return [specs[name] for name in sorted(specs)]
