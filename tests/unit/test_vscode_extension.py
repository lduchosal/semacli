"""Release invariants of the VS Code extension (ken #1131).

publish.sh syncs vscode/package.json to the bumped semacli version so the
.vsix attached to the GitHub release carries the release it was built
with. These tests keep the manifest and its packaging honest between
releases, without needing node.
"""

import json
from pathlib import Path

import pytest

from semacli import __version__

VSCODE = Path(__file__).resolve().parents[2] / "vscode"

# The sdist ships tests/ but not vscode/: nothing to check there.
pytestmark = pytest.mark.skipif(not VSCODE.is_dir(), reason="vscode/ not in this tree")


def _manifest() -> dict:
    return json.loads((VSCODE / "package.json").read_text(encoding="utf-8"))


class TestVscodeManifest:
    def test_version_matches_semacli(self) -> None:
        assert _manifest()["version"] == __version__

    def test_single_version_key_for_the_publish_sed(self) -> None:
        # publish.sh rewrites every `"version": "..."` line: only one may exist.
        text = (VSCODE / "package.json").read_text(encoding="utf-8")
        assert text.count('"version":') == 1

    def test_every_contributed_command_is_registered(self) -> None:
        manifest = _manifest()
        declared = {c["command"] for c in manifest["contributes"]["commands"]}
        source = (VSCODE / "src" / "extension.js").read_text(encoding="utf-8")
        assert declared
        for command in declared:
            assert f"'{command}'" in source, command

    def test_no_runtime_dependencies(self) -> None:
        # vsce runs with --no-dependencies: a runtime dep would be missing at install.
        assert "dependencies" not in _manifest()

    def test_vsix_ships_sources_only(self) -> None:
        ignored = (VSCODE / ".vscodeignore").read_text(encoding="utf-8").splitlines()
        for pattern in ("node_modules/**", "test/**", "lcov.info"):
            assert pattern in ignored
