"""The builder protocol and the state shared across one document."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, Sequence, TypeVar

from ..body import Code

_T = TypeVar("_T")
_T2 = TypeVar("_T2")

#: What a body-shaped argument accepts.  See :data:`fprime_cpp_codegen.body.Code`.
BodyLike = Code


class _Builder(ABC, Generic[_T]):
    """Something that turns into an IR node when the document is built."""

    @abstractmethod
    def build(self) -> _T:
        """Produce the IR node.  Safe to call more than once."""

    def build_members(self) -> list[Any]:
        """The IR members this builder contributes, in order.

        Decoration repeated per output file -- a banner, a preprocessor guard --
        overrides this to contribute several members at once.
        """
        return [self.build()]


def _resolve(items: Sequence[object]) -> list[Any]:
    """Turn a mixed list of IR nodes and builders into IR nodes, preserving order."""
    out: list[Any] = []
    for item in items:
        if isinstance(item, _Builder):
            out.extend(item.build_members())
        else:
            out.append(item)
    return out


@dataclass
class _DocContext:
    """State shared by every builder in one document."""

    cpp_files: list[str | None] = field(default_factory=lambda: [None])

    @property
    def cpp_file(self) -> str | None:
        """The source file definitions currently default to."""
        return self.cpp_files[-1]
