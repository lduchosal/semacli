"""Tests for the `template sync` manifest parser."""

from pathlib import Path

import pytest

from semacli.core.exceptions import ManifestError
from semacli.core.manifest import build_specs, load_manifest

_FULL = """
defaults:
  repository: 2113-ansible
  inventory: hosts
  environment: default
  description: "Run ansible playbook {playbook}"
playbooks: ansible
ignore: [requirements.yml]
views:
  mtree: BSD
templates:
  - name: book_base
    playbook: book_base.yml
    view: BOOK
    allow_override: limit
"""


def _manifest(tmp_path: Path, body: str, playbooks: tuple[str, ...] = ()) -> Path:
    path = tmp_path / "templates.yml"
    path.write_text(body, encoding="utf-8")
    if playbooks:
        (tmp_path / "ansible").mkdir(exist_ok=True)
        for name in playbooks:
            (tmp_path / "ansible" / name).write_text("---\n")
    return path


class TestLoadManifest:
    def test_parses_every_section(self, tmp_path: Path) -> None:
        manifest = load_manifest(_manifest(tmp_path, _FULL))
        assert manifest.defaults["repository"] == "2113-ansible"
        assert manifest.playbooks == "ansible"
        assert manifest.ignore == frozenset({"requirements.yml"})
        assert manifest.views == {"mtree": "BSD"}
        assert manifest.entries[0]["name"] == "book_base"

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="cannot read"):
            load_manifest(tmp_path / "nope.yml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="invalid YAML"):
            load_manifest(_manifest(tmp_path, "defaults: [unclosed\n"))

    @pytest.mark.usefixtures("cp1252_locale")
    def test_reads_utf8_whatever_the_locale(self, tmp_path: Path) -> None:
        # ken #1122: a cp1252 locale used to turn "Prépare" into "PrÃ©pare".
        body = 'templates:\n  - name: book_base\n    description: "Prépare {name}"\n'
        specs = build_specs(load_manifest(_manifest(tmp_path, body)))
        assert specs[0].description == "Prépare book_base"

    def test_non_utf8_file_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "templates.yml"
        path.write_bytes("templates:\n  - name: Prépare\n".encode("cp1252"))
        with pytest.raises(ManifestError, match="not valid UTF-8"):
            load_manifest(path)

    def test_root_must_be_a_mapping(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="must be a mapping"):
            load_manifest(_manifest(tmp_path, "- one\n- two\n"))

    def test_unknown_top_level_key_is_refused(self, tmp_path: Path) -> None:
        # A typo in a manifest must never pass silently.
        with pytest.raises(ManifestError, match="unknown key"):
            load_manifest(_manifest(tmp_path, "playbook: ansible\n"))

    def test_unknown_defaults_key_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="unknown key"):
            load_manifest(_manifest(tmp_path, "defaults:\n  repo: x\n"))

    def test_templates_must_be_a_list(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="must be a list"):
            load_manifest(_manifest(tmp_path, "templates:\n  name: x\n"))

    def test_entry_needs_a_name_or_playbook(self, tmp_path: Path) -> None:
        with pytest.raises(ManifestError, match="at least a playbook or a name"):
            load_manifest(_manifest(tmp_path, "templates:\n  - view: BSD\n"))

    def test_empty_manifest_is_valid(self, tmp_path: Path) -> None:
        manifest = load_manifest(_manifest(tmp_path, "\n"))
        assert build_specs(manifest) == []


class TestBuildSpecs:
    def test_scan_plus_entries_sorted_by_name(self, tmp_path: Path) -> None:
        path = _manifest(tmp_path, _FULL, ("mtree.yml", "ntp.yml", "requirements.yml"))
        specs = build_specs(load_manifest(path))
        assert [s.name for s in specs] == ["book_base", "mtree", "ntp"]

    def test_defaults_are_inherited_and_description_is_formatted(self, tmp_path: Path) -> None:
        path = _manifest(tmp_path, _FULL, ("mtree.yml",))
        mtree = next(s for s in build_specs(load_manifest(path)) if s.name == "mtree")
        assert mtree.repository == "2113-ansible"
        assert mtree.inventory == "hosts"
        assert mtree.description == "Run ansible playbook mtree.yml"

    def test_views_mapping_applies_to_scanned_playbooks(self, tmp_path: Path) -> None:
        path = _manifest(tmp_path, _FULL, ("mtree.yml", "ntp.yml"))
        specs = {s.name: s for s in build_specs(load_manifest(path))}
        assert specs["mtree"].view == "BSD"
        assert specs["ntp"].view is None
        assert specs["book_base"].view == "BOOK"

    def test_entry_overrides_the_scanned_playbook(self, tmp_path: Path) -> None:
        body = _FULL + "  - name: mtree\n    playbook: custom/mtree.yml\n    view: OVERRIDE\n"
        path = _manifest(tmp_path, body, ("mtree.yml",))
        mtree = next(s for s in build_specs(load_manifest(path)) if s.name == "mtree")
        assert mtree.playbook == "custom/mtree.yml"
        assert mtree.view == "OVERRIDE"

    def test_ignored_playbook_is_skipped(self, tmp_path: Path) -> None:
        path = _manifest(tmp_path, _FULL, ("requirements.yml",))
        assert [s.name for s in build_specs(load_manifest(path))] == ["book_base"]

    def test_playbooks_dir_argument_overrides_the_manifest_key(self, tmp_path: Path) -> None:
        path = _manifest(tmp_path, _FULL, ("mtree.yml",))
        other = tmp_path / "elsewhere"
        other.mkdir()
        (other / "solo.yml").write_text("---\n")
        specs = build_specs(load_manifest(path), other)
        assert [s.name for s in specs] == ["book_base", "solo"]

    def test_missing_playbooks_dir_raises(self, tmp_path: Path) -> None:
        path = _manifest(tmp_path, _FULL)
        with pytest.raises(ManifestError, match="playbooks directory not found"):
            build_specs(load_manifest(path))

    def test_name_without_playbook_defaults_to_name_yml(self, tmp_path: Path) -> None:
        path = _manifest(tmp_path, "templates:\n  - name: mtree\n")
        assert build_specs(load_manifest(path))[0].playbook == "mtree.yml"
