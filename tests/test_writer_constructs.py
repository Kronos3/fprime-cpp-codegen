"""Tests for how the writers render each C++ construct.

The emphasis is on the decisions that are easy to get wrong: which file a
definition lands in, which specifiers are repeated on an out-of-line definition
and which are not, and what happens to members that have no definition at all.
"""

from __future__ import annotations

import pytest

from fprime_cpp_codegen.comments import write_access_tag
from fprime_cpp_codegen.doc import (
    Class,
    Constructor,
    CppDoc,
    Destructor,
    Function,
    HppFile,
    Lines,
    Namespace,
    Output,
    Param,
    SVQualifier,
    Type,
)
from fprime_cpp_codegen.errors import CppCodegenError, ValidationError
from fprime_cpp_codegen.lines import line, lines
from fprime_cpp_codegen.writer import render_cpp, render_hpp

from .conftest import assert_compiles


def doc_with(*members: object, description: str = "test") -> CppDoc:
    return CppDoc(
        description=description,
        hpp_file=HppFile("T.hpp", "T_HPP"),
        cpp_file_name="T.cpp",
        members=list(members),  # type: ignore[arg-type]
    )


def in_class(*members: object, **kwargs: object) -> CppDoc:
    return doc_with(Class("C", members=list(members), **kwargs))  # type: ignore[arg-type]


class TestFunctionQualifiers:
    def test_pure_virtual_declares_but_does_not_define(self) -> None:
        doc = in_class(Function("f", sv=SVQualifier.PURE_VIRTUAL))
        assert "virtual void f() = 0;" in render_hpp(doc)
        assert "f()" not in render_cpp(doc)

    def test_pure_virtual_with_body_gets_a_default_implementation(self) -> None:
        doc = in_class(
            Function("f", sv=SVQualifier.PURE_VIRTUAL, body=[line("doIt();")])
        )
        assert "virtual void f() = 0;" in render_hpp(doc)
        assert "void C ::" in render_cpp(doc)

    def test_static_and_virtual_lead_the_declaration(self) -> None:
        hpp = render_hpp(
            in_class(
                Function("s", sv=SVQualifier.STATIC),
                Function("v", sv=SVQualifier.VIRTUAL),
            )
        )
        assert "static void s();" in hpp
        assert "virtual void v();" in hpp

    def test_override_and_final_trail_the_declaration(self) -> None:
        hpp = render_hpp(
            in_class(
                Function("o", sv=SVQualifier.OVERRIDE),
                Function("f", sv=SVQualifier.FINAL),
            )
        )
        assert "void o() override;" in hpp
        assert "void f() final;" in hpp

    def test_trailing_specifier_order(self) -> None:
        doc = in_class(
            Function("f", const=True, noexcept=True, sv=SVQualifier.OVERRIDE)
        )
        assert "void f() const noexcept override;" in render_hpp(doc)

    def test_definition_repeats_const_and_noexcept_but_not_override(self) -> None:
        # An out-of-line definition must match the declaration on const and
        # noexcept, and must NOT restate virtual, static, override or final.
        cpp = render_cpp(
            in_class(
                Function(
                    "f",
                    const=True,
                    noexcept=True,
                    sv=SVQualifier.OVERRIDE,
                    body=[line("return;")],
                )
            )
        )
        assert "f() const noexcept" in cpp
        assert "override" not in cpp
        assert "virtual" not in cpp

    def test_empty_return_type_emits_no_return_type(self) -> None:
        doc = in_class(Function("operator bool", ret_type=Type(""), const=True))
        assert "operator bool() const;" in render_hpp(doc)

    def test_cpp_type_spelling_is_used_only_for_the_return_type(self) -> None:
        doc = doc_with(
            Namespace(
                "N",
                [
                    Class(
                        "C",
                        members=[
                            Function(
                                "f",
                                ret_type=Type("Status", "N::C::Status"),
                                params=[Param(Type("Kind"), "k")],
                                body=[line("return Status();")],
                            )
                        ],
                    )
                ],
            )
        )
        cpp = render_cpp(doc)
        assert "N::C::Status C ::" in cpp
        # The parameter keeps its unqualified spelling: an out-of-class parameter
        # list is looked up in the class's own scope.
        assert "f(Kind k)" in cpp
        assert "Status f(Kind k);" in render_hpp(doc)


class TestDeletedAndDefaulted:
    def test_deleted_declares_and_defines_nothing(self) -> None:
        doc = in_class(
            Constructor(params=[Param(Type("const C&"), "other")], deleted=True)
        )
        assert "C(const C& other) = delete;" in render_hpp(doc)
        assert "= delete" not in render_cpp(doc)
        assert "C ::" not in render_cpp(doc)

    def test_defaulted_destructor(self) -> None:
        doc = in_class(Destructor(defaulted=True))
        assert "~C() = default;" in render_hpp(doc)
        assert "~C" not in render_cpp(doc)

    def test_deleted_and_defaulted_together_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="both deleted and defaulted"):
            render_hpp(in_class(Destructor(deleted=True, defaulted=True)))

    def test_deleted_with_a_body_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot also have a body"):
            render_hpp(in_class(Destructor(deleted=True, body=[line("x();")])))

    def test_pure_virtual_cannot_be_deleted(self) -> None:
        with pytest.raises(ValidationError, match="cannot also be deleted"):
            render_hpp(in_class(Function("f", sv=SVQualifier.PURE_VIRTUAL, deleted=True)))


