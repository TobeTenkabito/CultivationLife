"""Explicit expected errors at the application boundary."""


class NotFoundError(KeyError):
    """A requested resource is absent, rather than an unexpected missing dictionary key."""


class AccessDeniedError(PermissionError):
    """An explicit request access rejection, rather than a filesystem failure."""


class ContentError(ValueError):
    """内容包格式或跨表引用不合法。"""


class MetadataReadError(RuntimeError):
    """Existing account metadata could not be read safely; never overwrite it."""
