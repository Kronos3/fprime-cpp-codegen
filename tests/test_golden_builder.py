"""The builder API must be able to produce the reference document too.

``test_golden_ir.py`` pins the writers by hand-building the IR.  This one builds
the same document through the builder, which pins the builder as well: if the two
layers ever disagree about how something renders, one of these tests goes red.

The goldens are copies of what the native ``fpp`` compiler emits, so matching them
is not a requirement -- it is a check that this package's formatting has not
drifted from the F Prime house style that generated code is read alongside.
"""

from __future__ import annotations

from fprime_cpp_codegen import CppDocBuilder, Output

from .conftest import assert_compiles, assert_matches_golden

CTOR_BODY = "// line1\n// line2"
DTOR_BODY = "// Body line 1\n// Body line 2"
TWO_LINES = "This is line 1.\nThis is line 2."
SKIP_LINE = "This is line 1.\n\nThis is line 3."


def build() -> CppDocBuilder:
    """Build the reference document through the builder API."""
    doc = CppDocBuilder("C", description="CppDoc test", include_guard="N_C_HPP")
    doc.include("C.hpp", output=Output.CPP)
    doc.include("C.hpp", output=Output.CPP, cpp_file="Other")

    with doc.namespace("N") as ns:
        with ns.class_("C") as c:
            with c.public("Nested class"):
                with c.class_("N") as nested:
                    with nested.public():
                        nested.constructor(comment=SKIP_LINE, body=CTOR_BODY)
                        nested.destructor(comment=TWO_LINES, body=DTOR_BODY)
                        nested.function(
                            "f",
                            comment=TWO_LINES,
                            params=[
                                (
                                    "const double",
                                    "x",
                                    "This is parameter x line 1.\n\n"
                                    "This is parameter x line 3.",
                                ),
                                (
                                    "const int",
                                    "y",
                                    "This is parameter y line 1.\n"
                                    "This is parameter y line 2.",
                                ),
                            ],
                            cpp_file="Other",
                        )

            c.banner("Consructors and destructors")
            c.constructor(
                comment=TWO_LINES,
                params=[
                    ("const double", "x", "This is parameter x"),
                    ("const int", "y", "This is parameter y"),
                ],
                initializers=["x(x)", "y(y)"],
                body=CTOR_BODY,
            )
            c.destructor(comment=TWO_LINES, body=DTOR_BODY)

            with c.public("Public member functions"):
                c.function(
                    "f",
                    comment=TWO_LINES,
                    params=[
                        ("const double", "x", "This is parameter x", "0.0"),
                        ("const int", "y", "This is parameter y", "0"),
                    ],
                )
                c.function("g", comment=TWO_LINES, pure_virtual=True, const=True)

            with c.private("Private member variables"):
                c.var("double", "x", comment="Member variable x")
                c.var("int", "y", comment="Member variable y")

    with doc.namespace("M") as ns:
        with ns.class_("M") as m:
            with m.public():
                m.constructor(comment=SKIP_LINE, body=CTOR_BODY, cpp_file="Other")
                m.destructor(
                    comment=TWO_LINES, body=DTOR_BODY, virtual=True, cpp_file="Other"
                )

    return doc


def test_hpp_matches_golden() -> None:
    assert_matches_golden(build().render_hpp(), "C.hpp")


def test_default_cpp_matches_golden() -> None:
    assert_matches_golden(build().render_cpp(), "C.cpp")


def test_supplemental_cpp_matches_golden() -> None:
    assert_matches_golden(build().render_cpp("Other"), "Other.cpp")


def test_the_supplemental_file_is_discovered() -> None:
    # Nothing had to tell the builder that "Other.cpp" exists.
    assert set(build().files()) == {"C.hpp", "C.cpp", "Other.cpp"}


def test_generated_sources_compile() -> None:
    assert_compiles(build().files())
