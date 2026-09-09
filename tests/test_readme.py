"""The README's quick start must run, and must produce the output it claims.

Documented output rots quietly.  This extracts the snippet and the two C++ blocks
straight out of ``README.md``, runs the one, and compares against the others.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from .conftest import FPRIME_STUB_HEADERS, assert_compiles

README = Path(__file__).resolve().parent.parent / "README.md"

_FENCE = re.compile(r"^```(\w+)\n(.*?)^```$", re.MULTILINE | re.DOTALL)


def blocks(language: str) -> list[str]:
    """Every fenced code block in the README written in ``language``."""
    return [body for lang, body in _FENCE.findall(README.read_text()) if lang == language]


@pytest.fixture
def quick_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run the README's quick start and hand back the document it builds."""
    snippet = blocks("python")[0]
    assert "CppDocBuilder(" in snippet, "the first python block is not the quick start"
    # The snippet ends in doc.write(...), so run it somewhere disposable.
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, Any] = {}
    exec(compile(snippet, "README.md", "exec"), namespace)  # noqa: S102
    return namespace["doc"]


def test_quick_start_produces_the_documented_output(quick_start: Any) -> None:
    documented = blocks("cpp")[:2]
    assert len(documented) == 2, "expected the hpp and cpp blocks after the quick start"
    files = quick_start.files()
    assert files["Ring.hpp"] == documented[0]
    assert files["Ring.cpp"] == documented[1]


def test_quick_start_output_compiles(quick_start: Any) -> None:
    assert_compiles(quick_start.files(), stubs=FPRIME_STUB_HEADERS)


def test_quick_start_writes_where_it_says(tmp_path: Path, quick_start: Any) -> None:
    # monkeypatch.chdir put us in tmp_path, so the snippet's own write landed there.
    assert (tmp_path / "build-artifacts" / "Ring.hpp").is_file()
    assert (tmp_path / "build-artifacts" / "Ring.cpp").is_file()
