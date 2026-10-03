"""Explicit expected errors at the application boundary."""


class NotFoundError(KeyError):
    """A requested resource is absent, rather than an unexpected missing dictionary key."""


class AccessDeniedError(PermissionError):
    """An explicit request access rejection, rather than a filesystem failure."""