class TestHeaderOnlyDefinitions:
    def test_inline_body_puts_the_definition_in_the_header(self) -> None:
        doc = in_class(
            Function("get", ret_type=Type("U32"), inline_body=True, body=[line("return 1;")])
        )
        hpp = render_hpp(doc)
        assert "U32 get()" in hpp
        assert "return 1;" in hpp
        assert "return 1;" not in render_cpp(doc)

    def test_inline_keyword_implies_a_header_definition(self) -> None:
        # An inline function defined in one .cpp would not link from another.
        doc = in_class(Function("get", inline=True, body=[line("x();")]))
        assert "x();" in render_hpp(doc)
        assert "x();" not in render_cpp(doc)

    def test_constexpr_implies_a_header_definition(self) -> None:
        doc = in_class(
            Function("n", ret_type=Type("U32"), constexpr=True, body=[line("return 4;")])
        )
        assert "return 4;" in render_hpp(doc)
        assert "return 4;" not in render_cpp(doc)

    def test_function_template_is_defined_in_the_header(self) -> None:
        doc = in_class(
            Function(
                "cast",
                ret_type=Type("T"),
                template="typename T",
                body=[line("return static_cast<T>(m_v);")],
            )
        )
        hpp = render_hpp(doc)
        assert "template <typename T>" in hpp
        assert "return static_cast<T>(m_v);" in hpp
        assert "static_cast" not in render_cpp(doc)

    def test_templated_class_defines_everything_in_the_header(self) -> None:
        doc = doc_with(
            Class(
                "Box",
                template="typename T",
                members=[
                    Constructor(initializers=["m_v()"]),
                    Destructor(),
                    Function("get", ret_type=Type("T"), const=True, body=[line("return m_v;")]),
                ],
            )
        )
        hpp = render_hpp(doc)
        assert "template <typename T>" in hpp
        assert "return m_v;" in hpp
        assert "m_v()" in hpp
        cpp = render_cpp(doc)
        # Every member was defined in the header.
        assert "Box" not in cpp

    def test_pure_virtual_with_body_in_a_templated_class_is_rejected(self) -> None:
        doc = doc_with(
            Class(
                "B",
                template="typename T",
                members=[
                    Function("f", sv=SVQualifier.PURE_VIRTUAL, body=[line("x();")])
                ],
            )
        )
        with pytest.raises(ValidationError, match="pure virtual with a body"):
            render_hpp(doc)


class TestClasses:
    def test_final_and_superclasses(self) -> None:
        hpp = render_hpp(
            doc_with(Class("C", superclass_decls="public A, private B", final=True))
        )
        assert "class C final :" in hpp
        assert "public A, private B" in hpp

    def test_struct_keyword(self) -> None:
        assert "struct S {" in render_hpp(doc_with(Class("S", struct=True)))

    def test_class_template_declaration(self) -> None:
        hpp = render_hpp(doc_with(Class("C", template="typename T, int N")))
        assert "template <typename T, int N>" in hpp

    def test_nested_class_definitions_are_qualified(self) -> None:
        doc = doc_with(
            Class(
                "Outer",
                members=[
                    Class("Inner", members=[Constructor(), Destructor(virtual=True)])
                ],
            )
        )
        cpp = render_cpp(doc)
        assert "Outer::Inner ::" in cpp
        assert "Inner()" in cpp
        assert "~Inner()" in cpp

    def test_constructor_outside_a_class_is_rejected(self) -> None:
        with pytest.raises(CppCodegenError, match="only appear inside a class"):
            render_hpp(doc_with(Constructor()))

    def test_namespace_inside_a_class_is_rejected(self) -> None:
        with pytest.raises(CppCodegenError, match="may not be declared inside a class"):
            render_hpp(in_class(Namespace("N")))


class TestFreeFunctions:
    def test_free_function_definition_is_brace_on_the_same_line(self) -> None:
        doc = doc_with(
            Function("helper", ret_type=Type("U32"), body=[line("return 0;")])
        )
        cpp = render_cpp(doc)
        assert "U32 helper() {" in cpp
        assert "return 0;" in cpp

    def test_free_function_declaration(self) -> None:
        assert "U32 helper();" in render_hpp(
            doc_with(Function("helper", ret_type=Type("U32")))
        )


