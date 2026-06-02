"""Tests for semacli.core.exceptions."""

import pytest

from semacli.core.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NotFoundError,
    SemaCliError,
    SemaphoreAPIError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self) -> None:
        for cls in (
            ConfigurationError,
            AuthenticationError,
            SemaphoreAPIError,
            NotFoundError,
        ):
            assert issubclass(cls, SemaCliError)
            assert issubclass(cls, Exception)

    def test_can_raise_and_catch_as_base(self) -> None:
        with pytest.raises(SemaCliError):
            raise ConfigurationError("nope")
        with pytest.raises(SemaCliError):
            raise AuthenticationError("nope")
        with pytest.raises(SemaCliError):
            raise SemaphoreAPIError("nope")
        with pytest.raises(SemaCliError):
            raise NotFoundError("nope")

    def test_carries_message(self) -> None:
        e = ConfigurationError("missing url")
        assert str(e) == "missing url"
