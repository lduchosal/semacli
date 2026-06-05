"""Cassette: ``sem run echo --environment '{"msg":"hello-vcr"}'``.

The ``echo`` role accepts an ``msg`` extra-var and echoes it back in
its output. This cassette validates the ``--environment`` flag (JSON
env-vars override) end-to-end: the cassette captures both the POST
``/tasks`` body that carries the JSON-encoded vars and the task output
fetch that shows the echoed message.

Recorded with ``--check`` for symmetry with the other run cassettes,
even though echo is read-only.
"""

from __future__ import annotations

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT

MSG = "hello-vcr"


@pytest.mark.vcr
def test_run_environment_override(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    import json

    task = client.run_task(
        RECORD_PROJECT,
        template_id=_resolve_echo_id(client),
        environment=f'{{"msg":"{MSG}"}}',
        dry_run=True,
    )
    assert task.id > 0

    post = next(
        r
        for r in vcr_cassette.requests  # type: ignore[attr-defined]
        if r.method == "POST" and r.uri.endswith("/tasks")
    )
    body = json.loads(post.body)
    # The environment field is a JSON-encoded string at the body level.
    assert body["environment"] == f'{{"msg":"{MSG}"}}'
    assert json.loads(body["environment"]) == {"msg": MSG}
    assert body["dry_run"] is True


def _resolve_echo_id(client: SemaphoreClient) -> int:
    for t in client.get_templates(RECORD_PROJECT):
        if t.name.casefold() == "echo":
            return t.id
    pytest.skip("echo template not present on recording target")