class TestFileSelection:
    def test_definitions_go_only_to_their_named_source_file(self) -> None:
        doc = in_class(
            Function("here", body=[line("a();")]),
            Function("there", body=[line("b();")], cpp_file="Other"),
        )
        default = render_cpp(doc)
        other = render_cpp(doc, "Other")
        assert "a();" in default and "b();" not in default
        assert "b();" in other and "a();" not in other
        hpp = render_hpp(doc)
        assert "void here();" in hpp and "void there();" in hpp

    def test_lines_output_selection(self) -> None:
        doc = doc_with(
            Lines(lines("// hpp only"), Output.HPP),
            Lines(lines("// cpp only"), Output.CPP),
            Lines(lines("// both"), Output.BOTH),
        )
        hpp, cpp = render_hpp(doc), render_cpp(doc)
        assert "// hpp only" in hpp and "// cpp only" not in hpp and "// both" in hpp
        assert "// cpp only" in cpp and "// hpp only" not in cpp and "// both" in cpp

    def test_empty_namespace_is_kept_in_the_header_and_dropped_from_the_source(
        self,
    ) -> None:
        doc = doc_with(Namespace("Empty", [Lines(lines("// decl"), Output.HPP)]))
        assert "namespace Empty {" in render_hpp(doc)
        assert "namespace Empty" not in render_cpp(doc)


class TestParameters:
    def test_single_uncommented_parameter_stays_inline(self) -> None:
        doc = in_class(Function("f", params=[Param(Type("U32"), "x")]))
        assert "void f(U32 x);" in render_hpp(doc)

    def test_commented_parameter_is_exploded_even_when_alone(self) -> None:
        hpp = render_hpp(
            in_class(Function("f", params=[Param(Type("U32"), "x", comment="the x")]))
        )
        assert "void f(\n" in hpp
        assert "U32 x //!< the x" in hpp

    def test_defaults_appear_in_the_header_only(self) -> None:
        doc = in_class(
            Function(
                "f",
                params=[Param(Type("U32"), "x"), Param(Type("U32"), "y", default="0")],
                body=[line("use(x, y);")],
            )
        )
        assert "U32 y = 0" in render_hpp(doc)
        assert "= 0" not in render_cpp(doc)

    def test_a_default_argument_must_be_trailing(self) -> None:
        doc = in_class(
            Function(
                "f",
                params=[Param(Type("U32"), "x", default="0"), Param(Type("U32"), "y")],
            )
        )
        with pytest.raises(ValidationError, match="default arguments to be trailing"):
            render_hpp(doc)

    def test_multiline_parameter_comment_hangs_under_its_first_line(self) -> None:
        hpp = render_hpp(
            in_class(
                Function("f", params=[Param(Type("U32"), "x", comment="one\ntwo")])
            )
        )
        first = next(l for l in hpp.splitlines() if "//!< one" in l)
        second = next(l for l in hpp.splitlines() if "//!< two" in l)
        assert first.index("//!<") == second.index("//!<")


def test_a_document_using_every_construct_compiles() -> None:
    doc = CppDoc(
        description="everything",
        hpp_file=HppFile("Everything.hpp", "Everything_HPP"),
        cpp_file_name="Everything.cpp",
        members=[
            Lines([line('#include "Everything.hpp"')], Output.CPP),
            Lines(lines("using U32 = unsigned int;"), Output.HPP),
            Namespace(
                "Demo",
                [
                    Class(
                        "Base",
                        members=[
                            Lines(write_access_tag("public")),
                            Destructor(virtual=True, body=[]),
                            Function("run", sv=SVQualifier.PURE_VIRTUAL),
                        ],
                    ),
                    Class(
                        "Impl",
                        superclass_decls="public Base",
                        final=True,
                        members=[
                            Lines(write_access_tag("public")),
                            Constructor(
                                explicit=True,
                                params=[Param(Type("U32"), "n", comment="count")],
                                initializers=["m_n(n)"],
                            ),
                            Constructor(
                                params=[Param(Type("const Impl&"), "o")], deleted=True
                            ),
                            Destructor(defaulted=True),
                            Function(
                                "run",
                                sv=SVQualifier.OVERRIDE,
                                noexcept=True,
                                body=[line("m_n++;")],
                            ),
                            Function(
                                "count",
                                ret_type=Type("U32"),
                                const=True,
                                inline=True,
                                body=[line("return m_n;")],
                            ),
                            Lines(write_access_tag("private") + lines("U32 m_n;")),
                        ],
                    ),
                    Class(
                        "Box",
                        template="typename T",
                        members=[
                            Lines(write_access_tag("public")),
                            Constructor(
                                params=[Param(Type("T"), "v")], initializers=["m_v(v)"]
                            ),
                            Function("get", ret_type=Type("T"), const=True, body=[line("return m_v;")]),
                            Lines(write_access_tag("private") + lines("T m_v;")),
                        ],
                    ),
                    Function(
                        "twice",
                        ret_type=Type("U32"),
                        params=[Param(Type("U32"), "x")],
                        body=[line("return 2 * x;")],
                    ),
                ],
            ),
        ],
    )
    assert_compiles(
        {"Everything.hpp": render_hpp(doc), "Everything.cpp": render_cpp(doc)}
    )
