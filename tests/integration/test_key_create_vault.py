"""Cassette: ``sem key create --type none --password 's3cr3t'`` (ken #734).

The first VCR-style proof that ``body["string"] = password`` is the
right shape for a secret-only key on this Semaphore version. If the
upstream API later changes the field name to ``override_secret`` or
similar, this test goes red on the next replay.

Records create + delete back-to-back so the cassette is
self-cleaning.
"""

from __future__ import annotations

import json

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_key_create_type_none_with_password(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    key = client.create_key(
        RECORD_PROJECT,
        name="semacli-vcr-vault",
        type="none",
        password="s3cr3t",
    )
    try:
        assert key.id > 0
        assert key.type == "none"

        post = next(
            r
            for r in vcr_cassette.requests  # type: ignore[attr-defined]
            if r.method == "POST" and r.uri.endswith("/keys")
        )
        body = json.loads(post.body)
        assert body["name"] == "semacli-vcr-vault"
        assert body["type"] == "none"
        # Ken #734: type=none secret goes in top-level `string` field.
        assert body.get("string") == "s3cr3t"
    finally:
        client.delete_key(RECORD_PROJECT, key.id)
