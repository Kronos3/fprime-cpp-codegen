"""Tests for rendering a document to files on disk."""

from __future__ import annotations

from pathlib import Path

from fprime_cpp_codegen.doc import Class, CppDoc, Function, HppFile, Lines, Output
from fprime_cpp_codegen.lines import line, lines
from fprime_cpp_codegen.output import collect_cpp_files, doc_files, write_doc


def build_doc() -> CppDoc:
    return CppDoc(
        description="output test",
        hpp_file=HppFile("A.hpp", "A_HPP"),
        cpp_file_name="A.cpp",
        members=[
            Lines(lines('#include "A.hpp"'), Output.CPP),
            Lines(lines('#include "A.hpp"'), Output.CPP, cpp_file="Extra"),
            Class(
                "A",
                members=[
                    Function("here", body=[line("a();")]),
                    Function("there", body=[line("b();")], cpp_file="Extra"),
                ],
            ),
        ],
    )


class TestCollectCppFiles:
    def test_supplemental_files_are_discovered(self) -> None:
        assert collect_cpp_files(build_doc()) == ["Extra"]

    def test_the_default_file_is_not_reported_as_supplemental(self) -> None:
        doc = CppDoc(
            description="d",
            hpp_file=HppFile("A.hpp", "A_HPP"),
            cpp_file_name="A.cpp",
            members=[Class("A", members=[Function("f", body=[line("x();")], cpp_file="A")])],
        )
        assert collect_cpp_files(doc) == []

    def test_nothing_to_discover(self) -> None:
        doc = CppDoc(
            description="d",
            hpp_file=HppFile("A.hpp", "A_HPP"),
            cpp_file_name="A.cpp",
            members=[Class("A", members=[Function("f", body=[line("x();")])])],
        )
        assert collect_cpp_files(doc) == []


class TestDocFiles:
    def test_supplemental_source_files_are_discovered_by_default(self) -> None:
        # Forgetting to name a supplemental file would silently drop every
        # definition assigned to it, so discovery is the default.
        assert set(doc_files(build_doc())) == {"A.hpp", "A.cpp", "Extra.cpp"}

    def test_discovery_can_be_suppressed_with_an_explicit_list(self) -> None:
        assert set(doc_files(build_doc(), [])) == {"A.hpp", "A.cpp"}

    def test_supplemental_source_files_are_named_by_base(self) -> None:
        files = doc_files(build_doc(), ["Extra"])
        assert set(files) == {"A.hpp", "A.cpp", "Extra.cpp"}
        assert "a();" in files["A.cpp"] and "b();" not in files["A.cpp"]
        assert "b();" in files["Extra.cpp"] and "a();" not in files["Extra.cpp"]

    def test_every_file_ends_with_a_newline(self) -> None:
        for text in doc_files(build_doc(), ["Extra"]).values():
            assert text.endswith("\n")


class TestWriteDoc:
    def test_writes_the_expected_files(self, tmp_path: Path) -> None:
        result = write_doc(build_doc(), tmp_path)
        assert sorted(p.name for p in result.written) == ["A.cpp", "A.hpp", "Extra.cpp"]
        assert result.unchanged == []
        assert (tmp_path / "A.hpp").read_text().startswith("// =====")

    def test_creates_the_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "gen"
        write_doc(build_doc(), target)
        assert (target / "A.hpp").is_file()

    def test_a_second_identical_run_touches_nothing(self, tmp_path: Path) -> None:
        # Build systems key off mtimes, so a no-op regeneration must not cascade
        # a rebuild through everything downstream.
        write_doc(build_doc(), tmp_path, ["Extra"])
        before = {p: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
        result = write_doc(build_doc(), tmp_path, ["Extra"])
        assert result.written == []
        assert len(result.unchanged) == 3
        assert {p: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == before

    def test_changed_content_is_rewritten(self, tmp_path: Path) -> None:
        write_doc(build_doc(), tmp_path)
        (tmp_path / "A.cpp").write_text("stale\n")
        result = write_doc(build_doc(), tmp_path)
        assert [p.name for p in result.written] == ["A.cpp"]
        assert "stale" not in (tmp_path / "A.cpp").read_text()

    def test_skip_unchanged_can_be_turned_off(self, tmp_path: Path) -> None:
        write_doc(build_doc(), tmp_path)
        result = write_doc(build_doc(), tmp_path, skip_unchanged=False)
        assert len(result.written) == 3
        assert result.unchanged == []

    def test_all_lists_every_file(self, tmp_path: Path) -> None:
        write_doc(build_doc(), tmp_path)
        result = write_doc(build_doc(), tmp_path, ["Extra"])
        assert sorted(p.name for p in result.all) == ["A.cpp", "A.hpp", "Extra.cpp"]
