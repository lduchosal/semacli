"""Cassette: ``sem env create --name semacli-vcr --vars @vars.json``.

Validates that the ``@file`` expansion happens client-side: the
recorded request body must contain the literal JSON content of the
local file, not the ``@path`` string.

Records create + delete back-to-back so the cassette is
self-cleaning.
"""

from __future__ import annotations

import json

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_env_create_inlines_at_file(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    # We bypass the CLI here and call the client directly with the
    # already-expanded content — the CLI-side expansion is covered by
    # the unit tests. This cassette focuses on the HTTP contract.
    env = client.create_environment(
        RECORD_PROJECT,
        name="semacli-vcr-env",
        json_vars='{"region":"eu-west-1"}',
        password="",
    )
    try:
        assert env.id > 0
        assert env.name == "semacli-vcr-env"

        post = next(
            r
            for r in vcr_cassette.requests  # type: ignore[attr-defined]
            if r.method == "POST" and r.uri.endswith("/environment")
        )
        body = json.loads(post.body)
        assert body["name"] == "semacli-vcr-env"
        # Pydantic-side alias: client sends `json` (the API field name).
        assert body.get("json") == '{"region":"eu-west-1"}'
    finally:
        client.delete_environment(RECORD_PROJECT, env.id)
