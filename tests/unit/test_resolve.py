"""Tests for the name-or-id resolution helpers (UX.md § 3.2)."""

from unittest.mock import Mock

import pytest

from semacli.core.exceptions import AmbiguousNameError, NotFoundError
from semacli.core.resolve import _match_id_or_name, resolve_inventory


class _Item:
    def __init__(self, id_: int, name: str) -> None:
        self.id = id_
        self.name = name


_ITEMS = [_Item(1, "mtree"), _Item(2, "mtreeremove"), _Item(3, "Echo")]


class TestResolveInventory:
    def test_resolves_name_via_list(self) -> None:
        client = Mock()
        client.list_inventories.return_value = [_Item(4, "prod"), _Item(5, "staging")]
        assert resolve_inventory(client, 1, "prod") == 4
        client.list_inventories.assert_called_once_with(1)


class TestMatchIdOrName:
    def test_digit_passes_through_without_lookup(self) -> None:
        assert _match_id_or_name("42", [], "template", exact=False) == 42

    def test_exact_match_wins_over_fuzzy(self) -> None:
        assert _match_id_or_name("mtree", _ITEMS, "template", exact=False) == 1

    def test_exact_match_is_case_insensitive(self) -> None:
        assert _match_id_or_name("echo", _ITEMS, "template", exact=False) == 3

    def test_single_fuzzy_match_resolves(self) -> None:
        assert _match_id_or_name("remove", _ITEMS, "template", exact=False) == 2

    def test_no_match_raises_not_found(self) -> None:
        with pytest.raises(NotFoundError, match="no template matching 'nope'"):
            _match_id_or_name("nope", _ITEMS, "template", exact=False)

    def test_exact_flag_refuses_fuzzy(self) -> None:
        with pytest.raises(NotFoundError, match="with --exact"):
            _match_id_or_name("remove", _ITEMS, "template", exact=True)

    def test_ambiguous_fuzzy_raises(self) -> None:
        with pytest.raises(AmbiguousNameError):
            _match_id_or_name("tree", _ITEMS, "template", exact=False)
