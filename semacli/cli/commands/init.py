"""Interactive `sem init` — bootstrap a working semacli.ini.

Walks the user through URL, TLS verification, bearer token, project
selection, then writes a chmod-600 ini file at the chosen location.
See UX.md and ken #716 for the full flow.
"""

from pathlib import Path
from typing import Any

import click

from semacli.core.client import SemaphoreClient
from semacli.core.config import SemaphoreConfig
from semacli.core.exceptions import AuthenticationError, SemaCliError

from .._groups import RawEpilogCommand

INIT_HELP = """\
Create semacli.ini in guided mode.

Walks you through the Semaphore URL, TLS verification, bearer token,
default project, and target file location. Each step is validated
against the server before moving on. The resulting file is created with
mode 0600 so the token is not world-readable.
"""

INIT_EPILOG = """\
Examples:
  sem init                          # prompts for everything
  sem init --url https://semaphore.domain.com
  sem init --output ~/.semacli.ini
"""

_LOCATIONS = {
    "1": ("./semacli.ini", "current directory"),
    "2": (str(Path.home() / ".semacli.ini"), "home directory"),
    "3": ("/usr/local/etc/semacli.ini", "system-wide (needs sudo)"),
}


def _normalize_url(raw: str) -> str:
    """Trim trailing slashes and default to https:// when no scheme is given."""
    raw = raw.strip().rstrip("/")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def _ping_with(cfg: SemaphoreConfig) -> str | None:
    """Try a ping against `cfg`. Returns None on success, else an error
    message suitable for showing to the user."""
    try:
        client = SemaphoreClient(cfg, verbose=0)
        client.ping()
    except Exception as e:  # noqa: BLE001 — wizard probe: failures become hints
        return str(e)
    return None


def _check_token(cfg: SemaphoreConfig) -> tuple[int | None, str | None]:
    """Try `/projects` with `cfg`. Returns (project_count, error_msg)."""
    try:
        client = SemaphoreClient(cfg, verbose=0)
        projects = client.get_projects()
        return len(projects), None
    except AuthenticationError as e:
        return None, f"token refused by server: {e}"
    except Exception as e:  # noqa: BLE001 — wizard probe: failures become hints
        return None, str(e)


def _prompt_url() -> tuple[str, bool, bool]:
    """Returns (url, verify_ssl, allow_http) after a working ping."""
    while True:
        raw = click.prompt("URL of the Semaphore server", type=str)
        url = _normalize_url(raw)

        allow_http = False
        if url.startswith("http://"):
            click.echo(
                "warning: plain HTTP transmits credentials in clear text.",
                err=True,
            )
            if not click.confirm("Continue with http:// anyway?", default=False):
                continue
            allow_http = True

        verify_ssl = True
        if url.startswith("https://"):
            verify_ssl = click.confirm("Verify TLS certificate?", default=True)

        cfg = SemaphoreConfig(
            url=url, bearer_token=None, verify_ssl=verify_ssl, allow_http=allow_http
        )
        err = _ping_with(cfg)
        if err is None:
            click.echo("  -> ping OK")
            return url, verify_ssl, allow_http
        click.echo(f"  -> ping failed: {err}", err=True)
        if not click.confirm("Try a different URL?", default=True):
            raise click.Abort()


def _prompt_token(url: str, *, verify_ssl: bool, allow_http: bool) -> str:
    """Prompt for a bearer token until one is accepted by the server."""
    while True:
        click.echo("Generate a token in Semaphore UI -> User Settings -> Create API Token.")
        token: str = click.prompt("Bearer token", hide_input=True)
        cfg = SemaphoreConfig(
            url=url,
            bearer_token=token,
            verify_ssl=verify_ssl,
            allow_http=allow_http,
        )
        count, err = _check_token(cfg)
        if err is None:
            click.echo(f"  -> token OK ({count} project(s) visible)")
            return token
        click.echo(f"  -> {err}", err=True)
        if not click.confirm("Try a different token?", default=True):
            raise click.Abort()


