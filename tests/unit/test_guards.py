"""Tests for the pre-run override guard (ken #827) and the arguments guard (ken #636)."""

import pytest

from semacli.core.exceptions import InvalidArgumentsError, OverrideNotAllowedError
from semacli.core.guards import ensure_overrides_allowed, validate_template_arguments
from semacli.core.models import Template, TemplateTaskParams

_PERMISSIVE = TemplateTaskParams(
    allow_debug=True,
    allow_override_inventory=True,
    allow_override_limit=True,
    allow_override_skip_tags=True,
    allow_override_tags=True,
)


def _tpl(**params: bool) -> Template:
    return Template(id=7, name="mtree", task_params=TemplateTaskParams(**params))


class TestEnsureOverridesAllowed:
    def test_no_flags_passes_even_when_restrictive(self) -> None:
        ensure_overrides_allowed(_tpl())

    def test_permissive_template_passes_all_flags(self) -> None:
        tpl = Template(id=7, name="mtree", task_params=_PERMISSIVE)
        ensure_overrides_allowed(tpl, limit="web1", tags="ntp", skip_tags="slow", debug=2)

    @pytest.mark.parametrize(
        ("kwargs", "toggle"),
        [
            ({"limit": "web1"}, "allow_override_limit"),
            ({"tags": "ntp"}, "allow_override_tags"),
            ({"skip_tags": "slow"}, "allow_override_skip_tags"),
            ({"debug": 1}, "allow_debug"),
        ],
    )
    def test_forbidden_flag_raises(self, kwargs: dict, toggle: str) -> None:
        with pytest.raises(OverrideNotAllowedError) as exc:
            ensure_overrides_allowed(_tpl(), **kwargs)
        assert toggle in str(exc.value)
        assert "mtree" in str(exc.value)

    def test_limit_message_mentions_full_inventory(self) -> None:
        with pytest.raises(OverrideNotAllowedError, match="FULL inventory"):
            ensure_overrides_allowed(_tpl(), limit="web1")

    def test_only_relevant_toggle_checked(self) -> None:
        # limit allowed, tags forbidden: --limit alone must pass.
        tpl = _tpl(allow_override_limit=True)
        ensure_overrides_allowed(tpl, limit="web1")
        with pytest.raises(OverrideNotAllowedError):
            ensure_overrides_allowed(tpl, limit="web1", tags="ntp")

    def test_server_default_is_restrictive(self) -> None:
        # A template parsed without task_params (old server payload)
        # must be treated as all-forbidden.
        tpl = Template.model_validate({"id": 7, "name": "mtree"})
        with pytest.raises(OverrideNotAllowedError):
            ensure_overrides_allowed(tpl, limit="web1")


class TestValidateTemplateArguments:
    @pytest.mark.parametrize("value", ["", None, "[]", '["--diff"]', '["--diff", "--check"]'])
    def test_static_flags_pass(self, value: str | None) -> None:
        validate_template_arguments(value)

    @pytest.mark.parametrize(
        "value",
        ['["{{ limit }}"]', '["--limit", "{{ hosts }}"]', '["{% if x %}"]'],
    )
    def test_jinja_placeholder_is_refused(self, value: str) -> None:
        # ken #636: Semaphore stores arguments verbatim; ansible then reads
        # `{{ limit }}` as a literal host pattern.
        with pytest.raises(InvalidArgumentsError, match="Jinja"):
            validate_template_arguments(value)

    def test_non_json_is_refused(self) -> None:
        with pytest.raises(InvalidArgumentsError, match="not valid JSON"):
            validate_template_arguments("--diff")

    def test_json_object_is_refused(self) -> None:
        with pytest.raises(InvalidArgumentsError, match="not a JSON array"):
            validate_template_arguments('{"a": 1}')

    def test_non_string_element_is_refused(self) -> None:
        with pytest.raises(InvalidArgumentsError, match="must be a string"):
            validate_template_arguments("[1, 2]")

    def test_message_carries_the_offending_value(self) -> None:
        with pytest.raises(InvalidArgumentsError) as exc:
            validate_template_arguments("nope")
        assert exc.value.value == "nope"
