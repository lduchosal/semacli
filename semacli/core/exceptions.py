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
