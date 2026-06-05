"""VCR harness for the integration tests.

These tests record real HTTP traffic against a Semaphore server (mode
``record``) and replay it from cassettes the next time (mode ``replay``,
default in CI). The cassette files live under ``tests/integration/cassettes/``
and are committed alongside the test code.

# Modes

- ``none`` (default) — replay only. If a cassette is missing, the
  test is skipped with a clear message. CI runs in this mode and
  must NEVER touch the network.
- ``once`` — record on first run, replay thereafter. This is the mode
  to set on a developer box when adding a new cassette.

Toggle with the ``SEMACLI_RECORD`` environment variable: set to ``1``,
``true`` or a record mode name (``once``, ``new_episodes``,
``all``). Anything else means "replay only".

# Security

The Authorization header is always scrubbed before the cassette hits
disk; the token never lands in git.

# Recording configuration

Recording targets the Semaphore server at ``SEMACLI_RECORD_URL``,
falling back to whatever ``semacli.ini`` is configured with. The bearer
token comes from ``SEMACLI_RECORD_TOKEN`` (or ``semacli.ini``). The
default project id (for endpoints that need one) is ``SEMACLI_RECORD_PROJECT``
(default ``1`` or whatever ``semacli.ini`` says).

For replay mode the URL is rewritten to ``ANON_URL`` at record time
(see ``_anonymise_request``) so the cassettes never carry the real
hostname or path prefix.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from semacli.core.client import SemaphoreClient
from semacli.core.config import SemaphoreConfig, load_config

CASSETTE_DIR = Path(__file__).parent / "cassettes"

_RECORD_ENV = os.environ.get("SEMACLI_RECORD", "").strip().lower()
_RECORD_MODE_MAP = {
    "1": "once",
    "true": "once",
    "yes": "once",
    "once": "once",
    "new_episodes": "new_episodes",
    "all": "all",
    "none": "none",
    "": "none",
}
RECORD_MODE = _RECORD_MODE_MAP.get(_RECORD_ENV, "none")


def _load_record_target() -> tuple[str, str, int]:
    """Resolve the recording URL / token / project.

    Precedence:
    1. ``SEMACLI_RECORD_URL`` / ``SEMACLI_RECORD_TOKEN`` /
       ``SEMACLI_RECORD_PROJECT`` env vars (CI / explicit override).
    2. The project's ``semacli.ini`` (so developers can record with their
       existing config without exporting anything).
    3. Replay-only placeholders (no actual recording will work).
    """
    url = os.environ.get("SEMACLI_RECORD_URL")
    token = os.environ.get("SEMACLI_RECORD_TOKEN")
    project_str = os.environ.get("SEMACLI_RECORD_PROJECT")

    if url and token and project_str:
        return url, token, int(project_str)

    try:
        cfg = load_config("semacli.ini")
        return (
            url or cfg.url,
            token or (cfg.bearer_token or "REPLAY_ONLY_NO_TOKEN"),
            int(project_str) if project_str else (cfg.project or 1),
        )
    except Exception:
        return (
            url or "https://semaphore.example",
            token or "REPLAY_ONLY_NO_TOKEN",
            int(project_str) if project_str else 1,
        )


RECORD_URL, RECORD_TOKEN, RECORD_PROJECT = _load_record_target()


# ─────────────────────────────────────────────────────────────────────────
# Anonymisation
# ─────────────────────────────────────────────────────────────────────────
# Cassettes are committed to git, so the real Semaphore hostname must
# never land in them. During recording the ``before_record_request`` and
# ``before_record_response`` callbacks rewrite the URL to ``ANON_URL``.
# During replay the client fixture also points at ``ANON_URL`` so VCR's
# strict host+path matchers find the recorded entries.
ANON_URL = "https://semaphore.domain.com"
_EFFECTIVE_URL = RECORD_URL if RECORD_MODE != "none" else ANON_URL


def _anonymise_uri(uri: str) -> str:
    return uri.replace(RECORD_URL, ANON_URL) if RECORD_URL != ANON_URL else uri


def _before_record_request(request: Any) -> Any:
    request.uri = _anonymise_uri(request.uri)
    return request


def _before_record_response(response: Any) -> Any:
    # vcrpy gives us a dict-shaped response. Rewrite the body string if it
    # echoes the real URL (rare, but Semaphore sometimes embeds absolute
    # URLs in JSON metadata).
    body = response.get("body", {})
    raw = body.get("string")
    if isinstance(raw, str) and RECORD_URL in raw and RECORD_URL != ANON_URL:
        body["string"] = raw.replace(RECORD_URL, ANON_URL)
    return response


# ─────────────────────────────────────────────────────────────────────────
# VCR configuration (consumed by pytest-vcr)
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    """Per-module VCR configuration.

    - Token scrubbed via ``filter_headers``.
    - Real Semaphore URL rewritten to ``ANON_URL`` before write.
    - Match by method + host + path + query + body so that a stale
      cassette breaks the test instead of silently passing.
    """
    return {
        "filter_headers": [("authorization", "Bearer REDACTED")],
        "before_record_request": _before_record_request,
        "before_record_response": _before_record_response,
        "match_on": ["method", "scheme", "host", "port", "path", "query", "body"],
        "record_mode": RECORD_MODE,
        "decode_compressed_response": True,
    }


@pytest.fixture(scope="module")
def vcr_cassette_dir() -> str:
    return str(CASSETTE_DIR)


# ─────────────────────────────────────────────────────────────────────────
# Client fixture
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def client() -> Iterator[SemaphoreClient]:
    """A ``SemaphoreClient`` pointed at the recording target.

    - Record mode: real URL from ``semacli.ini`` / env vars.
    - Replay mode: ``ANON_URL`` to match the scrubbed cassettes.
    """
    cfg = SemaphoreConfig(
        url=_EFFECTIVE_URL,
        bearer_token=RECORD_TOKEN,
        project=RECORD_PROJECT,
        timeout=15,
        verify_ssl=True,
        allow_http=False,
    )
    c = SemaphoreClient(cfg, verbose=0)
    yield c


# ─────────────────────────────────────────────────────────────────────────
# Helpers used by the test skeletons
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def skip_if_no_cassette(request: pytest.FixtureRequest) -> None:
    """Skip in replay mode when the cassette file is absent.

    The cassette path is derived from the test function name — that's
    the convention pytest-vcr uses by default (``<test_name>.yaml``).
    """
    cassette_file = CASSETTE_DIR / f"{request.node.name}.yaml"
    if RECORD_MODE == "none" and not cassette_file.exists():
        pytest.skip(
            f"awaiting recording: cassettes/{cassette_file.name} does not exist yet. "
            f"Run with SEMACLI_RECORD=1 against the real server to capture it."
        )
