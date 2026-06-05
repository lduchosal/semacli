"""Cassette: ``sem run echo --check --diff``.

Validates the two ansible-mode flags (`--check` = no-changes,
`--diff` = show file changes) — they are independently passed in the
body as ``dry_run`` and ``diff``. Recorded against the safe ``echo``
template; the playbook is purely informational so ``--check`` is
overkill, but it pins the contract.
"""

from __future__ import annotations

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT


@pytest.mark.vcr
def test_run_check_and_diff(
    client: SemaphoreClient, skip_if_no_cassette: None, vcr_cassette: object
) -> None:
    import json

    task = client.run_task(
        RECORD_PROJECT,
        template_id=_resolve_echo_id(client),
        dry_run=True,
        diff=True,
    )
    assert task.id > 0

    post = next(
        r
        for r in vcr_cassette.requests  # type: ignore[attr-defined]
        if r.method == "POST" and r.uri.endswith("/tasks")
    )
    body = json.loads(post.body)
    assert body["dry_run"] is True
    assert body["diff"] is True
    assert "limit" not in body


def _resolve_echo_id(client: SemaphoreClient) -> int:
    for t in client.get_templates(RECORD_PROJECT):
        if t.name.casefold() == "echo":
            return t.id
    pytest.skip("echo template not present on recording target")
