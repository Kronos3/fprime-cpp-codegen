"""The exception hierarchy.

Everything this package raises on its own derives from :class:`CppCodegenError`,
so a generator can catch that one type and report a useful message rather than
letting a stray ``AttributeError`` escape.
"""

from __future__ import annotations

__all__ = ["CppCodegenError", "ScopeError", "ValidationError"]


class CppCodegenError(Exception):
    """Base class for every error raised by this package."""


class ScopeError(CppCodegenError):
    """A builder scope was used in a way its structure does not allow.

    Raised for things like ``else`` with no preceding ``if``, a ``case`` outside a
    ``switch``, adding members to a scope that has already been closed, or
    re-entering a scope that is already open.
    """


class ValidationError(CppCodegenError):
    """A document or declaration is malformed and could not produce valid C++."""
