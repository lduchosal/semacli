"""Shared unit-test fixtures."""

import io

import pytest


@pytest.fixture
def cp1252_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every text read without ``encoding=`` decode as cp1252.

    Reproduces Windows with ``PYTHONUTF8=0`` (ken #1122): ``Path.read_text``
    and ``ConfigParser.read`` resolve a missing encoding via
    ``io.text_encoding``, so a UTF-8 ``é`` would come back as ``Ã©``.
    """
    monkeypatch.setattr(io, "text_encoding", lambda encoding, _stacklevel=2: encoding or "cp1252")
