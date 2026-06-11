"""``sem self-update`` — upgrade semacli from PyPI."""

from __future__ import annotations

import subprocess
import sys

import click
import requests

from semacli import __version__

from .._groups import RawEpilogCommand, SectionedRootGroup

PYPI_JSON_URL = "https://pypi.org/pypi/semacli/json"

SELF_UPDATE_HELP = """\
Upgrade semacli to the latest version from PyPI.

Compares the installed version to the latest release on PyPI; if they
differ, runs ``pip install --upgrade semacli`` against the **current**
Python interpreter (so the right venv is targeted, not whatever ``pip``
happens to be on PATH).

Exit codes:
  0  already up to date, OR upgrade completed successfully.
  1  upgrade available but pip failed (network, permissions, conflict).
     With ``--check``: 1 also means an upgrade is available.
  2  could not reach PyPI.
"""

SELF_UPDATE_EPILOG = """\
Examples:
  sem self-update                # upgrade in place if not latest
  sem self-update --check        # compare only; exit 1 if upgrade is available
  sem self-update --pre          # allow pre-releases (--pre to pip)
  sem self-update --dry-run      # print the pip command, do not run it
"""


def _fetch_latest_version(*, allow_pre: bool, timeout: float = 10.0) -> str:
    """Return the latest version string from PyPI.

    With ``allow_pre`` true the highest pre-release is also considered;
    otherwise only stable releases. Raises ``RuntimeError`` on network or
    parse failure.
    """
    try:
        resp = requests.get(PYPI_JSON_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        msg = f"could not reach PyPI: {e}"
        raise RuntimeError(msg) from e

    if allow_pre:
        try:
            return str(data["info"]["version"])
        except (KeyError, TypeError) as e:
            msg = f"unexpected PyPI JSON shape: {e}"
            raise RuntimeError(msg) from e

    releases = data.get("releases", {})
    stables = [v for v in releases if _is_stable(v) and releases[v]]
    if stables:
        return str(max(stables, key=_version_key))
    try:
        return str(data["info"]["version"])
    except (KeyError, TypeError) as e:
        msg = f"unexpected PyPI JSON shape: {e}"
        raise RuntimeError(msg) from e


def _is_stable(version: str) -> bool:
    """A version is "stable" if it has no PEP 440 pre-release suffix."""
    lower = version.lower()
    return not any(tag in lower for tag in ("a", "b", "rc", "dev", "pre"))


def _version_key(version: str) -> tuple[int, ...]:
    """Best-effort tuple key for sorting MAJOR.MINOR.PATCH strings."""
    parts: list[int] = []
    for chunk in version.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _pip_command(*, allow_pre: bool) -> list[str]:
    """Build the pip upgrade command line, adding --pre when requested."""
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "semacli"]
    if allow_pre:
        cmd.append("--pre")
    return cmd


@click.command(
    "self-update",
    cls=RawEpilogCommand,
    help=SELF_UPDATE_HELP,
    epilog=SELF_UPDATE_EPILOG,
)
@click.option(
    "--check",
    "check_only",
    is_flag=True,
    help="Compare versions only; exit 1 if an upgrade is available.",
)
@click.option(
    "--pre",
    "allow_pre",
    is_flag=True,
    help="Allow pre-releases when picking the latest version.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the pip command instead of running it.",
)
def self_update_cmd(*, check_only: bool, allow_pre: bool, dry_run: bool) -> None:
    """Upgrade semacli from PyPI (or just compare versions with --check)."""
    current = __version__
    click.echo(f"Current version: {current}")

    click.echo("Fetching latest from PyPI ...")
    try:
        latest = _fetch_latest_version(allow_pre=allow_pre)
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        raise SystemExit(2) from e

    click.echo(f"Latest on PyPI:  {latest}")

    if latest == current:
        click.echo("Already up to date.")
        return

    if check_only:
        click.echo(f"Upgrade available: {current} -> {latest}")
        raise SystemExit(1)

    cmd = _pip_command(allow_pre=allow_pre)
    click.echo(f"Upgrading to {latest} ...")
    click.echo(f"  {' '.join(cmd)}")
    if dry_run:
        click.echo("(--dry-run: pip not executed)")
        return

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        click.echo(f"error: pip exited with code {result.returncode}", err=True)
        raise SystemExit(1)

    click.echo("Done. Run `sem --version` to confirm.")


def register_self_update_commands(main_group: SectionedRootGroup) -> None:
    """Register the `self-update` command."""
    main_group.add_command(self_update_cmd)
    main_group.set_category("self-update", "connection")
