"""The README's quick start must actually run, and its output must compile.

Documented code rots quietly.  This extracts the snippet straight out of
``README.md`` and executes it, so a change to the API that invalidates the README
fails here rather than in front of a reader.
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


def test_quick_start_produces_the_two_files(quick_start: Any) -> None:
    assert set(quick_start.files()) == {"Ring.hpp", "Ring.cpp"}


def test_quick_start_splits_declarations_from_definitions(quick_start: Any) -> None:
    hpp, cpp = quick_start.render_hpp(), quick_start.render_cpp()
    assert "Ring(" in hpp and "bool push(" in hpp
    # The inline accessor is defined in the header; push is defined in the source.
    assert "return m_size;" in hpp and "return m_size;" not in cpp
    assert "return true;" in cpp and "return true;" not in hpp


def test_quick_start_output_compiles(quick_start: Any) -> None:
    assert_compiles(quick_start.files(), stubs=FPRIME_STUB_HEADERS)


def test_quick_start_writes_where_it_says(tmp_path: Path, quick_start: Any) -> None:
    # monkeypatch.chdir put us in tmp_path, so the snippet's own write landed there.
    assert (tmp_path / "build-artifacts" / "Ring.hpp").is_file()
    assert (tmp_path / "build-artifacts" / "Ring.cpp").is_file()


def test_every_referenced_example_exists() -> None:
    """Every ``examples/...`` link in the README must point at a real file."""
    root = README.parent
    referenced = set(re.findall(r"\((examples/[\w./-]+)\)", README.read_text()))
    referenced |= set(re.findall(r"python (examples/[\w./-]+)", README.read_text()))
    assert referenced, "expected the README to point at the examples"
    missing = sorted(p for p in referenced if not (root / p).exists())
    assert not missing, f"README points at files that do not exist: {missing}"
