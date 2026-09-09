"""Turning a document into files on disk.

Generators run inside build systems, so writing is conservative by default: a file
whose contents already match is left alone rather than rewritten, which keeps its
mtime stable and stops a no-op regeneration from cascading a rebuild through
everything downstream.  Pass ``skip_unchanged=False`` to always write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .doc import Class, ClassMember, CppDoc, Member, Namespace
from .writer import render_cpp, render_hpp

__all__ = ["WriteResult", "collect_cpp_files", "doc_files", "write_doc"]


@dataclass(frozen=True)
class WriteResult:
    """What :func:`write_doc` did."""

    written: list[Path] = field(default_factory=list)
    """Files created or updated."""

    unchanged: list[Path] = field(default_factory=list)
    """Files that already had the right contents and were left alone."""

    @property
    def all(self) -> list[Path]:
        """Every file the document owns, written or not, in generation order."""
        return sorted([*self.written, *self.unchanged])


def collect_cpp_files(doc: CppDoc) -> list[str]:
    """Find every supplemental source file ``doc`` assigns definitions to.

    Returns base names without extensions, in the order they first appear, and
    never the document's own default file.  This is what lets rendering discover
    its own outputs instead of relying on the caller to remember them -- forgetting
    one would silently drop every definition assigned to it.
    """
    default_base = doc.cpp_file_name.rsplit(".", 1)[0]
    found: list[str] = []

    def visit(members: Sequence[Member | ClassMember]) -> None:
        for m in members:
            base = getattr(m, "cpp_file", None)
            if base is not None and base != default_base and base not in found:
                found.append(base)
            if isinstance(m, (Class, Namespace)):
                visit(m.members)

    visit(doc.members)
    return found


def doc_files(doc: CppDoc, cpp_files: Sequence[str] | None = None) -> dict[str, str]:
    """Render a document to a mapping of file name to text.

    Always produces the header and the document's default source file.
    ``cpp_files`` names additional source files by base name, without extension;
    each gets only the definitions assigned to it.  Left as ``None``, the
    supplemental files are discovered from the document itself.
    """
    if cpp_files is None:
        cpp_files = collect_cpp_files(doc)
    out = {
        doc.hpp_file.name: render_hpp(doc),
        doc.cpp_file_name: render_cpp(doc),
    }
    for base in cpp_files:
        out[f"{base}.cpp"] = render_cpp(doc, base)
    return out


def write_doc(
    doc: CppDoc,
    directory: str | Path = ".",
    cpp_files: Sequence[str] | None = None,
    *,
    skip_unchanged: bool = True,
    encoding: str = "utf-8",
) -> WriteResult:
    """Write a document's header and source files into ``directory``.

    The directory is created if it does not exist.  See :func:`doc_files` for how
    ``cpp_files`` selects supplemental source files.
    """
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    unchanged: list[Path] = []
    for name, text in doc_files(doc, cpp_files).items():
        path = root / name
        if skip_unchanged and path.is_file() and path.read_text(encoding=encoding) == text:
            unchanged.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        written.append(path)
    return WriteResult(written, unchanged)
