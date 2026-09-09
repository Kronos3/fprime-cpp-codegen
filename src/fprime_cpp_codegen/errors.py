"""The exception hierarchy.

Everything raised here derives from :class:`CppCodegenError`, so a generator can
catch one type.
"""

from __future__ import annotations

__all__ = ["CppCodegenError", "ScopeError", "ValidationError"]


class CppCodegenError(Exception):
    """Base class for every error raised here."""


class ScopeError(CppCodegenError):
    """A builder scope was used in a way its structure does not allow.

    ``else`` with no preceding ``if``, a ``case`` outside a ``switch``, building a body
    with a scope still open.
    """


class ValidationError(CppCodegenError):
    """A document or declaration is malformed and could not produce valid C++."""
