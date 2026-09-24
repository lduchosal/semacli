"""Custom exceptions for semacli."""


class SemaCliError(Exception):
    """Base exception for semacli."""

    pass


class ConfigurationError(SemaCliError):
    """Raised when there's a configuration error."""

    pass


class AuthenticationError(SemaCliError):
    """Raised when there's an authentication error."""

    pass


class SemaphoreAPIError(SemaCliError):
    """Raised when there's an error with the Semaphore API."""

    pass


class NotFoundError(SemaCliError):
    """Raised when a resource is not found."""

    pass


class HookError(SemaCliError):
    """Raised when a configured hook fails (non-zero exit or timeout)."""

    pass


class OverrideNotAllowedError(SemaCliError):
    """Raised when a per-run override flag (--limit, --tags, ...) is not
    permitted by the target template.

    Semaphore does not reject forbidden overrides — it silently drops
    them, so e.g. a refused ``--limit`` runs the playbook on the FULL
    inventory. semacli fails closed instead (ken #827).
    """

    def __init__(self, template_name: str, flag: str, toggle: str, consequence: str) -> None:
        self.template_name = template_name
        self.flag = flag
        self.toggle = toggle
        super().__init__(
            f"template '{template_name}' does not allow {flag} ({toggle}=false). "
            f"Semaphore would silently drop the flag and {consequence}. "
            f"Fix the template (or drop {flag}). Refusing to run."
        )


class AmbiguousNameError(SemaCliError):
    """Raised when a name resolves to more than one object and no exact
    match wins. Carries the candidate list so the caller can show it.
    """

    def __init__(self, query: str, candidates: list[tuple[int, str]]) -> None:
        self.query = query
        self.candidates = candidates
        rows = "\n".join(f"  {cid:>4}  {name}" for cid, name in candidates)
        super().__init__(
            f"ambiguous '{query}' — {len(candidates)} candidates:\n{rows}\n"
            "hint: use a more specific name, or pass --exact."
        )


class InvalidArgumentsError(SemaCliError):
    """Raised when ``--arguments`` is not a plain JSON array of static flags.

    Semaphore stores ``arguments`` verbatim and hands them to
    ansible-playbook without any templating pass. A ``{{ limit }}``
    placeholder therefore reaches ansible as a literal host pattern
    (ken #636), which silently matches nothing — or the wrong hosts.
    """

    def __init__(self, reason: str, value: str) -> None:
        self.reason = reason
        self.value = value
        super().__init__(
            f"invalid --arguments: {reason}. "
            f"Expected a JSON array of static flags, e.g. '[\"--diff\"]'. Got: {value!r}"
        )


class InvalidOverrideSpecError(SemaCliError):
    """Raised when an ``--allow-override`` spec names an unknown toggle."""

    def __init__(self, unknown: list[str], known: list[str]) -> None:
        self.unknown = unknown
        super().__init__(
            f"unknown override(s): {', '.join(unknown)}. "
            f"Known: {', '.join(known)} (or 'all' / 'none')."
        )


class ManifestError(SemaCliError):
    """Raised when a sync manifest is unreadable or structurally invalid."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        super().__init__(f"manifest {path}: {reason}")
