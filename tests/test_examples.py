"""The shipped examples must keep working, and their output must keep compiling."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import FPRIME_STUB_HEADERS, assert_compiles

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def load(name: str) -> ModuleType:
    """Import an example script by file name, without installing it as a package."""
    path = EXAMPLES / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_example_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ring_buffer_example_compiles() -> None:
    doc = load("ring_buffer").build()
    files = doc.files()
    assert set(files) == {"Ring.hpp", "Ring.cpp"}
    assert_compiles(files, stubs=FPRIME_STUB_HEADERS)


def test_ring_buffer_example_writes_files(tmp_path: Path) -> None:
    result = load("ring_buffer").build().write(tmp_path)
    assert sorted(p.name for p in result.written) == ["Ring.cpp", "Ring.hpp"]


@pytest.mark.parametrize("name", ["ring_buffer", "fpp_constants", "fpp_enum"])
def test_every_example_runs_as_a_script(name: str, tmp_path: Path) -> None:
    """Each example must work the way its own docstring says it does."""
    script = EXAMPLES / f"{name}.py"
    printed = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=60
    )
    assert printed.returncode == 0, printed.stderr
    assert "=====" in printed.stdout

    written = subprocess.run(
        [sys.executable, str(script), str(tmp_path / name)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert written.returncode == 0, written.stderr
    produced = sorted(p.name for p in (tmp_path / name).iterdir())
    assert len(produced) == 2 and produced[0].endswith(".cpp")
