"""Line- and member-level helpers for common C++ shapes.

Plain functions over ``list[Line]`` and over lists of document members, for callers
already thinking in lines or wanting a fragment to store and reuse.
:mod:`fprime_cpp_codegen.builder` sits on top of these.

The ``wrap_in_*`` helpers return nothing when handed an empty body, so a conditional
block with no content disappears instead of emitting ``if (x) {\\n}``.  Pass
``keep_empty=True`` for the empty braces.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Sequence

from .comments import add_param_comment, write_banner_comment, write_comment
from .doc import ClassMember, Lines, Member, Namespace, Output
from .lines import (
    Line,
    add_prefix_indent,
    blank,
    indent_lines,
    line,
    lines,
)

__all__ = [
    "Radix",
    "add_banner_comment",
    "add_class_member_comment",
    "add_comment",
    "add_member_comment",
    "identifier_from_qualified_name",
    "include",
    "include_guard",
    "include_line",
    "system_include",
    "system_include_line",
    "wrap_class_members_in_if_directive",
    "wrap_in_anonymous_namespace",
    "wrap_in_block",
    "wrap_in_do_while",
    "wrap_in_else",
    "wrap_in_enum",
    "wrap_in_enum_class",
    "wrap_in_extern_c",
    "wrap_in_for_loop",
    "wrap_in_for_loop_staggered",
    "wrap_in_if",
    "wrap_in_if_directive",
    "wrap_in_if_else",
    "wrap_in_named_enum",
    "wrap_in_named_struct",
    "wrap_in_namespace",
    "wrap_in_namespace_lines",
    "wrap_in_namespaces",
    "wrap_in_scope",
    "wrap_in_switch",
    "wrap_in_while",
    "wrap_members_in_if_directive",
    "write_enum_constant",
    "write_function_call",
    "write_id",
    "write_sum",
    "write_using_alias",
    "write_var_decl",
]


class Radix(Enum):
    """How to spell an integer literal."""

    DECIMAL = "decimal"
    HEX = "hex"


# ----------------------------------------------------------------------
# Includes and identifiers
# ----------------------------------------------------------------------


def include(path: str) -> str:
    """A quoted include directive, for project headers."""
    return f'#include "{path}"'


def system_include(path: str) -> str:
    """An angle-bracket include directive, for system headers."""
    return f"#include <{path}>"


def include_line(path: str) -> Line:
    """A quoted include directive as a line."""
    return line(include(path))


def system_include_line(path: str) -> Line:
    """An angle-bracket include directive as a line."""
    return line(system_include(path))


def identifier_from_qualified_name(name: str) -> str:
    """Flatten a dotted or ``::``-qualified name into a single identifier."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")


def include_guard(name: str, *namespaces: str, extension: str = "HPP") -> str:
    """Derive an include-guard macro from a name and its enclosing namespaces.

    ``include_guard("MyClass", "Fw", "Cfg")`` gives ``"Fw_Cfg_MyClass_HPP"``.
    Namespace arguments may themselves be qualified with ``::`` or ``.``.
    """
    parts = [
        part
        for ns in namespaces
        for part in re.split(r"::|\.", ns)
        if part
    ]
    ident = identifier_from_qualified_name("_".join([*parts, name]))
    return f"{ident}_{extension}"


def write_id(value: int) -> str:
    """Spell ``value`` as an uppercase hex literal, e.g. ``"0x1F"``."""
    return f"0x{value:X}"


# ----------------------------------------------------------------------
# Scopes
# ----------------------------------------------------------------------


def wrap_in_scope(
    opening: str,
    body: Sequence[Line],
    closing: str,
    *,
    keep_empty: bool = False,
) -> list[Line]:
    """Indent ``body`` one level between an ``opening`` and ``closing`` line.

    An empty body yields nothing unless ``keep_empty`` is set.
    """
    if not body and not keep_empty:
        return []
    return [*lines(opening), *indent_lines(body), *lines(closing)]


def wrap_in_block(body: Sequence[Line], *, keep_empty: bool = False) -> list[Line]:
    """Wrap ``body`` in a bare braced block."""
    return wrap_in_scope("{", body, "}", keep_empty=keep_empty)


