"""The document scope: one header plus one or more source files, and their output."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from ..doc import CppDoc, FileBanner, HppFile
from ..errors import ValidationError
from ..formatting import Formatter
from ..output import WriteResult, doc_files, write_doc
from ..writer import render_cpp, render_hpp
from .base import _DocContext
from .scopes import _MemberScope


class CppDocBuilder(_MemberScope[CppDoc]):
    """A whole C++ document: one header and one or more source files."""

    def __init__(
        self,
        file_base: str,
        *,
        description: str | None = None,
        include_guard: str | None = None,
        namespaces: Sequence[str] = (),
        tool_name: str | None = None,
        file_banner: FileBanner | None = None,
        formatter: Formatter | None = None,
        hpp_extension: str = "hpp",
        cpp_extension: str = "cpp",
    ) -> None:
        """Start a document whose files are named after ``file_base``.

        ``include_guard`` defaults to one derived from ``file_base`` and
        ``namespaces``; ``namespaces`` is used for nothing else, so pass it when you
        want ``Fw_Cfg_MyClass_HPP`` without spelling the macro out.

        ``formatter`` post-processes every file this document renders; see
        :mod:`fprime_cpp_codegen.formatting`.  Any render or write call can override
        it, but cannot switch it off.
        """
        super().__init__(_DocContext())
        if not file_base:
            raise ValidationError("a document needs a file name base")
        self.file_base = file_base
        self.description = description if description is not None else file_base
        self.hpp_extension = hpp_extension
        self.cpp_extension = cpp_extension
        self.tool_name = tool_name
        self.formatter = formatter
        """Applied to every file this document renders, unless a call overrides it."""

        self.file_banner = file_banner
        """Overrides the ``\\title``/``\\author``/``\\brief`` block atop each file.
        Distinct from :meth:`banner`, which emits a section comment."""

        self.include_guard = (
            include_guard
            if include_guard is not None
            else _default_guard(file_base, namespaces, hpp_extension)
        )

    @property
    def hpp_name(self) -> str:
        """The header file name, e.g. ``"MyClass.hpp"``."""
        return f"{self.file_base}.{self.hpp_extension}"

    @property
    def cpp_name(self) -> str:
        """The default source file name, e.g. ``"MyClass.cpp"``."""
        return f"{self.file_base}.{self.cpp_extension}"

    def build(self) -> CppDoc:
        return CppDoc(
            description=self.description,
            hpp_file=HppFile(self.hpp_name, self.include_guard),
            cpp_file_name=self.cpp_name,
            members=self._built_members(),
            tool_name=self.tool_name,
            banner=self.file_banner,
        )

    # -- output -------------------------------------------------------

    def _formatter(self, override: Formatter | None) -> Formatter | None:
        return override if override is not None else self.formatter

    def render_hpp(self, *, formatter: Formatter | None = None) -> str:
        """Render the header as text."""
        text = render_hpp(self.build())
        chosen = self._formatter(formatter)
        return chosen(text, self.hpp_name) if chosen else text

    def render_cpp(
        self, cpp_file: str | None = None, *, formatter: Formatter | None = None
    ) -> str:
        """Render one source file as text.  ``None`` selects the default one."""
        text = render_cpp(self.build(), cpp_file)
        chosen = self._formatter(formatter)
        if not chosen:
            return text
        name = f"{cpp_file}.{self.cpp_extension}" if cpp_file else self.cpp_name
        return chosen(text, name)

    def files(
        self,
        cpp_files: Sequence[str] | None = None,
        *,
        formatter: Formatter | None = None,
    ) -> dict[str, str]:
        """Render every file this document owns, as a name-to-text mapping."""
        return doc_files(self.build(), cpp_files, formatter=self._formatter(formatter))

    def write(
        self,
        directory: str | Path = ".",
        cpp_files: Sequence[str] | None = None,
        *,
        formatter: Formatter | None = None,
        skip_unchanged: bool = True,
        encoding: str = "utf-8",
    ) -> WriteResult:
        """Write every file this document owns into ``directory``.

        Supplemental source files are discovered automatically.
        """
        return write_doc(
            self.build(),
            directory,
            cpp_files,
            formatter=self._formatter(formatter),
            skip_unchanged=skip_unchanged,
            encoding=encoding,
        )

    def __enter__(self) -> CppDocBuilder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _default_guard(
    file_base: str, namespaces: Sequence[str], hpp_extension: str
) -> str:
    """Derive an include-guard macro from the file base, namespaces and extension.

    ``_default_guard("MyClass", ["Fw", "Cfg"], "hpp")`` gives ``"Fw_Cfg_MyClass_HPP"``.
    Namespace arguments may themselves be qualified with ``::`` or ``.``.
    """
    parts = [part for ns in namespaces for part in re.split(r"::|\.", ns) if part]
    ident = re.sub(r"[^A-Za-z0-9_]+", "_", "_".join([*parts, file_base])).strip("_")
    return f"{ident}_{hpp_extension.upper()}"
