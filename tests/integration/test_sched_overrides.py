"""Cassettes: schedule overrides + run-at one-shot round-trip (ken #907).

These exercise the real Semaphore contract for the fields added in ken
#907: a schedule's nested ``task_params`` (inventory / limit / tags /
skip-tags / cli-args / message) and the run-at one-shot trigger
(``type: "run_at"`` + ``run_at`` + ``delete_after_run``).

Each test creates an INACTIVE schedule (so it never fires), GETs it back
to confirm the server stored and returns the fields, then deletes it in a
``finally`` so the cassette captures the DELETE and the server is left
clean.
"""

from __future__ import annotations

import json

import pytest

from semacli.core.client import SemaphoreClient
from semacli.core.resolve import resolve_template

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_sched_overrides_roundtrip(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    template_id = resolve_template(client, RECORD_PROJECT, "echo")
    sched = client.create_schedule(
        RECORD_PROJECT,
        template_id=template_id,
        cron_format="0 3 * * *",
        name="ken907-overrides-vcr",
        active=False,  # never actually fires
        message="ken907-vcr",
        inventory_id=4,  # the "hosts" inventory on the record project
        cli_args='["--forks","5"]',
        limit="ans1,ans2",
        tags="pkg",
        skip_tags="slow",
    )
    try:
        assert sched.id > 0

        # The POST body carries the nested task_params shape (Semaphore db.TaskParams).
        post = next(
            r
            for r in vcr_cassette.requests  # type: ignore[attr-defined]
            if r.method == "POST" and r.uri.endswith("/schedules")
        )
        tp = json.loads(post.body)["task_params"]
        assert tp["inventory_id"] == 4
        assert tp["message"] == "ken907-vcr"
        assert tp["arguments"] == '["--forks","5"]'
        assert tp["params"] == {"limit": ["ans1", "ans2"], "tags": ["pkg"], "skip_tags": ["slow"]}

        # GET-after-save: the server returns the overrides it persisted.
        fetched = client.get_schedule(RECORD_PROJECT, sched.id)
        assert fetched.task_params is not None
        assert fetched.task_params.inventory_id == 4
        assert fetched.task_params.params.limit == ["ans1", "ans2"]
        assert fetched.task_params.params.tags == ["pkg"]
        assert fetched.task_params.params.skip_tags == ["slow"]
    finally:
        client.delete_schedule(RECORD_PROJECT, sched.id)


@pytest.mark.vcr
def test_sched_run_at_once_roundtrip(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    template_id = resolve_template(client, RECORD_PROJECT, "echo")
    sched = client.create_schedule(
        RECORD_PROJECT,
        template_id=template_id,
        cron_format="",
        name="ken907-runat-vcr",
        active=False,
        schedule_type="run_at",
        run_at="2030-01-01T02:00:00Z",  # far future so the cassette stays valid
        delete_after_run=True,
    )
    try:
        assert sched.id > 0

        post = next(
            r
            for r in vcr_cassette.requests  # type: ignore[attr-defined]
            if r.method == "POST" and r.uri.endswith("/schedules")
        )
        body = json.loads(post.body)
        assert body["type"] == "run_at"
        assert body["run_at"] == "2030-01-01T02:00:00Z"
        assert body["delete_after_run"] is True

        fetched = client.get_schedule(RECORD_PROJECT, sched.id)
        assert fetched.type == "run_at"
        assert fetched.delete_after_run is True
    finally:
        client.delete_schedule(RECORD_PROJECT, sched.id)
