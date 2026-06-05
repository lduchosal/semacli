"""Cassette: ``sem key create --type login_password --login admin --password 'pw'`` (ken #735).

Validates that login + password go out as two distinct top-level
fields inside the ``login_password`` envelope, NOT a combined
``user:pass`` string.

Records create + delete back-to-back so the cassette is
self-cleaning.
"""

from __future__ import annotations

import json

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_key_create_login_password_split(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    key = client.create_key(
        RECORD_PROJECT,
        name="semacli-vcr-login",
        type="login_password",
        login="admin",
        password="s3cr3t",
    )
    try:
        assert key.id > 0
        assert key.type == "login_password"

        post = next(
            r
            for r in vcr_cassette.requests  # type: ignore[attr-defined]
            if r.method == "POST" and r.uri.endswith("/keys")
        )
        body = json.loads(post.body)
        assert body["name"] == "semacli-vcr-login"
        assert body["type"] == "login_password"
        envelope = body.get("login_password", {})
        assert envelope.get("login") == "admin"
        assert envelope.get("password") == "s3cr3t"
    finally:
        client.delete_key(RECORD_PROJECT, key.id)
