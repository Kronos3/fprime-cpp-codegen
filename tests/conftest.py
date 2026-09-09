"""Shared test fixtures and helpers."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import pytest

GOLDENS = Path(__file__).parent / "goldens"


def read_golden(name: str) -> str:
    """Read a golden file's text."""
    return (GOLDENS / name).read_text()


def assert_matches_golden(text: str, name: str) -> None:
    """Assert generated text is byte-identical to the named golden file."""
    expected = read_golden(name)
    if text != expected:
        import difflib

        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                text.splitlines(),
                fromfile=f"goldens/{name}",
                tofile=f"generated/{name}",
                lineterm="",
            )
        )
        pytest.fail(f"{name} does not match golden:\n\n{diff}")


def _compiler() -> str | None:
    for candidate in ("g++", "clang++", "c++"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


#: Enough of the F Prime basic types to compile generated code that includes them.
FPRIME_STUB_HEADERS = {
    "Fw/FPrimeBasicTypes.hpp": (
        "#ifndef FW_FPRIME_BASIC_TYPES_HPP\n"
        "#define FW_FPRIME_BASIC_TYPES_HPP\n"
        "typedef unsigned char U8;\n"
        "typedef unsigned short U16;\n"
        "typedef unsigned int U32;\n"
        "typedef signed int I32;\n"
        "typedef float F32;\n"
        "typedef double F64;\n"
        "typedef unsigned long FwSizeType;\n"
        "#endif\n"
    ),
}


def assert_compiles(
    files: dict[str, str],
    *,
    stubs: dict[str, str] | None = None,
    defines: Sequence[str] = (),
) -> None:
    """Compile the given C++ sources, skipping the test if no compiler is present.

    ``stubs`` supplies extra headers to place alongside them, for generated code that
    includes headers the test environment does not have.  ``defines`` are passed as
    ``-D`` flags, without which code inside a ``#if`` guard is never compiled.
    """
    cxx = _compiler()
    if cxx is None:
        pytest.skip("no C++ compiler found")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, text in {**(stubs or {}), **files}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        sources = [name for name in files if name.endswith(".cpp")]
        flags = [f"-D{d}" for d in defines]
        result = subprocess.run(
            [cxx, "-std=c++14", "-Wall", "-Wextra", "-fsyntax-only", *flags, *sources],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            result.returncode == 0
        ), f"{cxx} {' '.join(flags)} failed:\n{result.stderr}\n\n" + "\n\n".join(
            f"=== {n} ===\n{t}" for n, t in files.items()
        )
