"""Tests for the pre-run override guard (ken #827)."""

import pytest

from semacli.core.exceptions import OverrideNotAllowedError
from semacli.core.guards import ensure_overrides_allowed
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
