"""Cassette: bare ping (no auth).

Covers the simplest path through the stack and validates the recording
harness itself before we tackle the trickier endpoints.
"""

from __future__ import annotations

import pytest

from semacli.core.client import SemaphoreClient


@pytest.mark.vcr
def test_ping_returns_pong(client: SemaphoreClient, skip_if_no_cassette: None) -> None:
    assert client.ping() == "pong"
