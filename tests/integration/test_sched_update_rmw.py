"""Cassette: ``sched update`` is read-modify-write (ken #1169).

Semaphore's ``PUT /schedules/{sid}`` replaces the whole row: semacli used
to send only the passed fields, so a cron change wiped ``task_params``
(the limit vanished -> the schedule targeted every host of the template)
and ``--inactive`` failed with ``Cron: empty spec string``.

Creates an inactive schedule with a limit, changes only its cron, then
toggles it, checking each time that the server kept the rest. Create +
updates + delete are recorded back-to-back so the cassette self-cleans.
"""

from __future__ import annotations

import pytest

from semacli.core.client import SemaphoreClient
from semacli.core.resolve import resolve_template

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_sched_update_preserves_unpassed_fields(
    client: SemaphoreClient, skip_if_no_cassette: None
) -> None:
    template_id = resolve_template(client, RECORD_PROJECT, "echo")
    sched = client.create_schedule(
        RECORD_PROJECT,
        template_id=template_id,
        cron_format="0 6 * * *",
        name="ken1169-rmw-vcr",
        active=False,  # never actually fires
        inventory_id=4,
        limit="ans1,ans2",
        tags="pkg",
    )
    try:
        client.update_schedule(RECORD_PROJECT, sched.id, cron_format="30 6 * * *")
        after = client.get_schedule(RECORD_PROJECT, sched.id)
        assert after.cron_format == "30 6 * * *"
        assert after.name == "ken1169-rmw-vcr"
        assert after.active is False
        assert after.task_params is not None
        assert after.task_params.inventory_id == 4
        assert after.task_params.params.limit == ["ans1", "ans2"]
        assert after.task_params.params.tags == ["pkg"]

        client.update_schedule(RECORD_PROJECT, sched.id, limit="ans1")
        after = client.get_schedule(RECORD_PROJECT, sched.id)
        assert after.task_params is not None
        assert after.task_params.params.limit == ["ans1"]
        assert after.task_params.params.tags == ["pkg"]
        assert after.task_params.inventory_id == 4

        # --active / --inactive alone: no cron resent, nothing else touched.
        client.update_schedule(RECORD_PROJECT, sched.id, active=True)
        client.update_schedule(RECORD_PROJECT, sched.id, active=False)
        after = client.get_schedule(RECORD_PROJECT, sched.id)
        assert after.active is False
        assert after.cron_format == "30 6 * * *"
        assert after.task_params is not None
        assert after.task_params.params.limit == ["ans1"]
    finally:
        client.delete_schedule(RECORD_PROJECT, sched.id)
