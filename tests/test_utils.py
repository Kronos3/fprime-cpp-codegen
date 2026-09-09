"""Tests for the line- and member-level C++ helpers."""

from __future__ import annotations

from fprime_cpp_codegen.doc import Class, Lines, Namespace, Output
from fprime_cpp_codegen.lines import Line, line, render
from fprime_cpp_codegen.utils import (
    Radix,
    add_banner_comment,
    add_class_member_comment,
    add_comment,
    add_member_comment,
    identifier_from_qualified_name,
    include,
    include_guard,
    system_include,
    wrap_class_members_in_if_directive,
    wrap_in_anonymous_namespace,
    wrap_in_block,
    wrap_in_do_while,
    wrap_in_enum_class,
    wrap_in_extern_c,
    wrap_in_for_loop,
    wrap_in_for_loop_staggered,
    wrap_in_if,
    wrap_in_if_directive,
    wrap_in_if_else,
    wrap_in_named_struct,
    wrap_in_namespace_lines,
    wrap_in_namespaces,
    wrap_in_scope,
    wrap_in_switch,
    wrap_in_while,
    wrap_members_in_if_directive,
    write_enum_constant,
    write_function_call,
    write_id,
    write_sum,
    write_using_alias,
    write_var_decl,
)

BODY = [line("doIt();")]


def text(ll: list[Line]) -> str:
    return render(ll)


class TestIncludes:
    def test_quoted_and_angle_forms(self) -> None:
        assert include("Fw/Types.hpp") == '#include "Fw/Types.hpp"'
        assert system_include("cstdio") == "#include <cstdio>"

    def test_include_guard_from_namespaces(self) -> None:
        assert include_guard("MyClass", "Fw", "Cfg") == "Fw_Cfg_MyClass_HPP"

    def test_include_guard_splits_qualified_namespaces(self) -> None:
        assert include_guard("C", "A::B") == "A_B_C_HPP"
        assert include_guard("C", "A.B") == "A_B_C_HPP"

    def test_include_guard_without_namespaces(self) -> None:
        assert include_guard("C") == "C_HPP"

    def test_include_guard_extension_is_configurable(self) -> None:
        assert include_guard("C", extension="H") == "C_H"

    def test_identifier_flattening(self) -> None:
        assert identifier_from_qualified_name("A::B.c-d") == "A_B_c_d"

    def test_write_id_is_uppercase_hex(self) -> None:
        assert write_id(255) == "0xFF"


class TestScopes:
    def test_scope_indents_its_body(self) -> None:
        assert text(wrap_in_block(BODY)) == "{\n  doIt();\n}\n"

    def test_empty_scope_vanishes(self) -> None:
        assert wrap_in_block([]) == []

    def test_keep_empty_forces_the_braces(self) -> None:
        assert text(wrap_in_block([], keep_empty=True)) == "{\n}\n"

    def test_if_and_else(self) -> None:
        assert text(wrap_in_if("x > 0", BODY)) == "if (x > 0) {\n  doIt();\n}\n"

    def test_if_else_drops_an_empty_else(self) -> None:
        # A dangling "else {}" is worse than no else at all.
        assert text(wrap_in_if_else("c", BODY, [])) == "if (c) {\n  doIt();\n}\n"

    def test_if_else_both_arms(self) -> None:
        assert text(wrap_in_if_else("c", BODY, [line("other();")])) == (
            "if (c) {\n  doIt();\n}\nelse {\n  other();\n}\n"
        )

    def test_while_and_do_while(self) -> None:
        assert text(wrap_in_while("c", BODY)) == "while (c) {\n  doIt();\n}\n"
        assert text(wrap_in_do_while("c", BODY)) == "do {\n  doIt();\n} while (c);\n"

    def test_for_loop(self) -> None:
        assert text(wrap_in_for_loop("U32 i = 0", "i < n", "i++", BODY)) == (
            "for (U32 i = 0; i < n; i++) {\n  doIt();\n}\n"
        )

    def test_staggered_for_loop_has_no_trailing_blank(self) -> None:
        result = wrap_in_for_loop_staggered("U32 i = 0", "i < n", "i++", BODY)
        assert text(result) == (
            "for (\n  U32 i = 0;\n  i < n;\n  i++\n) {\n  doIt();\n}\n"
        )

    def test_switch(self) -> None:
        assert text(wrap_in_switch("k", BODY)) == "switch (k) {\n  doIt();\n}\n"

    def test_namespaces_nest_outermost_first(self) -> None:
        assert text(wrap_in_namespace_lines(["A", "B"], BODY)) == (
            "namespace A {\n  namespace B {\n    doIt();\n  }\n}\n"
        )

    def test_anonymous_namespace_and_extern_c(self) -> None:
        assert text(wrap_in_anonymous_namespace(BODY)).startswith("namespace {")
        assert text(wrap_in_extern_c(BODY)).startswith('extern "C" {')

    def test_enum_class_with_and_without_underlying_type(self) -> None:
        body = [line("A = 0,")]
        assert text(wrap_in_enum_class("E", body)) == "enum class E {\n  A = 0,\n};\n"
        assert text(wrap_in_enum_class("E", body, "U8")) == (
            "enum class E : U8 {\n  A = 0,\n};\n"
        )

    def test_named_struct(self) -> None:
        assert text(wrap_in_named_struct("S", [line("U32 x;")])) == (
            "struct S {\n  U32 x;\n};\n"
        )

    def test_scope_accepts_multiline_openings(self) -> None:
        assert text(wrap_in_scope("a\n|b", BODY, "c")) == "a\nb\n  doIt();\nc\n"


