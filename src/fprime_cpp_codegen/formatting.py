"""Passing generated files through an external formatter.

``clang-format`` is lexical: it needs no compilation database, include paths, or
working compiler, so generated text with missing includes and unknown types
formats fine.  It cannot tell a type name from a variable, so ``a * b;`` becomes
``a *b;``.

A formatter takes the file text and its name.  ``clang-format`` locates the
governing ``.clang-format`` by searching upward from the file's path, so the name
determines which project style applies.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .errors import CppCodegenError

__all__ = ["ClangFormat", "Formatter"]


@runtime_checkable
class Formatter(Protocol):
    """Post-processes one generated file's text."""

    def __call__(self, text: str, file_name: str) -> str:
        """Return ``text`` reformatted.  ``file_name`` is the name it is written as."""
        ...


@dataclass(frozen=True)
class ClangFormat:
    """Runs ``clang-format`` over generated text, through stdin and stdout::

        doc.write("build-artifacts", formatter=ClangFormat())

    With no ``style``, ``clang-format``'s default applies, which searches for a
    ``.clang-format`` upward from the generated file's directory.  ``style`` may be
    a named style such as ``"LLVM"`` or inline YAML like
    ``"{BasedOnStyle: LLVM, ColumnLimit: 120}"``.

    This reformats everything: a ``Ret Class ::`` line and its indented signature
    collapse onto one, and namespace bodies lose their indentation.
    """

    executable: str = "clang-format"
    style: str | None = None
    timeout: float = 30.0

    def available(self) -> bool:
        """Whether the executable can be found on ``PATH``."""
        return shutil.which(self.executable) is not None

    def version(self) -> str:
        """The formatter's version string."""
        return self._run(["--version"], text=None).strip()

    def __call__(self, text: str, file_name: str) -> str:
        """Return ``text`` as ``clang-format`` writes it for ``file_name``."""
        args = [f"--assume-filename={file_name}"]
        if self.style is not None:
            args.append(f"--style={self.style}")
        return self._run(args, text=text)

    def _run(self, args: list[str], *, text: str | None) -> str:
        try:
            result = subprocess.run(
                [self.executable, *args],
                input=text,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise CppCodegenError(
                f"{self.executable!r} was not found on PATH; install clang-format or "
                "pass a different executable to ClangFormat"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise CppCodegenError(
                f"{self.executable!r} did not finish within {self.timeout}s"
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit status {result.returncode}"
            raise CppCodegenError(f"{self.executable!r} failed: {detail}")
        return result.stdout
