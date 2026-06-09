"""Cassette: ``sem run echo --limit ans1 --check`` — the #738 bug.

This is the test that should have caught the silent ``--limit`` drop.
It records what the client actually puts on the wire (the body of
``POST /api/project/{pid}/tasks``) and asserts that the Semaphore
server responds with a task whose effective limit is the one we asked
for.

Targets the ``echo`` template (purely informational, idempotent by
design) and always recorded with ``--check`` (Semaphore check mode)
so the playbook never alters anything. echo is non-destructive
regardless as a second safety net.

NB: the assertion on the response side depends on what Semaphore
actually returns (task creation echoes the body). The Phase 2 review
(after the first recording) will tighten the assertion to whatever
field actually carries the limit back.
"""

from __future__ import annotations

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_run_with_limit_check(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    import json

    task = client.run_task(
        RECORD_PROJECT,
        template_id=_resolve_echo_id(client),
        limit="ans1",
        dry_run=True,
    )
    assert task.id > 0

    # Inspect the recorded POST /tasks request body — this is what the
    # CLI actually sent. The whole point of the VCR harness: prove the
    # wire contract.
    post = next(
        r
        for r in vcr_cassette.requests  # type: ignore[attr-defined]
        if r.method == "POST" and r.uri.endswith("/tasks")
    )
    body = json.loads(post.body)
    # Per ken #782, ansible flags moved under `params` (with limit as
    # an array). Previously the top-level `limit` string only worked by
    # accident, via the deprecated `PreInsert` migration in db.Task.
    assert body["params"]["limit"] == ["ans1"]
    assert body["params"]["dry_run"] is True
    assert "diff" not in body["params"]  # we did not pass --diff
    assert "limit" not in body  # no longer at the top level


def _resolve_echo_id(client: SemaphoreClient) -> int:
    """Return the template id for echo on the recording target."""
    for t in client.get_templates(RECORD_PROJECT):
        if t.name.casefold() == "echo":
            return t.id
    pytest.skip("echo template not present on recording target")
