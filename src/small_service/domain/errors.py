"""Named errors of the domain."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every error the domain raises on purpose."""


class InvalidTtlError(DomainError, ValueError):
    """A cache time-to-live must be a positive number of seconds."""


class InvalidJobKeyError(DomainError, ValueError):
    """A job key must be 1 to 64 characters from letters, digits, dot, dash and underscore."""


class JobNotStartedError(DomainError, RuntimeError):
    """`Job.wait` was called before `Job.start`."""