def wrap_in_namespace(
    name: str, body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in ``namespace <name> { ... }``."""
    return wrap_in_scope(f"namespace {name} {{", body, "}", keep_empty=keep_empty)


def wrap_in_anonymous_namespace(
    body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in an unnamed namespace, giving it internal linkage."""
    return wrap_in_scope("namespace {", body, "}", keep_empty=keep_empty)


def wrap_in_namespace_lines(
    names: Sequence[str], body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in a chain of nested namespaces, outermost first."""
    out = list(body)
    for name in reversed(names):
        out = wrap_in_namespace(name, out, keep_empty=keep_empty)
    return out


def wrap_in_extern_c(body: Sequence[Line], *, keep_empty: bool = False) -> list[Line]:
    """Wrap ``body`` in ``extern "C" { ... }``."""
    return wrap_in_scope('extern "C" {', body, "}", keep_empty=keep_empty)


def wrap_in_enum(body: Sequence[Line], *, keep_empty: bool = False) -> list[Line]:
    """Wrap ``body`` in an unnamed ``enum { ... };``."""
    return wrap_in_scope("enum {", body, "};", keep_empty=keep_empty)


def wrap_in_named_enum(
    name: str, body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in ``enum <name> { ... };``."""
    return wrap_in_scope(f"enum {name} {{", body, "};", keep_empty=keep_empty)


def wrap_in_enum_class(
    name: str,
    body: Sequence[Line],
    underlying: str | None = None,
    *,
    keep_empty: bool = False,
) -> list[Line]:
    """Wrap ``body`` in ``enum class <name> [: <underlying>] { ... };``."""
    head = f"enum class {name} : {underlying} {{" if underlying else f"enum class {name} {{"
    return wrap_in_scope(head, body, "};", keep_empty=keep_empty)


def wrap_in_named_struct(
    name: str, body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in ``struct <name> { ... };``."""
    return wrap_in_scope(f"struct {name} {{", body, "};", keep_empty=keep_empty)


def wrap_in_switch(
    selector: str, body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in ``switch (<selector>) { ... }``."""
    return wrap_in_scope(f"switch ({selector}) {{", body, "}", keep_empty=keep_empty)


def wrap_in_if(
    condition: str, body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in ``if (<condition>) { ... }``."""
    return wrap_in_scope(f"if ({condition}) {{", body, "}", keep_empty=keep_empty)


def wrap_in_else(body: Sequence[Line], *, keep_empty: bool = False) -> list[Line]:
    """Wrap ``body`` in ``else { ... }``."""
    return wrap_in_scope("else {", body, "}", keep_empty=keep_empty)


def wrap_in_if_else(
    condition: str,
    if_body: Sequence[Line],
    else_body: Sequence[Line],
    *,
    keep_empty: bool = False,
) -> list[Line]:
    """Wrap two bodies in an ``if``/``else`` pair.

    Either arm vanishing takes its keyword with it, so an empty ``else`` leaves a lone
    ``if`` and no dangling ``else {}``.
    """
    return [
        *wrap_in_if(condition, if_body, keep_empty=keep_empty),
        *wrap_in_else(else_body, keep_empty=keep_empty),
    ]


def wrap_in_while(
    condition: str, body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in ``while (<condition>) { ... }``."""
    return wrap_in_scope(f"while ({condition}) {{", body, "}", keep_empty=keep_empty)


def wrap_in_do_while(
    condition: str, body: Sequence[Line], *, keep_empty: bool = False
) -> list[Line]:
    """Wrap ``body`` in ``do { ... } while (<condition>);``."""
    return wrap_in_scope("do {", body, f"}} while ({condition});", keep_empty=keep_empty)


def wrap_in_for_loop(
    init: str,
    condition: str,
    step: str,
    body: Sequence[Line],
    *,
    keep_empty: bool = False,
) -> list[Line]:
    """Wrap ``body`` in a single-line ``for`` header."""
    return wrap_in_scope(
        f"for ({init}; {condition}; {step}) {{", body, "}", keep_empty=keep_empty
    )


def wrap_in_for_loop_staggered(
    init: str,
    condition: str,
    step: str,
    body: Sequence[Line],
    *,
    keep_empty: bool = False,
) -> list[Line]:
    """Wrap ``body`` in a ``for`` header split across lines."""
    return wrap_in_scope(
        f"""|for (
            |  {init};
            |  {condition};
            |  {step}
            |) {{
            |""",
        body,
        "}",
        keep_empty=keep_empty,
    )


def wrap_in_if_directive(
    directive: str,
    body: Sequence[Line],
    *,
    keep_empty: bool = False,
) -> list[Line]:
    """Bracket ``body`` with a preprocessor ``directive`` and ``#endif``.

    ``directive`` is written verbatim and must include its ``#``, e.g.
    ``"#if FW_ENABLE_TEXT_LOGGING"`` or ``"#ifdef BUILD_UT"``.  The body is not
    indented, since directives are column-zero constructs.
    """
    if not body and not keep_empty:
        return []
    return [*lines(f"\n{directive}"), *body, blank(), *lines("#endif")]


# ----------------------------------------------------------------------
# Statements and declarations
# ----------------------------------------------------------------------


def write_function_call(
    name: str,
    args: Sequence[str] = (),
    variable_args: Sequence[str] = (),
) -> list[Line]:
    """Render a call statement.

    With only ``args`` the call stays on one line.  ``variable_args`` -- trailing
    arguments whose number varies per call site, such as the fields of an event --
    explodes the call one argument per line.
    """
    if not variable_args:
        return lines(f"{name}({', '.join(args)});")
    return wrap_in_scope(f"{name}(", lines(",\n".join([*args, *variable_args])), ");")


def write_sum(
    terms: Sequence[str],
    empty: str = "0",
    separator: str = "+",
    terminator: str = ";",
    *,
    prefix: str = "",
) -> list[Line]:
    """Render a sum of ``terms``, one per line, with the operator trailing.

    An empty list renders as ``empty``, so a zero-term total needs no special case.
    ``prefix`` is written before the first term with the rest hanging beneath it, as in
    ``prefix="return "``.
    """
    if not terms:
        body = lines(f"{empty}{terminator}")
    else:
        body = [
            *(line(f"{t} {separator}") for t in terms[:-1]),
            line(f"{terms[-1]}{terminator}"),
        ]
    return add_prefix_indent(prefix, body) if prefix else body


def write_enum_constant(
    name: str,
    value: int,
    comment: str | None = None,
    radix: Radix = Radix.DECIMAL,
) -> list[Line]:
    """Render one enumerator, with an optional doxygen post-comment."""
    spelled = f"0x{value:x}" if radix is Radix.HEX else str(value)
    return add_param_comment(f"{name} = {spelled},", comment)


def write_using_alias(name: str, target: str) -> list[Line]:
    """Render ``using <name> = <target>;``."""
    return lines(f"using {name} = {target};")


def write_var_decl(type_name: str, name: str, init: str | None = None) -> list[Line]:
    """Render a variable declaration, with an optional initialiser."""
    return lines(f"{type_name} {name} = {init};" if init is not None else f"{type_name} {name};")


# ----------------------------------------------------------------------
# Comments over lines and members
# ----------------------------------------------------------------------


def add_banner_comment(comment: str, body: Sequence[Line]) -> list[Line]:
    """Prefix a non-empty body with a ruled banner comment."""
    return [*write_banner_comment(comment), *body] if body else []


def add_comment(comment: str, body: Sequence[Line]) -> list[Line]:
    """Prefix a non-empty body with a plain comment."""
    return [*write_comment(comment), *body] if body else []


def add_member_comment(
    comment: str,
    members: Sequence[Member],
    output: Output = Output.BOTH,
    cpp_file: str | None = None,
) -> list[Member]:
    """Prefix a non-empty list of document members with a banner comment."""
    if not members:
        return []
    banner = Lines(write_banner_comment(comment), output, cpp_file)
    return [banner, *members]


def add_class_member_comment(
    comment: str,
    members: Sequence[ClassMember],
    output: Output = Output.BOTH,
    cpp_file: str | None = None,
) -> list[ClassMember]:
    """Prefix a non-empty list of class members with a banner comment."""
    if not members:
        return []
    banner = Lines(write_banner_comment(comment), output, cpp_file)
    return [banner, *members]


def wrap_members_in_if_directive(
    directive: str,
    members: Sequence[Member],
    output: Output = Output.BOTH,
) -> list[Member]:
    """Bracket a non-empty list of document members with a preprocessor guard."""
    if not members:
        return []
    return [
        Lines(lines(f"\n{directive}"), output),
        *members,
        Lines([blank(), *lines("#endif")], output),
    ]


def wrap_class_members_in_if_directive(
    directive: str,
    members: Sequence[ClassMember],
    output: Output = Output.BOTH,
) -> list[ClassMember]:
    """Bracket a non-empty list of class members with a preprocessor guard."""
    if not members:
        return []
    return [
        Lines(lines(f"\n{directive}"), output),
        *members,
        Lines([blank(), *lines("#endif")], output),
    ]


def wrap_in_namespaces(
    names: Sequence[str], members: Sequence[Member]
) -> list[Member]:
    """Nest ``members`` inside a chain of namespaces, outermost first."""
    out = list(members)
    for name in reversed(names):
        out = [Namespace(name, out)]
    return out
