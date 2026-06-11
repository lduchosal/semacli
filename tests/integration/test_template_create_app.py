"""Cassette: ``sem template create`` sends the ``app`` field (ken #812).

Modern Semaphore rejects a template payload without ``app`` with
``HTTP 400 Invalid app id``. Validates that ``create_template``
defaults to ``app=ansible`` and that the server accepts the payload.

Records create + delete back-to-back so the cassette is
self-cleaning.
"""

from __future__ import annotations

import json

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_template_create_sends_app(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    tpl = client.create_template(
        RECORD_PROJECT,
        name="semacli-vcr-tpl",
        playbook="ping.yml",
        inventory_id=4,
        repository_id=3,
        description="vcr cassette ken #812",
    )
    try:
        assert tpl.id > 0
        assert tpl.name == "semacli-vcr-tpl"

        post = next(
            r
            for r in vcr_cassette.requests  # type: ignore[attr-defined]
            if r.method == "POST" and r.uri.endswith("/templates")
        )
        body = json.loads(post.body)
        assert body["app"] == "ansible"
        assert body["playbook"] == "ping.yml"
        # Permissive by default (ken #826): without these the server
        # silently drops per-run --limit/--tags/--debug.
        assert body["allow_override_args_in_task"] is True
        assert all(body["task_params"].values())

        # The server must persist the toggles, not just accept them.
        created = client.get_template(RECORD_PROJECT, tpl.id)
        assert created.task_params.allow_override_limit is True
        assert created.task_params.allow_debug is True
    finally:
        client.delete_template(RECORD_PROJECT, tpl.id)
