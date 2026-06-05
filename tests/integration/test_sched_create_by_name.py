"""Cassette: ``sem sched create --template echo --cron '0 3 * * *'``.

Validates the name-first fix from ken #736: the CLI resolves the name
``echo`` through ``resolve_template`` and POSTs ``/schedules`` with
the numeric id. The cassette records the GET (template list), the POST
(schedule create) and the DELETE (cleanup) — all in one go so a replay
exercises the full lifecycle.
"""

from __future__ import annotations

import json

import pytest

from semacli.core.client import SemaphoreClient
from semacli.core.resolve import resolve_template

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_sched_create_resolves_name(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    template_id = resolve_template(client, RECORD_PROJECT, "echo")
    sched = client.create_schedule(
        RECORD_PROJECT,
        template_id=template_id,
        cron_format="0 3 * * *",
        name="semacli-vcr-test",
        active=False,  # created inactive so it does not actually fire
    )
    try:
        assert sched.id > 0
        assert sched.template_id == template_id

        post = next(
            r
            for r in vcr_cassette.requests  # type: ignore[attr-defined]
            if r.method == "POST" and r.uri.endswith("/schedules")
        )
        body = json.loads(post.body)
        assert body["template_id"] == template_id
        assert body["cron_format"] == "0 3 * * *"
        assert body["name"] == "semacli-vcr-test"
    finally:
        client.delete_schedule(RECORD_PROJECT, sched.id)
