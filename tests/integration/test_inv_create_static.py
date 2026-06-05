"""Cassette: ``sem inv create --type static --inventory '[prod]\\nweb1'`` (ken #733).

Validates that the renamed ``--inventory`` option lands in the HTTP
body as the API field ``inventory`` (alias of ``content`` in the
pydantic model), with the inline INI passed through verbatim.

Records create + delete back-to-back so the cassette is
self-cleaning.
"""

from __future__ import annotations

import json

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_inv_create_static_inline(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    inv = client.create_inventory(
        RECORD_PROJECT,
        name="semacli-vcr-inv",
        type="static",
        content="[prod]\nweb1\n",
        ssh_key_id=0,
        become_key_id=0,
    )
    try:
        assert inv.id > 0
        assert inv.name == "semacli-vcr-inv"

        post = next(
            r
            for r in vcr_cassette.requests  # type: ignore[attr-defined]
            if r.method == "POST" and r.uri.endswith("/inventory")
        )
        body = json.loads(post.body)
        assert body["name"] == "semacli-vcr-inv"
        assert body["type"] == "static"
        # API field name for the content is `inventory`.
        assert body.get("inventory") == "[prod]\nweb1\n"
    finally:
        client.delete_inventory(RECORD_PROJECT, inv.id)
