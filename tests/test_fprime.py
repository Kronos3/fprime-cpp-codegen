"""Tests for the optional F Prime idiom layer."""

from __future__ import annotations

from typing import Sequence

from fprime_cpp_codegen import fprime
from fprime_cpp_codegen.doc import Class, Lines, Output
from fprime_cpp_codegen.lines import Line, line, render


def text(ll: Sequence[Line]) -> str:
    return render(ll)


class TestStandardHeaders:
    def test_hpp_headers_are_quoted_includes(self) -> None:
        assert '#include "Fw/FPrimeBasicTypes.hpp"' in fprime.STANDARD_USER_HPP_HEADERS
        assert all(h.startswith("#include") for h in fprime.STANDARD_USER_HPP_HEADERS)

    def test_cpp_headers_bring_in_assert(self) -> None:
        assert fprime.STANDARD_USER_CPP_HEADERS == ['#include "Fw/Types/Assert.hpp"']


class TestAssert:
    def test_bare_assert(self) -> None:
        assert text(fprime.write_assert("ptr != nullptr")) == "FW_ASSERT(ptr != nullptr);\n"

    def test_assert_reports_its_values(self) -> None:
        # The reported values are what makes a flight-side assert diagnosable.
        assert text(fprime.write_assert("i < n", "i", "n")) == "FW_ASSERT(i < n, i, n);\n"


class TestExternalString:
    def test_buffer_name_is_namespaced_to_the_autocoder(self) -> None:
        assert fprime.buffer_name("msg") == "__fprime_ac_msg_buffer"

    def test_declaration_is_a_fixed_buffer_plus_a_view(self) -> None:
        # No dynamic memory: a string local is an array plus a view onto it.
        assert text(fprime.external_string_decl("msg", "80")) == (
            "char __fprime_ac_msg_buffer[Fw::StringBase::BUFFER_SIZE(80)];\n"
            "Fw::ExternalString msg(__fprime_ac_msg_buffer, "
            "sizeof __fprime_ac_msg_buffer);\n"
        )


class TestGuards:
    def test_text_log_guard_brackets_members(self) -> None:
        members = fprime.guard_class_members_for_text_log([Lines([line("void f();")])])
        assert len(members) == 3
        first = members[0]
        assert isinstance(first, Lines)
        assert "#if FW_ENABLE_TEXT_LOGGING" in text(first.content)

    def test_unit_test_guard_uses_ifdef(self) -> None:
        members = fprime.guard_members_for_unit_test([Class("C")])
        first = members[0]
        assert isinstance(first, Lines)
        assert "#ifdef BUILD_UT" in text(first.content)

    def test_empty_guards_vanish(self) -> None:
        assert fprime.guard_class_members_for_text_log([]) == []
        assert fprime.guard_members_for_text_log([]) == []
        assert fprime.guard_class_members_for_unit_test([]) == []
        assert fprime.guard_members_for_unit_test([]) == []


class TestOstreamOperator:
    def test_declaration_goes_to_the_header_and_definition_to_the_source(self) -> None:
        members = fprime.write_ostream_operator("MyType", [line("return os;")])
        # Opening guard, declaration, definition, closing guard.
        assert len(members) == 4
        bodies = [m for m in members if isinstance(m, Lines)]
        declaration = bodies[1]
        definition = bodies[2]
        assert declaration.output is Output.HPP
        assert "friend std::ostream& operator<<(" in text(declaration.content)
        assert definition.output is Output.CPP
        assert "return os;" in text(definition.content)

    def test_the_whole_thing_is_unit_test_only(self) -> None:
        members = fprime.write_ostream_operator("MyType", [line("return os;")])
        opening, closing = members[0], members[-1]
        assert isinstance(opening, Lines) and isinstance(closing, Lines)
        assert "#ifdef BUILD_UT" in text(opening.content)
        assert "#endif" in text(closing.content)


class TestBuilderInterop:
    def test_guarding_builder_members_in_place(self) -> None:
        from fprime_cpp_codegen import CppDocBuilder

        d = CppDocBuilder("Ev")
        with d.class_("Ev") as cls:
            with cls.public("Text logging"):
                with cls.if_directive(fprime.FW_ENABLE_TEXT_LOGGING):
                    cls.function("describe", const=True, body="(void) 0;")
        hpp, cpp = d.render_hpp(), d.render_cpp()
        assert hpp.count("describe") == 1
        # Exactly one definition, and it stays inside the guard.
        assert cpp.count("describe") == 1
        assert "#if FW_ENABLE_TEXT_LOGGING" in cpp
        assert cpp.index("#if FW_ENABLE_TEXT_LOGGING") < cpp.index("describe")
        assert cpp.index("describe") < cpp.index("#endif")

    def test_assert_and_ostream_operator_splice_into_a_class(self) -> None:
        from fprime_cpp_codegen import CppDocBuilder

        d = CppDocBuilder("Ev")
        with d.class_("Ev") as cls:
            with cls.public("Public member functions"):
                fn = cls.function("emit")
                fn.param("U32", "id")
                fn.body.raw(fprime.write_assert("id < MAX", "id"))
            cls.member(*fprime.write_ostream_operator("Ev", [line("return os;")]))
        assert "FW_ASSERT(id < MAX, id);" in d.render_cpp()
        assert "friend std::ostream& operator<<(" in d.render_hpp()
        assert "std::ostream& operator<<(std::ostream& os, const Ev& obj) {" in d.render_cpp()
