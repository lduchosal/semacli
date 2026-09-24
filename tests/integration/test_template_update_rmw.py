"""Cassette: ``template update`` is read-modify-write (ken #1118).

Semaphore's PUT replaces the whole row. semacli used to send only the
fields the caller passed, which made the server answer ``HTTP 400
Invalid app id`` — and, when it did go through, silently wiped
``task_params`` / ``view_id``, turning a rename into a template that
ignores ``--limit``.

Creates a throwaway template, patches one field, and checks what the
server kept. Create + update + delete are recorded back-to-back so the
cassette is self-cleaning.
"""

from __future__ import annotations

import json

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_template_update_preserves_unpassed_fields(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    tpl = client.create_template(
        RECORD_PROJECT,
        name="semacli-vcr-rmw",
        playbook="ping.yml",
        inventory_id=4,
        repository_id=3,
        description="vcr cassette ken #1118",
        view_id=2,
    )
    try:
        client.update_template(RECORD_PROJECT, tpl.id, description="patched by vcr")

        put = next(
            r for r in vcr_cassette.requests if r.method == "PUT"  # type: ignore[attr-defined]
        )
        body = json.loads(put.body)
        # The PUT carries the whole row, not just the patched field.
        assert body["description"] == "patched by vcr"
        assert body["app"] == "ansible"
        assert body["playbook"] == "ping.yml"
        assert body["task_params"]["allow_override_limit"] is True
        # Server-computed fields are never echoed back.
        assert "tasks" not in body

        after = client.get_template(RECORD_PROJECT, tpl.id)
        assert after.description == "patched by vcr"
        assert after.app == "ansible"
        assert after.view_id == 2
        assert after.task_params.allow_override_limit is True
        assert after.task_params.allow_debug is True
    finally:
        client.delete_template(RECORD_PROJECT, tpl.id)