class TestIfDirective:
    def test_guarded_lines_are_not_indented(self) -> None:
        # The directive must sit at column zero.
        assert text(wrap_in_if_directive("#ifdef BUILD_UT", BODY)) == (
            "\n#ifdef BUILD_UT\ndoIt();\n\n#endif\n"
        )

    def test_empty_guard_vanishes(self) -> None:
        assert wrap_in_if_directive("#ifdef X", []) == []

    def test_members_are_bracketed_by_lines_members(self) -> None:
        members = wrap_class_members_in_if_directive("#ifdef X", [Lines(BODY)])
        assert len(members) == 3
        assert isinstance(members[0], Lines) and isinstance(members[2], Lines)
        assert members[0].output is Output.BOTH

    def test_empty_member_list_vanishes(self) -> None:
        assert wrap_members_in_if_directive("#ifdef X", []) == []
        assert wrap_class_members_in_if_directive("#ifdef X", []) == []


class TestStatements:
    def test_function_call_stays_on_one_line(self) -> None:
        assert text(write_function_call("f", ["a", "b"])) == "f(a, b);\n"

    def test_function_call_with_no_arguments(self) -> None:
        assert text(write_function_call("f")) == "f();\n"

    def test_variable_arguments_explode_the_call(self) -> None:
        assert text(write_function_call("f", ["a"], ["b", "c"])) == (
            "f(\n  a,\n  b,\n  c\n);\n"
        )

    def test_sum(self) -> None:
        assert text(write_sum(["a", "b", "c"])) == "a +\nb +\nc;\n"

    def test_sum_of_one_term(self) -> None:
        assert text(write_sum(["a"])) == "a;\n"

    def test_empty_sum_uses_the_placeholder(self) -> None:
        assert text(write_sum([])) == "0;\n"

    def test_sum_separator_and_terminator_are_configurable(self) -> None:
        assert text(write_sum(["a", "b"], separator="&&", terminator="")) == "a &&\nb\n"

    def test_enum_constant_decimal_and_hex(self) -> None:
        assert text(write_enum_constant("A", 10)) == "A = 10,\n"
        assert text(write_enum_constant("A", 255, radix=Radix.HEX)) == "A = 0xff,\n"

    def test_enum_constant_comment(self) -> None:
        assert text(write_enum_constant("A", 1, "first")) == "A = 1, //!< first\n"

    def test_using_alias_and_var_decl(self) -> None:
        assert text(write_using_alias("Id", "U32")) == "using Id = U32;\n"
        assert text(write_var_decl("U32", "x")) == "U32 x;\n"
        assert text(write_var_decl("U32", "x", "0")) == "U32 x = 0;\n"


class TestMemberComments:
    def test_banner_and_comment_over_lines(self) -> None:
        assert "// Section" in text(add_banner_comment("Section", BODY))
        assert "// Note" in text(add_comment("Note", BODY))

    def test_comments_over_an_empty_body_vanish(self) -> None:
        assert add_banner_comment("Section", []) == []
        assert add_comment("Note", []) == []
        assert add_member_comment("Section", []) == []
        assert add_class_member_comment("Section", []) == []

    def test_member_comment_prepends_a_lines_member(self) -> None:
        members = add_member_comment("Section", [Class("C")])
        assert isinstance(members[0], Lines)
        assert members[0].output is Output.BOTH
        assert len(members) == 2

    def test_wrap_in_namespaces_nests_members(self) -> None:
        result = wrap_in_namespaces(["A", "B"], [Class("C")])
        assert isinstance(result[0], Namespace) and result[0].name == "A"
        inner = result[0].members[0]
        assert isinstance(inner, Namespace) and inner.name == "B"
        assert isinstance(inner.members[0], Class)

    def test_wrap_in_no_namespaces_is_a_passthrough(self) -> None:
        members = [Class("C")]
        assert wrap_in_namespaces([], members) == members
