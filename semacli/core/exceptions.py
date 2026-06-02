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
