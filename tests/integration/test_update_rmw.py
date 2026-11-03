"""Cassettes: every ``<resource> update`` is read-modify-write (ken #1170).

Semaphore's PUT replaces the whole row: semacli used to send only the
fields the caller passed, so a lone ``--name`` blanked the rest (extra
vars of an environment, inventory content, repository URL…) or got a 400.
Same family as ken #1118 (template) and ken #1169 (schedule).

Each test creates a throwaway resource on the record project, patches ONE
field, re-reads the raw object and checks that the other fields survived,
then deletes it in a ``finally`` so the cassette self-cleans. Users and the
project itself are not recorded: patching them on the live server is not
throwaway (unit tests cover their merge).
"""

from __future__ import annotations

from typing import Any

import pytest

from semacli.core.client import SemaphoreClient
from semacli.core.resolve import resolve_template

from .conftest import RECORD_PROJECT

P = RECORD_PROJECT
_FAKE_PEM = "-----BEGIN OPENSSH PRIVATE KEY-----\nvcr\n-----END OPENSSH PRIVATE KEY-----\n"


def _raw(client: SemaphoreClient, path: str) -> dict[str, Any]:
    data = client._request(f"project/{P}/{path}")  # noqa: SLF001  # raw GET, no model filtering
    assert isinstance(data, dict)
    return data


@pytest.mark.vcr
def test_env_update_keeps_vars(client: SemaphoreClient, skip_if_no_cassette: None) -> None:
    env = client.create_environment(P, "ken1170-env-vcr", json_vars='{"a": 1}', password="vlt")
    try:
        client.update_environment(P, env.id, name="ken1170-env-vcr-renamed")
        after = _raw(client, f"environment/{env.id}")
        assert after["name"] == "ken1170-env-vcr-renamed"
        assert after["json"] == '{"a": 1}'
        assert after["password"] == "vlt"
    finally:
        client.delete_environment(P, env.id)


@pytest.mark.vcr
def test_key_update_rename_and_rotate(client: SemaphoreClient, skip_if_no_cassette: None) -> None:
    key = client.create_key(
        P, name="ken1170-key-vcr", type="login_password", login="u", password="p"
    )
    try:
        # rename only: no override_secret, type untouched
        client.update_key(P, key.id, name="ken1170-key-vcr-renamed")
        after = _raw(client, f"keys/{key.id}")
        assert after["name"] == "ken1170-key-vcr-renamed"
        assert after["type"] == "login_password"

        # --private-key: the secret is really replaced (override_secret)
        client.update_key(
            P, key.id, ssh={"private_key": _FAKE_PEM, "login": "root", "passphrase": ""}
        )
        after = _raw(client, f"keys/{key.id}")
        assert after["name"] == "ken1170-key-vcr-renamed"
        assert after["type"] == "ssh"
    finally:
        client.delete_key(P, key.id)


@pytest.mark.vcr
def test_inv_and_repo_update_keep_fields(
    client: SemaphoreClient, skip_if_no_cassette: None
) -> None:
    key = client.create_key(P, name="ken1170-invkey-vcr", type="none")
    inv = client.create_inventory(
        P, name="ken1170-inv-vcr", type="static", content="[all]\nh1\n", ssh_key_id=key.id
    )
    repo = client.create_repository(
        P,
        name="ken1170-repo-vcr",
        git_url="https://example.invalid/vcr.git",
        git_branch="main",
        ssh_key_id=key.id,
    )
    try:
        client.update_inventory(P, inv.id, name="ken1170-inv-vcr-renamed")
        after = _raw(client, f"inventory/{inv.id}")
        assert after["name"] == "ken1170-inv-vcr-renamed"
        assert after["inventory"] == "[all]\nh1\n"
        assert after["type"] == "static"
        assert after["ssh_key_id"] == key.id

        client.update_repository(P, repo.id, git_branch="develop")
        after = _raw(client, f"repositories/{repo.id}")
        assert after["git_branch"] == "develop"
        assert after["git_url"] == "https://example.invalid/vcr.git"
        assert after["name"] == "ken1170-repo-vcr"
        assert after["ssh_key_id"] == key.id
    finally:
        client.delete_repository(P, repo.id)
        client.delete_inventory(P, inv.id)
        client.delete_key(P, key.id)


@pytest.mark.vcr
def test_view_update_keeps_title(client: SemaphoreClient, skip_if_no_cassette: None) -> None:
    view = client.create_view(P, "ken1170-view-vcr", position=7)
    try:
        client.update_view(P, view.id, position=8)  # used to 400 "title can not be empty"
        after = _raw(client, f"views/{view.id}")
        assert after["title"] == "ken1170-view-vcr"
        assert after["position"] == 8
    finally:
        client.delete_view(P, view.id)


@pytest.mark.vcr
def test_integration_and_matcher_update(client: SemaphoreClient, skip_if_no_cassette: None) -> None:
    template_id = resolve_template(client, P, "echo")
    integ = client.create_integration(
        P, name="ken1170-integ-vcr", template_id=template_id, auth_header="X-Vcr"
    )
    try:
        matcher = client.add_integration_matcher(
            P, integ.id, name="m", match_type="equals", method="body", key="ref", value="main"
        )
        client.update_integration(P, integ.id, name="ken1170-integ-vcr-renamed")
        after = _raw(client, f"integrations/{integ.id}")
        assert after["name"] == "ken1170-integ-vcr-renamed"
        assert after["template_id"] == template_id
        assert after["auth_header"] == "X-Vcr"

        client.update_integration_matcher(P, integ.id, matcher.id, value="develop")
        after = _raw(client, f"integrations/{integ.id}/matchers/{matcher.id}")
        assert after["value"] == "develop"
        assert after["key"] == "ref"
        assert after["match_type"] == "equals"
        assert after["name"] == "m"
    finally:
        client.delete_integration(P, integ.id)
