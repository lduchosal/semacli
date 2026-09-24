"""Per-template override toggles (Semaphore ``task_params``).

One vocabulary shared by ``template create`` / ``update`` / ``sync``
(the ``--allow-override`` spec), by the run-time guard and by the
audit command: the cli speaks ansible ("limit", "skip-tags"), the API
speaks Go struct fields ("allow_override_limit", "allow_debug").
"""

from collections.abc import Sequence

from .exceptions import InvalidOverrideSpecError

# cli word -> task_params field. Order is the display order.
OVERRIDE_TOGGLES: dict[str, str] = {
    "limit": "allow_override_limit",
    "tags": "allow_override_tags",
    "skip-tags": "allow_override_skip_tags",
    "inventory": "allow_override_inventory",
    "debug": "allow_debug",
}

ALL_OVERRIDES = "all"
NO_OVERRIDES = "none"


def _wanted(spec: str | Sequence[str]) -> set[str]:
    """Normalise a spec into the set of cli words it enables."""
    words = spec.split(",") if isinstance(spec, str) else list(spec)
    wanted = {w.strip().lower() for w in words if w.strip()}
    if ALL_OVERRIDES in wanted:
        return set(OVERRIDE_TOGGLES)
    if NO_OVERRIDES in wanted:
        return set()
    unknown = sorted(wanted - set(OVERRIDE_TOGGLES))
    if unknown:
        raise InvalidOverrideSpecError(unknown, list(OVERRIDE_TOGGLES))
    return wanted


def parse_allow_override(spec: str | Sequence[str] | None) -> dict[str, bool] | None:
    """Turn an ``--allow-override`` spec into a ``task_params`` payload.

    ``"limit,tags"`` enables those two and disables the rest; ``"all"``
    and ``"none"`` are the shorthands; ``None`` means "caller did not
    ask", so the field is left untouched (read-modify-write on update).
    """
    if spec is None:
        return None
    wanted = _wanted(spec)
    return {field: (word in wanted) for word, field in OVERRIDE_TOGGLES.items()}


def permissive_task_params() -> dict[str, bool]:
    """Every override allowed — the create default (ken #826)."""
    return dict.fromkeys(OVERRIDE_TOGGLES.values(), True)


def allowed_words(task_params: dict[str, bool]) -> list[str]:
    """List the cli words a ``task_params`` payload actually allows."""
    return [word for word, field in OVERRIDE_TOGGLES.items() if task_params.get(field)]


def missing_words(task_params: dict[str, bool], required: Sequence[str]) -> list[str]:
    """List the required cli words a ``task_params`` payload forbids."""
    return [word for word in required if not task_params.get(OVERRIDE_TOGGLES[word])]
