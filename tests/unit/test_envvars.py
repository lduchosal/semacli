"""Tests for the ``--environment`` normalizer (ken #745)."""

from __future__ import annotations

import json

import click
import pytest

from semacli.cli._envvars import normalize_environment


class TestNormalizeEnvironment:
    def test_none_is_passthrough(self) -> None:
        assert normalize_environment(None) is None

    def test_empty_is_passthrough(self) -> None:
        assert normalize_environment("") is None

    def test_valid_json_object_unchanged(self) -> None:
        raw = '{"msg":"coucou"}'
        assert normalize_environment(raw) == raw

    def test_valid_json_array_unchanged(self) -> None:
        raw = "[1, 2, 3]"
        assert normalize_environment(raw) == raw

    def test_valid_json_with_leading_whitespace(self) -> None:
        raw = '   {"k":"v"}'
        assert normalize_environment(raw) == raw

    def test_invalid_json_raises_usage_error(self) -> None:
        with pytest.raises(click.UsageError) as exc:
            normalize_environment('{"msg":"coucou"')  # missing closing brace
        assert "not valid JSON" in str(exc.value)

    def test_single_key_val(self) -> None:
        result = normalize_environment("msg=coucou")
        assert result is not None
        assert json.loads(result) == {"msg": "coucou"}

    def test_multiple_key_val(self) -> None:
        result = normalize_environment("msg=coucou foo=bar")
        assert result is not None
        assert json.loads(result) == {"msg": "coucou", "foo": "bar"}

    def test_value_can_contain_equals(self) -> None:
        # split on the FIRST '=' only, so `msg=a=b` → {"msg":"a=b"}
        result = normalize_environment("msg=a=b")
        assert result is not None
        assert json.loads(result) == {"msg": "a=b"}

    def test_empty_value(self) -> None:
        result = normalize_environment("msg=")
        assert result is not None
        assert json.loads(result) == {"msg": ""}

    def test_token_without_equals_raises(self) -> None:
        with pytest.raises(click.UsageError) as exc:
            normalize_environment("msgcoucou")
        assert "expected 'key=value'" in str(exc.value)

    def test_empty_key_raises(self) -> None:
        with pytest.raises(click.UsageError) as exc:
            normalize_environment("=coucou")
        assert "empty key" in str(exc.value)
