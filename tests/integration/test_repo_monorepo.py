"""Cassette: ``repo update --monorepo`` against the svn fork (ken #1248).

The fork v2.21.0-svn.1 adds a ``monorepo`` repository field (one checkout
shared by every template). The test creates a throwaway repository, flips
the flag on then off through the read-modify-write update, re-reads the
raw object each time and checks the other fields survived, then deletes
it in a ``finally`` so the cassette self-cleans.
"""

from __future__ import annotations

from typing import Any

import pytest

from semacli.core.client import SemaphoreClient

from .conftest import RECORD_PROJECT

P = RECORD_PROJECT


def _raw(client: SemaphoreClient, path: str) -> dict[str, Any]:
    data = client._request(f"project/{P}/{path}")  # noqa: SLF001  # raw GET, no model filtering
    assert isinstance(data, dict)
    return data


@pytest.mark.vcr
def test_repo_update_monorepo_roundtrip(client: SemaphoreClient, skip_if_no_cassette: None) -> None:
    key = client.create_key(P, name="ken1248-key-vcr", type="none")
    repo = client.create_repository(
        P,
        name="ken1248-repo-vcr",
        git_url="https://example.invalid/vcr.git",
        git_branch="main",
        ssh_key_id=key.id,
    )
    try:
        assert _raw(client, f"repositories/{repo.id}")["monorepo"] is False

        client.update_repository(P, repo.id, monorepo=True)
        after = _raw(client, f"repositories/{repo.id}")
        assert after["monorepo"] is True
        assert after["git_url"] == "https://example.invalid/vcr.git"
        assert after["git_branch"] == "main"
        assert after["ssh_key_id"] == key.id
        assert client.get_repository(P, repo.id).monorepo is True

        client.update_repository(P, repo.id, monorepo=False)
        assert _raw(client, f"repositories/{repo.id}")["monorepo"] is False
    finally:
        client.delete_repository(P, repo.id)
        client.delete_key(P, key.id)
