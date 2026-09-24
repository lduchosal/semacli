"""Tests for the `template sync` planner (pure, offline)."""

import pytest

from semacli.core.exceptions import InvalidArgumentsError, NotFoundError
from semacli.core.manifest import TemplateSpec
from semacli.core.sync import (
    CREATE,
    SKIP,
    UPDATE,
    Change,
    NameIndex,
    desired_body,
    diff_body,
    plan_sync,
)

_INDEX = NameIndex(
    repositories={"2113-ansible": 3},
    inventories={"hosts": 4},
    environments={"default": 1},
    views={"bsd": 2, "book": 9},
)


def _spec(**overrides: object) -> TemplateSpec:
    base = {
        "name": "mtree",
        "playbook": "mtree.yml",
        "repository": "2113-ansible",
        "inventory": "hosts",
        "environment": "default",
        "description": "Run ansible playbook mtree.yml",
    }
    base.update(overrides)
    return TemplateSpec(**base)  # type: ignore[arg-type]


def _existing(**overrides: object) -> dict:
    base = {
        "id": 6,
        "name": "mtree",
        "playbook": "mtree.yml",
        "app": "ansible",
        "repository_id": 3,
        "inventory_id": 4,
        "environment_id": 1,
        "view_id": 2,
        "description": "Run ansible playbook mtree.yml",
        "arguments": "[]",
        "allow_override_args_in_task": True,
        "task_params": {
            "allow_debug": True,
            "allow_override_inventory": True,
            "allow_override_limit": True,
            "allow_override_skip_tags": True,
            "allow_override_tags": True,
        },
    }
    base.update(overrides)
    return base


class TestNameIndex:
    def test_digits_pass_through_without_a_lookup(self) -> None:
        assert _INDEX.lookup("views", "42") == 42
        assert _INDEX.lookup("views", 42) == 42

    def test_none_stays_none(self) -> None:
        assert _INDEX.lookup("environments", None) is None

    def test_name_is_case_insensitive(self) -> None:
        assert _INDEX.lookup("views", "BSD") == 2

    def test_unknown_name_lists_the_candidates(self) -> None:
        with pytest.raises(NotFoundError) as exc:
            _INDEX.lookup("views", "nope")
        assert "bsd" in str(exc.value)


class TestDesiredBody:
    def test_resolves_names_and_defaults_to_permissive(self) -> None:
        body = desired_body(_spec(view="BSD"), _INDEX, 1)
        assert body["repository_id"] == 3
        assert body["inventory_id"] == 4
        assert body["environment_id"] == 1
        assert body["view_id"] == 2
        assert body["task_params"]["allow_override_limit"] is True

    def test_no_view_means_zero_not_null(self) -> None:
        assert desired_body(_spec(), _INDEX, 1)["view_id"] == 0

    def test_empty_arguments_normalise_to_an_empty_array(self) -> None:
        assert desired_body(_spec(), _INDEX, 1)["arguments"] == "[]"

    def test_environment_omitted_when_not_declared(self) -> None:
        assert "environment_id" not in desired_body(_spec(environment=None), _INDEX, 1)

    def test_explicit_allow_override_narrows(self) -> None:
        body = desired_body(_spec(allow_override="limit"), _INDEX, 1)
        assert body["task_params"]["allow_override_limit"] is True
        assert body["task_params"]["allow_debug"] is False

    def test_jinja_arguments_are_refused(self) -> None:
        # ken #636: Semaphore never expands them, ansible reads a host pattern.
        with pytest.raises(InvalidArgumentsError):
            desired_body(_spec(arguments='["--limit", "{{ limit }}"]'), _INDEX, 1)


class TestDiffBody:
    def test_identical_is_empty(self) -> None:
        assert diff_body(_existing(), desired_body(_spec(view="BSD"), _INDEX, 1)) == ()

    def test_null_view_equals_zero(self) -> None:
        assert diff_body(_existing(view_id=None), desired_body(_spec(), _INDEX, 1)) == ()

    def test_reports_field_and_toggle_changes(self) -> None:
        existing = _existing(view_id=None, task_params={"allow_override_limit": True})
        changes = diff_body(existing, desired_body(_spec(view="BSD"), _INDEX, 1))
        assert Change("view_id", 0, 2) in changes
        assert Change("task_params.allow_debug", False, True) in changes

    def test_change_renders_as_old_arrow_new(self) -> None:
        assert str(Change("view_id", 0, 2)) == "view_id: 0 -> 2"


class TestPlanSync:
    def test_missing_name_is_a_create(self) -> None:
        plan = plan_sync([_spec()], [], _INDEX, 1, update=False)
        assert plan.actions[0].verb == CREATE
        assert plan.count(CREATE) == 1

    def test_existing_name_is_skipped_without_update(self) -> None:
        plan = plan_sync([_spec(view="BOOK")], [_existing()], _INDEX, 1, update=False)
        action = plan.actions[0]
        assert action.verb == SKIP
        assert action.reason == "exists"
        assert action.changes  # the diff is computed, just not applied

    def test_update_only_touches_what_differs(self) -> None:
        plan = plan_sync([_spec(view="BOOK")], [_existing()], _INDEX, 1, update=True)
        assert plan.actions[0].verb == UPDATE
        assert plan.actions[0].template_id == 6

    def test_update_skips_an_identical_template(self) -> None:
        plan = plan_sync([_spec(view="BSD")], [_existing()], _INDEX, 1, update=True)
        assert plan.actions[0].verb == SKIP
        assert plan.actions[0].reason == "unchanged"

    def test_server_only_templates_are_orphans_never_deleted(self) -> None:
        plan = plan_sync(
            [_spec()], [_existing(), _existing(id=7, name="legacy")], _INDEX, 1, update=True
        )
        assert plan.orphans == ("legacy",)
