"""Tests for the override vocabulary shared by create / update / sync / audit."""

import pytest

from semacli.core.exceptions import InvalidOverrideSpecError
from semacli.core.overrides import (
    OVERRIDE_TOGGLES,
    allowed_words,
    missing_words,
    parse_allow_override,
    permissive_task_params,
)


class TestParseAllowOverride:
    def test_none_means_untouched(self) -> None:
        assert parse_allow_override(None) is None

    def test_all_enables_every_toggle(self) -> None:
        assert parse_allow_override("all") == permissive_task_params()

    def test_none_word_disables_every_toggle(self) -> None:
        assert set(parse_allow_override("none").values()) == {False}

    def test_comma_list_is_exclusive(self) -> None:
        parsed = parse_allow_override("limit,tags")
        assert parsed == {
            "allow_override_limit": True,
            "allow_override_tags": True,
            "allow_override_skip_tags": False,
            "allow_override_inventory": False,
            "allow_debug": False,
        }

    def test_sequence_and_whitespace_and_case(self) -> None:
        assert parse_allow_override([" Limit ", "SKIP-TAGS"]) == parse_allow_override(
            "limit,skip-tags"
        )

    def test_unknown_word_raises_and_lists_the_known_ones(self) -> None:
        with pytest.raises(InvalidOverrideSpecError) as exc:
            parse_allow_override("limit,bogus")
        assert exc.value.unknown == ["bogus"]
        assert "limit" in str(exc.value)

    def test_all_wins_over_a_narrower_word(self) -> None:
        assert parse_allow_override("limit,all") == permissive_task_params()


class TestWordHelpers:
    def test_allowed_words_follows_declaration_order(self) -> None:
        assert allowed_words(permissive_task_params()) == list(OVERRIDE_TOGGLES)

    def test_allowed_words_empty_when_all_false(self) -> None:
        assert allowed_words({}) == []

    def test_missing_words_reports_only_the_required_ones(self) -> None:
        params = {"allow_override_limit": True}
        assert missing_words(params, ["limit", "tags", "debug"]) == ["tags", "debug"]
