"""Fidelity test: the document IR must reproduce upstream FPP's output exactly.

The three golden files in ``tests/goldens`` are byte-for-byte copies of what the
native (Scala) ``fpp`` compiler's ``CppWriter`` test emits.  Building the same
document out of this package's IR and rendering it must produce the same bytes,
which is what lets a generator move from ``fpp`` to here without churning its
reference output.

This test constructs the document by hand through the low-level IR.  Its sibling
``test_golden_builder.py`` builds the same document through the builder API, so
between them they pin both layers to the same target.
"""

from __future__ import annotations

from fprime_cpp_codegen.comments import (
    write_access_tag,
    write_banner_comment,
    write_doxygen_comment,
)
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
from fprime_cpp_codegen.lines import blank, line, lines
from fprime_cpp_codegen.writer import render_cpp, render_hpp

from .conftest import assert_compiles, assert_matches_golden

INCLUDE_HEADER = [blank(), line('#include "C.hpp"')]

CONST_DOUBLE = Type("const double")
CONST_INT = Type("const int")

CTOR_BODY = [line("// line1"), line("// line2")]
DTOR_BODY = [line("// Body line 1"), line("// Body line 2")]


def build_doc() -> CppDoc:
    """Construct the reference document out of raw IR nodes."""
    nested_class = Class(
        name="N",
        members=[
            Lines(write_access_tag("public")),
            Constructor(
                comment="This is line 1.\n\nThis is line 3.",
                body=CTOR_BODY,
            ),
            Destructor(
                comment="This is line 1.\nThis is line 2.",
                body=DTOR_BODY,
            ),
            Function(
                name="f",
                comment="This is line 1.\nThis is line 2.",
                params=[
                    Param(
                        CONST_DOUBLE,
                        "x",
                        comment="This is parameter x line 1.\n\nThis is parameter x line 3.",
                    ),
                    Param(
                        CONST_INT,
                        "y",
                        comment="This is parameter y line 1.\nThis is parameter y line 2.",
                    ),
                ],
                cpp_file="Other",
            ),
        ],
    )

    class_c = Class(
        name="C",
        members=[
            Lines(write_access_tag("public")),
            Lines(write_banner_comment("Nested class"), output=Output.BOTH),
            nested_class,
            Lines(
                write_banner_comment("Consructors and destructors"),
                output=Output.BOTH,
            ),
            Constructor(
                comment="This is line 1.\nThis is line 2.",
                params=[
                    Param(CONST_DOUBLE, "x", comment="This is parameter x"),
                    Param(CONST_INT, "y", comment="This is parameter y"),
                ],
                initializers=["x(x)", "y(y)"],
                body=CTOR_BODY,
            ),
            Destructor(
                comment="This is line 1.\nThis is line 2.",
                body=DTOR_BODY,
            ),
            Lines(write_access_tag("public")),
            Lines(write_banner_comment("Public member functions"), output=Output.BOTH),
            Function(
                name="f",
                comment="This is line 1.\nThis is line 2.",
                params=[
                    Param(CONST_DOUBLE, "x", comment="This is parameter x", default="0.0"),
                    Param(CONST_INT, "y", comment="This is parameter y", default="0"),
                ],
            ),
            Function(
                name="g",
                comment="This is line 1.\nThis is line 2.",
                sv=SVQualifier.PURE_VIRTUAL,
                const=True,
            ),
            Lines(
                [
                    *write_access_tag("private"),
                    *write_banner_comment("Private member variables"),
                    *write_doxygen_comment("Member variable x"),
                    *lines("double x;"),
                    *write_doxygen_comment("Member variable y"),
                    *lines("int y;"),
                ]
            ),
        ],
    )

    class_m = Class(
        name="M",
        members=[
            Lines(write_access_tag("public")),
            Constructor(
                comment="This is line 1.\n\nThis is line 3.",
                body=CTOR_BODY,
                cpp_file="Other",
            ),
            Destructor(
                comment="This is line 1.\nThis is line 2.",
                body=DTOR_BODY,
                virtual=True,
                cpp_file="Other",
            ),
        ],
    )

    return CppDoc(
        description="CppDoc test",
        hpp_file=HppFile("C.hpp", "N_C_HPP"),
        cpp_file_name="C.cpp",
        members=[
            Lines(INCLUDE_HEADER, output=Output.CPP),
            Lines(INCLUDE_HEADER, output=Output.CPP, cpp_file="Other"),
            Namespace("N", [class_c]),
            Namespace("M", [class_m]),
        ],
    )


def test_hpp_matches_golden() -> None:
    assert_matches_golden(render_hpp(build_doc()), "C.hpp")


def test_default_cpp_matches_golden() -> None:
    assert_matches_golden(render_cpp(build_doc()), "C.cpp")


def test_supplemental_cpp_matches_golden() -> None:
    assert_matches_golden(render_cpp(build_doc(), "Other"), "Other.cpp")


def test_generated_sources_compile() -> None:
    doc = build_doc()
    assert_compiles(
        {
            "C.hpp": render_hpp(doc),
            "C.cpp": render_cpp(doc),
            "Other.cpp": render_cpp(doc, "Other"),
        }
    )
