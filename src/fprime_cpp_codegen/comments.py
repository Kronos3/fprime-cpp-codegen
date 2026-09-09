"""Comment, banner, and access-tag rendering.

Doxygen ``//!`` comments above declarations, ``//!<`` post comments hanging off
parameters, and ruled banners separating sections.
"""

from __future__ import annotations

from .doc import FileBanner
from .lines import (
    INDENT_INCREMENT,
    IndentMode,
    Line,
    blank,
    indent_lines,
    join,
    join_lists,
    line,
    lines,
)

__all__ = [
    "BANNER_RULE",
    "add_comment_prefix",
    "add_param_comment",
    "left_align_directive",
    "write_access_tag",
    "write_banner",
    "write_banner_comment",
    "write_comment",
    "write_comment_body",
    "write_doxygen_comment",
    "write_doxygen_comment_opt",
    "write_doxygen_post_comment",
    "write_doxygen_post_comment_opt",
    "write_function_body",
]

#: The horizontal rule that delimits a banner comment.
BANNER_RULE = "// ----------------------------------------------------------------------"


def add_comment_prefix(prefix: str, l: Line) -> Line:
    """Prefix a comment line.

    A blank line inside a multi-line comment becomes a bare ``//!``, with no trailing
    space.
    """
    if not l.string:
        return line(prefix)
    return join(" ", line(prefix), l)


def write_comment_body(comment: str) -> list[Line]:
    """Render ``comment`` as ``//`` lines, with no leading blank."""
    return [add_comment_prefix("//", l) for l in lines(comment)]


def write_comment(comment: str) -> list[Line]:
    """Render ``comment`` as ``//`` lines, preceded by a blank line."""
    return [blank(), *write_comment_body(comment)]


def write_banner_comment(comment: str) -> list[Line]:
    """Render ``comment`` as a ruled banner, preceded by a blank line."""
    rule = line(BANNER_RULE)
    return [blank(), rule, *write_comment_body(comment), rule]


def write_doxygen_comment(comment: str) -> list[Line]:
    """Render ``comment`` as ``//!`` lines, preceded by a blank line."""
    return [blank(), *(add_comment_prefix("//!", l) for l in lines(comment))]


def write_doxygen_comment_opt(comment: str | None) -> list[Line]:
    """Render an optional doxygen comment.

    ``None`` yields a single blank line, keeping declarations separated whether or not
    they are documented.
    """
    return write_doxygen_comment(comment) if comment is not None else [blank()]


def write_doxygen_post_comment(comment: str) -> list[Line]:
    """Render ``comment`` as ``//!<`` lines, with no leading blank."""
    return [add_comment_prefix("//!<", l) for l in lines(comment)]


def write_doxygen_post_comment_opt(comment: str | None) -> list[Line]:
    """Render an optional doxygen post comment, or a single blank line."""
    return write_doxygen_post_comment(comment) if comment is not None else [blank()]


def add_param_comment(s: str, comment: str | None) -> list[Line]:
    """Hang a doxygen post-comment off the end of ``s``.

    Continuation lines are indented to the column the comment starts at, stacking
    under its first line.  Used for parameters and enumerated constants.
    """
    if comment is None:
        return lines(s)
    return join_lists(
        IndentMode.INDENT, lines(s), " ", write_doxygen_post_comment(comment)
    )


def write_access_tag(tag: str) -> list[Line]:
    """Render an access-specifier label such as ``public:``.

    Shifted out by two spaces to sit half a level left of the members it governs,
    which are indented two levels into the class body.
    """
    return [blank(), line(f"{tag}:").indent_out(2)]


def left_align_directive(l: Line) -> Line:
    """Force a preprocessor directive to column zero by discarding its indentation."""
    return Line(l.string) if l.string.startswith("#") else l


def write_banner(
    banner: FileBanner,
    file_name: str,
    generic_description: str,
) -> list[Line]:
    """Render the ``\\title``/``\\author``/``\\brief`` block atop a file."""
    return lines(
        f"""|// ======================================================================
            |// \\title  {banner.title(file_name)}
            |// \\author {banner.author(file_name)}
            |// \\brief  {banner.description(file_name, generic_description)}
            |// ======================================================================"""
    )


def write_function_body(body: list[Line]) -> list[Line]:
    """Wrap ``body`` in braces, indenting it one level.

    An empty body renders as braces around a single blank line.
    """
    inner = indent_lines(body, INDENT_INCREMENT) if body else [blank()]
    return [line("{"), *inner, line("}")]
