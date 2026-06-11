"""Name-or-id resolution helpers (UX.md § 3).

These functions implement the rules in UX.md § 3.2:
- integer queries are returned as-is (no lookup),
- string queries match by case-insensitive substring within the project,
- an exact match wins over fuzzy matches when both are present,
- 0 matches raises NotFoundError, N-non-exact matches raises
  AmbiguousNameError.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from .exceptions import AmbiguousNameError, NotFoundError

if TYPE_CHECKING:
    from .client import SemaphoreClient


class _Named(Protocol):
    id: int
    name: str


def _match_id_or_name(query: str, items: Sequence[_Named], kind: str, exact: bool) -> int:
    if query.isdigit():
        return int(query)

    q = query.casefold()

    exact_hits = [it for it in items if it.name.casefold() == q]
    if exact_hits:
        return exact_hits[0].id
    if exact:
        raise NotFoundError(f"no {kind} matching '{query}' (with --exact)")

    fuzzy = [it for it in items if q in it.name.casefold()]
    if not fuzzy:
        raise NotFoundError(f"no {kind} matching '{query}'")
    if len(fuzzy) == 1:
        return fuzzy[0].id

    raise AmbiguousNameError(query, [(it.id, it.name) for it in fuzzy])


def resolve_template(
    client: "SemaphoreClient", pid: int, query: str, *, exact: bool = False
) -> int:
    """Resolve a template name (or id) to a numeric template id."""
    items = client.get_templates(pid)
    return _match_id_or_name(query, items, "template", exact)
