"""Tests for optional post-processing of generated files."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fprime_cpp_codegen import ClangFormat, CppDocBuilder, CppCodegenError, Output

CLANG_FORMAT = ClangFormat()
needs_clang_format = pytest.mark.skipif(
    not CLANG_FORMAT.available(), reason="clang-format not on PATH"
)


def build() -> CppDocBuilder:
    """A document with a header, a default source file, and a supplemental one."""
    doc = CppDocBuilder("Ring", description="a ring")
    doc.include("Ring.hpp", output=Output.CPP)
    with doc.class_("Ring") as cls:
        with cls.public():
            cls.function("push", ret="bool", body="return true;")
            with doc.cpp_file("RingHelpers"):
                cls.function("rebalance", body="tidy();")
    return doc


class Recorder:
    """A formatter that records what it was handed and marks the text."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def __call__(self, text: str, file_name: str) -> str:
        self.seen.append((file_name, text))
        return f"// formatted {file_name}\n{text}"

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.seen]


class TestPlumbing:
    def test_files_are_formatted_and_get_their_own_names(self) -> None:
        recorder = Recorder()
        files = build().files(formatter=recorder)
        assert sorted(recorder.names) == ["Ring.cpp", "Ring.hpp", "RingHelpers.cpp"]
        for name, text in files.items():
            assert text.startswith(f"// formatted {name}\n")

    def test_render_hpp_and_render_cpp_pass_the_right_name(self) -> None:
        recorder = Recorder()
        doc = build()
        doc.render_hpp(formatter=recorder)
        doc.render_cpp(formatter=recorder)
        doc.render_cpp("RingHelpers", formatter=recorder)
        assert recorder.names == ["Ring.hpp", "Ring.cpp", "RingHelpers.cpp"]

    def test_write_formats_before_writing(self, tmp_path: Path) -> None:
        build().write(tmp_path, formatter=Recorder())
        assert (tmp_path / "Ring.hpp").read_text().startswith("// formatted Ring.hpp")

    def test_a_document_level_formatter_applies_to_everything(self) -> None:
        recorder = Recorder()
        doc = build()
        doc.formatter = recorder
        doc.render_hpp()
        doc.files()
        assert recorder.names.count("Ring.hpp") == 2

    def test_a_call_argument_overrides_the_document_formatter(self) -> None:
        doc_level, call_level = Recorder(), Recorder()
        doc = build()
        doc.formatter = doc_level
        doc.render_hpp(formatter=call_level)
        assert call_level.names == ["Ring.hpp"]
        assert doc_level.names == []

    def test_formatting_can_be_set_at_construction(self) -> None:
        recorder = Recorder()
        doc = CppDocBuilder("A", formatter=recorder)
        doc.class_("A")
        doc.render_hpp()
        assert recorder.names == ["A.hpp"]

    def test_no_formatter_leaves_the_text_alone(self) -> None:
        assert build().render_hpp().startswith("// ======")

    def test_the_unchanged_check_compares_formatted_text(self, tmp_path: Path) -> None:
        # Otherwise every run would rewrite every file, since what is on disk is
        # formatted and what was just rendered is not.
        recorder = Recorder()
        build().write(tmp_path, formatter=recorder)
        again = build().write(tmp_path, formatter=recorder)
        assert again.written == []
        assert len(again.unchanged) == 3


@needs_clang_format
class TestClangFormat:
    def test_it_needs_no_compilation_context(self) -> None:
        # No includes, no compile_commands.json, no types it has heard of.
        source = (
            '#include "DoesNotExist.hpp"\n'
            "namespace N{class C:public Totally::Unknown<Base>{\n"
            "public:C(UnknownType x):m_x(x){}\nprivate:UnknownType m_x;};}\n"
        )
        result = CLANG_FORMAT(source, "C.hpp")
        assert "namespace N {" in result
        assert "class C : public Totally::Unknown<Base> {" in result

    def test_it_formats_a_generated_document(self) -> None:
        formatted = build().render_cpp(formatter=CLANG_FORMAT)
        assert "bool Ring ::push()" in formatted or "bool Ring::push()" in formatted
        assert formatted.endswith("\n")

    def test_an_explicit_style_is_honoured(self) -> None:
        narrow = ClangFormat(style="{BasedOnStyle: LLVM, ColumnLimit: 30}")
        long_call = "void f() { someCall(aaaaaaa, bbbbbbb, ccccccc, ddddddd); }\n"
        assert len(narrow(long_call, "x.cpp").splitlines()) > 1

    def test_the_file_name_selects_the_governing_config(self, tmp_path: Path) -> None:
        # clang-format searches upward from the file's path, so the name is what
        # lets a project's own .clang-format apply.
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / ".clang-format").write_text(
            "BasedOnStyle: LLVM\nColumnLimit: 20\n"
        )
        source = "void aVeryLongFunctionName(int aaa, int bbb, int ccc);\n"
        outside = CLANG_FORMAT(source, str(tmp_path / "probe.cpp"))
        inside = CLANG_FORMAT(source, str(tmp_path / "nested" / "probe.cpp"))
        assert len(outside.splitlines()) == 1
        assert len(inside.splitlines()) > 1

    def test_version_reports_something(self) -> None:
        assert "clang-format" in CLANG_FORMAT.version()

    def test_a_failure_is_reported_as_a_codegen_error(self) -> None:
        with pytest.raises(CppCodegenError, match="failed"):
            ClangFormat(style="NotAStyle")("int x;\n", "x.cpp")


class TestClangFormatErrors:
    def test_a_missing_executable_says_so(self) -> None:
        formatter = ClangFormat(executable="definitely-not-a-real-formatter")
        assert not formatter.available()
        with pytest.raises(CppCodegenError, match="not found on PATH"):
            formatter("int x;\n", "x.cpp")

    def test_available_reflects_path(self) -> None:
        assert ClangFormat().available() == (shutil.which("clang-format") is not None)
