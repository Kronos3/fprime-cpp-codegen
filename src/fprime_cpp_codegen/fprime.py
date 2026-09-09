"""F Prime idioms, kept separate from the general-purpose layers.

The conventions that show up in every F Prime autocoded file, collected so a
generator does not have to retype them.  All strings and lines; no knowledge of the
FPP model.

Import it explicitly; the core API stays framework-neutral.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .doc import ClassMember, Lines, Member, Output
from .lines import Line, blank, lines, wrap_in_scope

__all__ = [
    "BUILD_UT",
    "FW_ENABLE_TEXT_LOGGING",
    "STANDARD_SYSTEM_CPP_HEADERS",
    "STANDARD_SYSTEM_HPP_HEADERS",
    "STANDARD_USER_CPP_HEADERS",
    "STANDARD_USER_HPP_HEADERS",
    "buffer_name",
    "external_string_decl",
    "guard_class_members_for_text_log",
    "guard_class_members_for_unit_test",
    "guard_members_for_text_log",
    "guard_members_for_unit_test",
    "write_assert",
    "write_ostream_operator",
]

#: The preprocessor condition guarding text-log support.
FW_ENABLE_TEXT_LOGGING = "#if FW_ENABLE_TEXT_LOGGING"

#: The preprocessor condition guarding unit-test-only code.
BUILD_UT = "#ifdef BUILD_UT"

#: Project headers an autocoded F Prime header normally needs.
STANDARD_USER_HPP_HEADERS = [
    f'#include "{path}"'
    for path in (
        "Fw/FPrimeBasicTypes.hpp",
        "Fw/Types/ExternalString.hpp",
        "Fw/Types/Serializable.hpp",
        "Fw/Types/String.hpp",
    )
]

#: System headers an autocoded F Prime header normally needs.  Empty, but kept so a
#: generator can splice it in unconditionally.
STANDARD_SYSTEM_HPP_HEADERS: list[str] = []

#: Project headers an autocoded F Prime source file normally needs.
STANDARD_USER_CPP_HEADERS = ['#include "Fw/Types/Assert.hpp"']

#: System headers an autocoded F Prime source file normally needs.
STANDARD_SYSTEM_CPP_HEADERS: list[str] = []


def write_assert(condition: str, *args: str) -> list[Line]:
    """Render an ``FW_ASSERT``.

    Extra arguments become the assert's reported values, making a flight-side
    assertion diagnosable after the fact.  Each must already be spelled as a C++
    expression, casts included.
    """
    joined = ", ".join([condition, *args])
    return lines(f"FW_ASSERT({joined});")


def buffer_name(name: str) -> str:
    """The backing-array name for a generated ``Fw::ExternalString``."""
    return f"__fprime_ac_{name}_buffer"


def external_string_decl(name: str, size: str) -> list[Line]:
    """Declare an ``Fw::ExternalString`` over a stack buffer of ``size`` characters.

    F Prime avoids dynamic memory, so a string-typed local is a fixed char array plus
    a view onto it, not an owning string object.
    """
    buf = buffer_name(name)
    return lines(f"""|char {buf}[Fw::StringBase::BUFFER_SIZE({size})];
            |Fw::ExternalString {name}({buf}, sizeof {buf});""")


def _guard_members(directive: str, members: Sequence[Any], output: Output) -> list[Any]:
    """Bracket a non-empty run of members with ``directive`` and ``#endif``."""
    if not members:
        return []
    return [
        Lines(lines(f"\n{directive}"), output),
        *members,
        Lines([blank(), *lines("#endif")], output),
    ]


def guard_class_members_for_text_log(
    members: Sequence[ClassMember], output: Output = Output.BOTH
) -> list[ClassMember]:
    """Bracket class members with ``#if FW_ENABLE_TEXT_LOGGING``."""
    return _guard_members(FW_ENABLE_TEXT_LOGGING, members, output)


def guard_members_for_text_log(
    members: Sequence[Member], output: Output = Output.BOTH
) -> list[Member]:
    """Bracket document members with ``#if FW_ENABLE_TEXT_LOGGING``."""
    return _guard_members(FW_ENABLE_TEXT_LOGGING, members, output)


def guard_class_members_for_unit_test(
    members: Sequence[ClassMember], output: Output = Output.BOTH
) -> list[ClassMember]:
    """Bracket class members with ``#ifdef BUILD_UT``."""
    return _guard_members(BUILD_UT, members, output)


def guard_members_for_unit_test(
    members: Sequence[Member], output: Output = Output.BOTH
) -> list[Member]:
    """Bracket document members with ``#ifdef BUILD_UT``."""
    return _guard_members(BUILD_UT, members, output)


def write_ostream_operator(name: str, body: Sequence[Line]) -> list[ClassMember]:
    """Declare and define a friend ``operator<<`` for ``name``, unit-test only.

    Returns the header declaration and the source-file definition, both inside a
    ``BUILD_UT`` guard, ready to splice into a class's member list.
    """
    declaration = Lines(lines(f"""|
                |//! Ostream operator
                |friend std::ostream& operator<<(
                |    std::ostream& os, //!< The ostream
                |    const {name}& obj //!< The object
                |);"""))
    definition = Lines(
        wrap_in_scope(
            f"\nstd::ostream& operator<<(std::ostream& os, const {name}& obj) {{",
            body,
            "}",
        ),
        Output.CPP,
    )
    return guard_class_members_for_unit_test([declaration, definition])
