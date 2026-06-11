"""Vulture whitelist — false positives, referenced here so vulture sees a use.

Parsed (never executed) by `pdm run vulture` / scripts/quality_metrics.py.
"""

cls  # pydantic @model_validator(mode="before") classmethod signature (core/models.py)
skip_if_no_cassette  # pytest fixture requested by name in tests/integration/*
