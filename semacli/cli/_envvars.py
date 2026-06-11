"""Helpers for the ``--environment`` flag on ``run`` / ``task run``.

The flag accepts either:
- a JSON object/array string (``'{"msg":"coucou"}'``), or
- ansible-style ``key=val`` pairs (``'msg=coucou foo=bar'``).

Both forms produce a JSON-encoded string suitable for the
``environment`` field of ``POST /tasks``.

Catching malformed input client-side avoids a 500 round-trip whose
body Semaphore often leaves empty after a panic.
"""

from __future__ import annotations

import json

import click


def normalize_environment(raw: str | None) -> str | None:
    """Return a JSON-encoded string for ``body["environment"]``, or None.

    - ``None`` / empty → ``None`` (no override).
    - Starts with ``{`` or ``[`` → must parse as JSON, returned verbatim.
    - Otherwise → parsed as ``key=val [key=val ...]``, returned as JSON.

    Raises ``click.UsageError`` (exit code 2) on malformed input.
    """
    if raw is None or raw == "":
        return None

    stripped = raw.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            json.loads(raw)
        except json.JSONDecodeError as e:
            msg = f"--environment is not valid JSON: {e}"
            raise click.UsageError(msg) from e
        return raw

    pairs: dict[str, str] = {}
    for token in raw.split():
        if "=" not in token:
            msg = f"--environment '{raw}': expected 'key=value' (got '{token}')"
            raise click.UsageError(msg)
        key, _, value = token.partition("=")
        if not key:
            msg = f"--environment '{raw}': empty key in '{token}'"
            raise click.UsageError(msg)
        pairs[key] = value
    return json.dumps(pairs)