def _prompt_project(cfg: SemaphoreConfig) -> int | None:
    """Pick a default project by id or name; returns None when skipped or ambiguous."""
    projects = SemaphoreClient(cfg, verbose=0).get_projects()
    if not projects:
        click.echo("  no projects visible — skipping default project selection.")
        return None
    click.echo("Available projects:")
    for p in projects:
        click.echo(f"  {p.id:>4}  {p.name}")
    raw = click.prompt(
        "Default project (id or name, blank to skip)",
        default="",
        show_default=False,
    )
    raw = raw.strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    matches = [p for p in projects if raw.casefold() in p.name.casefold()]
    if len(matches) == 1:
        return matches[0].id
    if not matches:
        click.echo("  -> no project matching that name; skipping.", err=True)
        return None
    click.echo("  -> ambiguous; skipping. Set 'project = <id>' manually later.", err=True)
    return None


def _prompt_location() -> Path:
    """Ask which of the known config file locations to write to."""
    click.echo("Where should semacli.ini live?")
    for key, (path, label) in _LOCATIONS.items():
        click.echo(f"  {key}) {path}  ({label})")
    choice = click.prompt("Choice", default="1", type=click.Choice(list(_LOCATIONS.keys())))
    return Path(_LOCATIONS[choice][0]).expanduser()


def _write_ini(
    target: Path,
    *,
    url: str,
    token: str,
    verify_ssl: bool,
    allow_http: bool,
    project: int | None,
) -> None:
    """Write the semacli.ini file from the wizard answers and chmod it 600."""
    lines: list[str] = [
        "[semaphore]",
        f"url = {url}",
    ]
    if project is not None:
        lines.append(f"project = {project}")
    lines += ["", "[auth]", "method = bearer_token", f"bearer_token = {token}"]
    if not verify_ssl or allow_http:
        lines += ["", "[settings]"]
        if not verify_ssl:
            lines.append("verify_ssl = false")
        if allow_http:
            lines.append("allow_http = true")
    lines.append("")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        click.echo(f"warning: could not chmod 600 {target}", err=True)


def _confirm_overwrite(target: Path) -> None:
    """Abort unless the user confirms clobbering an existing ini file."""
    if target.exists() and not click.confirm(f"{target} exists — overwrite?", default=False):
        click.echo("aborted; nothing written.", err=True)
        raise click.Abort()


@click.command("init", cls=RawEpilogCommand, help=INIT_HELP, epilog=INIT_EPILOG)
@click.option("--url", default=None, help="Pre-fill the URL prompt.")
@click.option(
    "--output",
    "output_path",
    default=None,
    help="Write the ini file to this path (skips the location prompt).",
)
def init_cmd(url: str | None, output_path: str | None) -> None:
    """Interactive wizard that writes a working semacli.ini."""
    click.echo("sem init — create a working semacli.ini.\n")
    try:
        if url:
            url = _normalize_url(url)
        chosen_url, verify_ssl, allow_http = (
            _prompt_url() if not url else (url, True, url.startswith("http://"))
        )
        token = _prompt_token(chosen_url, verify_ssl=verify_ssl, allow_http=allow_http)
        cfg = SemaphoreConfig(
            url=chosen_url,
            bearer_token=token,
            verify_ssl=verify_ssl,
            allow_http=allow_http,
        )
        project = _prompt_project(cfg)
        target = Path(output_path).expanduser() if output_path else _prompt_location()
        _confirm_overwrite(target)
        _write_ini(
            target,
            url=chosen_url,
            token=token,
            verify_ssl=verify_ssl,
            allow_http=allow_http,
            project=project,
        )
        click.echo(f"\nwrote {target} (mode 0600).")
        click.echo("\nTry:\n  sem ping\n  sem project\n  sem template")
    except click.Abort:
        raise
    except SemaCliError as e:
        click.echo(f"error: {e}", err=True)
        raise SystemExit(2) from e


def register_init_commands(main_group: Any) -> None:
    """Register the `init` command."""
    main_group.add_command(init_cmd)
    main_group.commands["init"].category = "connection"
