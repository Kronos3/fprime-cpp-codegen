"""The builder API: the comfortable way to assemble a C++ document.

Nesting in the generated C++ follows nesting in the Python::

    doc = CppDocBuilder("Counter", description="a counter")
    doc.include("Fw/FPrimeBasicTypes.hpp")

    with doc.namespace("Fw") as ns:
        with ns.class_("Counter", final=True) as cls:
            with cls.public("Constructors and destructors"):
                cls.constructor(initializers=["m_count(0)"])
                cls.destructor()
            with cls.public("Public member functions"):
                with cls.function("bump", ret="U32") as fn:
                    fn.body.line("m_count++;")
                    fn.body.line("return m_count;")
            with cls.private("Member variables"):
                cls.var("U32", "m_count", comment="How many bumps so far")

    doc.write("build-artifacts")

``with`` is optional almost everywhere.  A builder is attached to its parent the
moment you create it, so its position in the output is already fixed and you can
keep filling it in afterwards::

    fn = cls.function("bump", ret="U32")
    fn.param("U32", "by", default="1")
    fn.body.line("return m_count + by;")

Use ``with`` where you want the visual grouping, and on access sections and
preprocessor guards, where it also makes an empty section disappear instead of
leaving a stray ``public:`` or an empty ``#if``.

Builders are values.  A helper function can build a fragment and return it, and
the caller splices it in with :meth:`ClassBuilder.member`, which is what makes
generating from a data model pleasant::

    def accessor(cls, name, type_name):
        fn = cls.function(f"get{name}", ret=type_name, const=True)
        fn.body.line(f"return m_{name};")

    for name, type_name in model.fields:
        accessor(cls, name, type_name)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, Iterable, Iterator, Sequence, TypeVar

from .body import Body, Code, stmts
from .comments import (
    add_param_comment,
    write_access_tag,
    write_banner_comment,
    write_doxygen_comment,
    write_doxygen_comment_opt,
)
from .doc import (
    Class,
    Constructor,
    CppDoc,
    Destructor,
    FileBanner,
    Function,
    HppFile,
    Lines,
    Namespace,
    Output,
    Param,
    SVQualifier,
    Type,
    Variable,
    as_type,
)
from .errors import ValidationError
from .lines import Line, blank
from .lines import line as _line
from .lines import lines as _lines
from .output import WriteResult, doc_files, write_doc
from .utils import (
    Radix,
    include,
    include_guard,
    system_include,
    wrap_in_enum,
    wrap_in_enum_class,
    wrap_in_named_enum,
)
from .writer import (
    needs_definition,
    render_cpp,
    render_hpp,
    variable_defined_in_source,
)

__all__ = [
    "AccessSection",
    "ClassBuilder",
    "ConstructorBuilder",
    "CppDocBuilder",
    "DestructorBuilder",
    "EnumBuilder",
    "FunctionBuilder",
    "NamespaceBuilder",
]

_T = TypeVar("_T")
_T2 = TypeVar("_T2")

#: What a body-shaped argument accepts.  See :data:`fprime_cpp_codegen.body.Code`.
BodyLike = Code


class _Builder(ABC, Generic[_T]):
    """Something that turns into an IR node when the document is built."""

    @abstractmethod
    def build(self) -> _T:
        """Produce the IR node.  Safe to call more than once."""

    def build_members(self) -> list[Any]:
        """The IR members this builder contributes, in order.

        Almost always just :meth:`build`.  Decoration that has to be repeated per
        output file -- a banner, a preprocessor guard -- overrides this to
        contribute several members at once.
        """
        return [self.build()]


def _resolve(items: Sequence[object]) -> list[Any]:
    """Turn a mixed list of IR nodes and builders into IR nodes, preserving order."""
    out: list[Any] = []
    for item in items:
        if isinstance(item, _Builder):
            out.extend(item.build_members())
        else:
            out.append(item)
    return out


def _as_body_lines(body: Code) -> list[Line]:
    """Coerce whatever the caller passed as a body into lines."""
    return stmts(body)


def _as_params(params: Iterable[Param | tuple[str, ...] | Sequence[str]]) -> list[Param]:
    """Coerce a parameter spec list into :class:`Param` objects.

    A tuple is read as ``(type, name)`` optionally followed by ``comment`` and
    ``default``, which keeps a generated parameter table readable at the call site.
    """
    out: list[Param] = []
    for p in params:
        if isinstance(p, Param):
            out.append(p)
            continue
        parts = list(p)
        if not 2 <= len(parts) <= 4:
            raise ValidationError(
                f"parameter {p!r} should be a Param, or a tuple of "
                "(type, name[, comment[, default]])"
            )
        type_name, name, *rest = parts
        # An empty string is how the tuple form says "skip this one" -- handy when
        # you want a default argument but no comment.
        comment = rest[0] or None if len(rest) > 0 else None
        default = rest[1] or None if len(rest) > 1 else None
        out.append(Param(as_type(type_name), name, comment, default))
    return out


def _sv_qualifier(
    *,
    static: bool,
    virtual: bool,
    pure_virtual: bool,
    override: bool,
    final: bool,
) -> SVQualifier:
    """Collapse the mutually exclusive static/virtual flags into one qualifier."""
    if pure_virtual:
        # "virtual and pure_virtual" is redundant rather than contradictory, so it
        # is allowed; anything else alongside it is a mistake.
        conflicts = [n for n, v in (("static", static), ("override", override), ("final", final)) if v]
        if conflicts:
            raise ValidationError(
                f"a pure virtual function cannot also be {' or '.join(conflicts)}"
            )
        return SVQualifier.PURE_VIRTUAL
    chosen = [
        n
        for n, v in (
            ("static", static),
            ("virtual", virtual),
            ("override", override),
            ("final", final),
        )
        if v
    ]
    if len(chosen) > 1:
        raise ValidationError(
            f"a function cannot be {' and '.join(chosen)} at once; pick one"
        )
    if static:
        return SVQualifier.STATIC
    if virtual:
        return SVQualifier.VIRTUAL
    if override:
        return SVQualifier.OVERRIDE
    if final:
        return SVQualifier.FINAL
    return SVQualifier.NONE


def _extends(extends: str | Sequence[str] | None) -> str | None:
    """Normalise a base-class specification into the text after the colon."""
    if extends is None:
        return None
    if isinstance(extends, str):
        return extends
    joined = ", ".join(extends)
    return joined or None


@dataclass
class _DocContext:
    """State shared by every builder in one document."""

    cpp_files: list[str | None] = field(default_factory=lambda: [None])

    @property
    def cpp_file(self) -> str | None:
        """The source file definitions currently default to."""
        return self.cpp_files[-1]


# ----------------------------------------------------------------------
# Definition builders
# ----------------------------------------------------------------------


class FunctionBuilder(_Builder[Function]):
    """A function or member function under construction."""

    def __init__(
        self,
        name: str,
        *,
        ret: Type | str = "void",
        params: Iterable[Param | Sequence[str]] = (),
        comment: str | None = None,
        body: Code = None,
        const: bool = False,
        static: bool = False,
        virtual: bool = False,
        pure_virtual: bool = False,
        override: bool = False,
        final: bool = False,
        constexpr: bool = False,
        inline: bool = False,
        noexcept: bool = False,
        deleted: bool = False,
        defaulted: bool = False,
        template: str | None = None,
        inline_body: bool = False,
        cpp_file: str | None = None,
    ) -> None:
        if not name:
            raise ValidationError("a function needs a name")
        self.name = name
        self.ret = as_type(ret)
        self.comment = comment
        self.const = const
        self.constexpr = constexpr
        self.inline = inline
        self.noexcept = noexcept
        self.deleted = deleted
        self.defaulted = defaulted
        self.template = template
        self.inline_body = inline_body
        self.cpp_file = cpp_file
        self._sv = _sv_qualifier(
            static=static,
            virtual=virtual,
            pure_virtual=pure_virtual,
            override=override,
            final=final,
        )
        self._params = _as_params(params)
        self.body = Body(_as_body_lines(body))

    def param(
        self,
        type_name: Type | str,
        name: str,
        *,
        comment: str | None = None,
        default: str | None = None,
    ) -> FunctionBuilder:
        """Append one formal parameter.  Returns self, so calls can be chained."""
        self._params.append(Param(as_type(type_name), name, comment, default))
        return self

    def params(self, *params: Param | Sequence[str]) -> FunctionBuilder:
        """Append several formal parameters at once."""
        self._params.extend(_as_params(params))
        return self

    def build(self) -> Function:
        return Function(
            self.name,
            params=list(self._params),
            ret_type=self.ret,
            body=self.body.build(),
            comment=self.comment,
            sv=self._sv,
            const=self.const,
            constexpr=self.constexpr,
            inline=self.inline,
            noexcept=self.noexcept,
            deleted=self.deleted,
            defaulted=self.defaulted,
            template=self.template,
            inline_body=self.inline_body,
            cpp_file=self.cpp_file,
        )

    def __enter__(self) -> FunctionBuilder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class ConstructorBuilder(_Builder[Constructor]):
    """A constructor under construction."""

    def __init__(
        self,
        *,
        params: Iterable[Param | Sequence[str]] = (),
        initializers: Iterable[str] = (),
        comment: str | None = None,
        body: Code = None,
        explicit: bool = False,
        constexpr: bool = False,
        noexcept: bool = False,
        deleted: bool = False,
        defaulted: bool = False,
        template: str | None = None,
        inline_body: bool = False,
        cpp_file: str | None = None,
    ) -> None:
        self.comment = comment
        self.explicit = explicit
        self.constexpr = constexpr
        self.noexcept = noexcept
        self.deleted = deleted
        self.defaulted = defaulted
        self.template = template
        self.inline_body = inline_body
        self.cpp_file = cpp_file
        self._params = _as_params(params)
        self._initializers = list(initializers)
        self.body = Body(_as_body_lines(body))

    def param(
        self,
        type_name: Type | str,
        name: str,
        *,
        comment: str | None = None,
        default: str | None = None,
    ) -> ConstructorBuilder:
        """Append one formal parameter."""
        self._params.append(Param(as_type(type_name), name, comment, default))
        return self

    def params(self, *params: Param | Sequence[str]) -> ConstructorBuilder:
        """Append several formal parameters at once."""
        self._params.extend(_as_params(params))
        return self

    def init(self, *entries: str) -> ConstructorBuilder:
        """Append member-initializer entries, e.g. ``init("m_size(size)")``."""
        self._initializers.extend(entries)
        return self

    def build(self) -> Constructor:
        return Constructor(
            params=list(self._params),
            initializers=list(self._initializers),
            body=self.body.build(),
            comment=self.comment,
            explicit=self.explicit,
            constexpr=self.constexpr,
            noexcept=self.noexcept,
            deleted=self.deleted,
            defaulted=self.defaulted,
            template=self.template,
            inline_body=self.inline_body,
            cpp_file=self.cpp_file,
        )

    def __enter__(self) -> ConstructorBuilder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class DestructorBuilder(_Builder[Destructor]):
    """A destructor under construction."""

    def __init__(
        self,
        *,
        comment: str | None = None,
        body: Code = None,
        virtual: bool = False,
        override: bool = False,
        noexcept: bool = False,
        deleted: bool = False,
        defaulted: bool = False,
        inline_body: bool = False,
        cpp_file: str | None = None,
    ) -> None:
        self.comment = comment
        self.virtual = virtual
        self.override = override
        self.noexcept = noexcept
        self.deleted = deleted
        self.defaulted = defaulted
        self.inline_body = inline_body
        self.cpp_file = cpp_file
        self.body = Body(_as_body_lines(body))

    def build(self) -> Destructor:
        return Destructor(
            body=self.body.build(),
            comment=self.comment,
            virtual=self.virtual,
            override=self.override,
            noexcept=self.noexcept,
            deleted=self.deleted,
            defaulted=self.defaulted,
            inline_body=self.inline_body,
            cpp_file=self.cpp_file,
        )

    def __enter__(self) -> DestructorBuilder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class EnumBuilder(_Builder[Lines]):
    """An enum or enum class under construction.  Renders as raw lines."""

    def __init__(
        self,
        name: str | None = None,
        *,
        underlying: str | None = None,
        scoped: bool = False,
        comment: str | None = None,
        output: Output = Output.HPP,
        cpp_file: str | None = None,
        radix: Radix = Radix.DECIMAL,
        trailing_comma: bool = True,
        comment_above: bool = False,
        qualifier: str = "",
    ) -> None:
        if underlying is not None and not scoped:
            raise ValidationError(
                "an underlying type needs a scoped enum; pass scoped=True (or use "
                "enum_class())"
            )
        if scoped and not name:
            raise ValidationError("a scoped enum needs a name")
        self.name = name
        self.underlying = underlying
        self.scoped = scoped
        self.comment = comment
        self.output = output
        self.cpp_file = cpp_file
        self.radix = radix
        self.trailing_comma = trailing_comma
        """Whether the last enumerator carries a comma.  Legal either way; F Prime
        writes one for a type's enumerators and omits it for a bare constant."""

        self.comment_above = comment_above
        """Put each enumerator's comment on its own ``//!`` line above it, rather
        than as a ``//!<`` post-comment after it.  Worth turning on when the
        comments are long enough that trailing them would run the lines out."""

        self.qualifier = qualifier
        self._constants: list[list[Line]] = []

    @property
    def type(self) -> Type:
        """This enum as a :class:`Type`, qualified for use in a source file.

        A nested enum is spelled bare inside its class but needs the class name in
        front of it in a source-file return type, which precedes ``Class::`` and so
        is not yet in the class's scope.  Pass this to ``ret=`` and both spellings
        come out right::

            status = cls.enum_class("Status", underlying="U8")
            cls.function("check", ret=status.type)
        """
        if self.name is None:
            raise ValidationError("an anonymous enum has no type name")
        return Type(self.name, f"{self.qualifier}::{self.name}" if self.qualifier else None)

    def constant(
        self,
        name: str,
        value: int | str | None = None,
        *,
        comment: str | None = None,
        radix: Radix | None = None,
    ) -> EnumBuilder:
        """Append one enumerator.

        ``value`` may be an integer, an arbitrary C++ expression, or ``None`` to let
        the compiler assign the next value.
        """
        if value is None:
            text = f"{name},"
        elif isinstance(value, int):
            spelled = (
                f"0x{value:x}" if (radix or self.radix) is Radix.HEX else str(value)
            )
            text = f"{name} = {spelled},"
        else:
            text = f"{name} = {value},"
        if comment is not None and self.comment_above:
            entry = [*write_doxygen_comment(comment)[1:], _line(text)]
        else:
            entry = add_param_comment(text, comment)
        self._constants.append(entry)
        return self

    def constants(self, *names: str) -> EnumBuilder:
        """Append several auto-numbered enumerators at once."""
        for name in names:
            self.constant(name)
        return self

    def _body(self) -> list[Line]:
        """The enumerators, with the last one's comma removed if asked."""
        entries = [list(e) for e in self._constants]
        if entries and not self.trailing_comma:
            last = entries[-1]
            last[-1] = Line(last[-1].string.rstrip(","), last[-1].indent)
        return [l for entry in entries for l in entry]

    def build(self) -> Lines:
        body = self._body()
        if self.scoped:
            assert self.name is not None
            inner = wrap_in_enum_class(
                self.name, body, self.underlying, keep_empty=True
            )
        elif self.name is not None:
            inner = wrap_in_named_enum(self.name, body, keep_empty=True)
        else:
            inner = wrap_in_enum(body, keep_empty=True)
        return Lines(
            [*write_doxygen_comment_opt(self.comment), *inner],
            self.output,
            self.cpp_file,
        )

    def __enter__(self) -> EnumBuilder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


# ----------------------------------------------------------------------
# Scopes
# ----------------------------------------------------------------------


def _source_targets(members: Sequence[object], *, in_class: bool) -> list[str | None]:
    """Which source files ``members`` contribute definitions to.

    Entries are ``cpp_file`` base names, with ``None`` standing for the document's
    default source file, in order of first appearance.  An empty result means these
    members are header-only.

    Anything that decorates a group of members -- a banner, a preprocessor guard --
    has to know this.  A single decoration pinned to no file at all lands in the
    default source file, which is wrong twice over when the members went somewhere
    else: the decoration heads nothing where it appears, and is absent where it is
    needed.
    """
    found: list[str | None] = []

    def note(target: str | None) -> None:
        if target not in found:
            found.append(target)

    def visit(items: Sequence[object]) -> None:
        for m in items:
            if isinstance(m, _Builder):
                visit(m.build_members())
            elif isinstance(m, Lines):
                if m.output is not Output.HPP and m.content:
                    note(m.cpp_file)
            elif isinstance(m, (Function, Constructor, Destructor)):
                pure = getattr(m, "sv", None) is SVQualifier.PURE_VIRTUAL
                if needs_definition(m, pure_virtual=pure) and not m.defined_in_header:
                    note(m.cpp_file)
            elif isinstance(m, Variable):
                if variable_defined_in_source(m, in_class=in_class):
                    note(m.cpp_file)
            elif isinstance(m, Class):
                # A templated class defines everything in the header.
                if m.template is None:
                    visit(m.members)

    visit(members)
    return found


def _per_file_lines(
    content: list[Line], output: Output, targets: Sequence[str | None]
) -> list[Lines]:
    """Repeat ``content`` once for the header and once per source file in ``targets``."""
    out: list[Lines] = []
    if output is not Output.CPP:
        out.append(Lines(content, Output.HPP))
    if output is not Output.HPP:
        out.extend(Lines(content, Output.CPP, target) for target in targets)
    return out


class _SectionBanner(_Builder[Lines]):
    """The banner comment heading an access section.

    Where it goes is decided at build time, once the section's contents are known.
    A header-only section -- nested types, member variables -- keeps its banner out
    of the source files entirely, rather than leaving a heading with nothing under
    it.  Otherwise the banner follows the members: normally into the default source
    file, and into the supplemental files instead when that is where the section's
    definitions actually went.
    """

    def __init__(self, comment: str) -> None:
        self.comment = comment
        self.members: list[object] = []

    def _targets(self) -> list[str | None]:
        targets = _source_targets(self.members, in_class=True)
        # A banner is decoration, so one copy is enough: prefer the default source
        # file whenever it has any of the section, and only relocate when it has
        # none.  A guard cannot do this -- see _Guard.
        if None in targets:
            return [None]
        return targets

    def build(self) -> Lines:
        return self._members()[0]

    def _members(self) -> list[Lines]:
        content = write_banner_comment(self.comment)
        return _per_file_lines(content, Output.BOTH, self._targets())

    def build_members(self) -> list[Any]:
        return list(self._members())


class _Guard:
    """A preprocessor guard bracketing a run of members.

    Unlike a banner, the guard is not decoration: code that escapes it gets
    compiled unconditionally.  So it is repeated into *every* source file that
    receives a guarded definition, not just one of them.
    """

    def __init__(self, directive: str, output: Output, *, in_class: bool) -> None:
        self.directive = directive
        self.output = output
        self.in_class = in_class
        self.members: list[object] = []

    def targets(self) -> list[str | None]:
        return _source_targets(self.members, in_class=self.in_class)

    def open_members(self) -> list[Lines]:
        if not self.members:
            return []
        return _per_file_lines(_lines(f"\n{self.directive}"), self.output, self.targets())

    def close_members(self) -> list[Lines]:
        if not self.members:
            return []
        content = [blank(), *_lines("#endif")]
        return _per_file_lines(content, self.output, self.targets())


class _GuardOpen(_Builder[Lines]):
    """Placeholder for a guard's opening directive, resolved at build time."""

    def __init__(self, guard: _Guard) -> None:
        self._guard = guard

    def build(self) -> Lines:
        members = self._guard.open_members()
        return members[0] if members else Lines([], self._guard.output)

    def build_members(self) -> list[Any]:
        return list(self._guard.open_members())


class _GuardClose(_Builder[Lines]):
    """Placeholder for a guard's ``#endif``, resolved at build time."""

    def __init__(self, guard: _Guard) -> None:
        self._guard = guard

    def build(self) -> Lines:
        members = self._guard.close_members()
        return members[0] if members else Lines([], self._guard.output)

    def build_members(self) -> list[Any]:
        return list(self._guard.close_members())


class AccessSection:
    """An access-specifier section of a class.

    The ``public:`` label goes in immediately, so ``cls.public("Interface")`` works
    on its own.  Used as a ``with`` block it also cleans up after itself: a section
    that ends up with no members takes its label and banner back out, so
    conditionally generated code does not leave a stray ``public:`` behind.
    """

    def __init__(self, scope: ClassBuilder, tag: str, comment: str | None) -> None:
        self._scope = scope
        self._count = 1
        # The label belongs to the header alone.
        scope._add(Lines(write_access_tag(tag), Output.HPP))
        self._banner: _SectionBanner | None = None
        if comment is not None:
            self._banner = scope._add(_SectionBanner(comment))
            self._count += 1
        self._start = len(scope._pending)

    def __enter__(self) -> ClassBuilder:
        return self._scope

    def __exit__(self, *exc: object) -> None:
        pending = self._scope._pending
        if len(pending) == self._start:
            del pending[self._start - self._count : self._start]
        elif self._banner is not None:
            self._banner.members = pending[self._start :]
        return None


class _Scope(_Builder[_T], Generic[_T]):
    """Shared behaviour for anything that holds an ordered list of members."""

    _in_class = False
    """Whether this scope is a class body.  Decides how a variable's declaration
    and definition are split."""

    def __init__(
        self, ctx: _DocContext | None = None, *, type_qualifier: str = ""
    ) -> None:
        self._ctx = ctx if ctx is not None else _DocContext()
        self._pending: list[object] = []
        self._type_qualifier = type_qualifier
        """How a type declared in this scope must be spelled from a source file.
        Empty at namespace scope, since a source file is written inside its
        namespace; the enclosing class chain otherwise."""

    # -- internals ----------------------------------------------------

    def _add(self, item: _T2) -> _T2:
        self._pending.append(item)
        return item

    def _resolved_cpp_file(self, cpp_file: str | None) -> str | None:
        """Fall back to the enclosing ``cpp_file`` block when none was given."""
        return cpp_file if cpp_file is not None else self._ctx.cpp_file

    def _built_members(self) -> list[Any]:
        return _resolve(self._pending)

    # -- raw content --------------------------------------------------

    def member(self, *members: object) -> None:
        """Splice in ready-made IR members or builders, in order.

        This is how output from :mod:`fprime_cpp_codegen.utils` and
        :mod:`fprime_cpp_codegen.fprime` gets in::

            cls.member(*fprime.write_ostream_operator("MyType", body))
        """
        for m in members:
            self._add(m)

    def raw(
        self,
        ll: Iterable[Line],
        *,
        output: Output = Output.HPP,
        cpp_file: str | None = None,
    ) -> None:
        """Append already-rendered lines as a member."""
        self._add(Lines(list(ll), output, self._resolved_cpp_file(cpp_file)))

    def lines(
        self,
        text: str,
        *,
        output: Output = Output.HPP,
        cpp_file: str | None = None,
    ) -> None:
        """Append a margin-stripped, possibly multi-line block of C++ as a member."""
        self.raw(_lines(text), output=output, cpp_file=cpp_file)

    def banner(
        self,
        text: str,
        *,
        output: Output = Output.BOTH,
        cpp_file: str | None = None,
    ) -> None:
        """Append a ruled banner comment, heading the members that follow.

        Unlike the banner an access section carries, this one is unconditional: it
        goes into both files unless told otherwise, because nothing here knows which
        members it is meant to be heading.
        """
        self.raw(write_banner_comment(text), output=output, cpp_file=cpp_file)

    def doc_comment(self, text: str, *, output: Output = Output.HPP) -> None:
        """Append a standalone ``//!`` doxygen comment."""
        self.raw(write_doxygen_comment(text), output=output)

    def using(
        self,
        name: str,
        target: str,
        *,
        comment: str | None = None,
        output: Output = Output.HPP,
    ) -> None:
        """Append a type alias: ``using <name> = <target>;``."""
        self.raw(
            [*write_doxygen_comment_opt(comment), *_lines(f"using {name} = {target};")],
            output=output,
        )

    # -- nested constructs -------------------------------------------

    def enum(
        self,
        name: str | None = None,
        *,
        comment: str | None = None,
        output: Output = Output.HPP,
        radix: Radix = Radix.DECIMAL,
        trailing_comma: bool = True,
        comment_above: bool = False,
    ) -> EnumBuilder:
        """Add an unscoped ``enum``, named or anonymous.

        An anonymous enum is how a header carries an integer constant without also
        needing a definition in a source file.
        """
        return self._add(
            EnumBuilder(
                name,
                comment=comment,
                output=output,
                radix=radix,
                trailing_comma=trailing_comma,
                comment_above=comment_above,
                qualifier=self._type_qualifier,
            )
        )

    def enum_class(
        self,
        name: str,
        *,
        underlying: str | None = None,
        comment: str | None = None,
        output: Output = Output.HPP,
        radix: Radix = Radix.DECIMAL,
        trailing_comma: bool = True,
        comment_above: bool = False,
    ) -> EnumBuilder:
        """Add a scoped ``enum class``, optionally with an underlying type."""
        return self._add(
            EnumBuilder(
                name,
                underlying=underlying,
                scoped=True,
                comment=comment,
                output=output,
                radix=radix,
                trailing_comma=trailing_comma,
                comment_above=comment_above,
                qualifier=self._type_qualifier,
            )
        )

    def var(
        self,
        type_name: Type | str,
        name: str,
        *,
        init: str | None = None,
        array: str | None = None,
        comment: str | None = None,
        static: bool = False,
        const: bool = False,
        constexpr: bool = False,
        mutable: bool = False,
        extern: bool = False,
        out_of_line_definition: bool = False,
        cpp_file: str | None = None,
    ) -> None:
        """Add a variable: a class data member, or a constant at namespace scope."""
        self._add(
            Variable(
                name,
                as_type(type_name),
                init=init,
                array=array,
                comment=comment,
                static=static,
                const=const,
                constexpr=constexpr,
                mutable=mutable,
                extern=extern,
                out_of_line_definition=out_of_line_definition,
                cpp_file=self._resolved_cpp_file(cpp_file),
            )
        )

    @contextmanager
    def if_directive(
        self, directive: str, *, output: Output = Output.BOTH
    ) -> Iterator[Any]:
        """Bracket the members added inside with a preprocessor guard.

        ``directive`` is written verbatim and must include its ``#``.  A guard that
        ends up with no members inside it is not emitted at all.  If the block
        raises, any members it did add are discarded.

        The guard is repeated into every source file that receives one of the
        guarded definitions, so a definition sent to a supplemental ``.cpp`` stays
        guarded there rather than escaping into an unconditional compile.
        """
        start = len(self._pending)
        try:
            yield self
        except BaseException:
            del self._pending[start:]
            raise
        if len(self._pending) == start:
            return
        guard = _Guard(directive, output, in_class=self._in_class)
        guard.members = self._pending[start:]
        self._pending.insert(start, _GuardOpen(guard))
        self._pending.append(_GuardClose(guard))

    @contextmanager
    def cpp_file(self, base: str | None) -> Iterator[Any]:
        """Send definitions created inside this block to ``<base>.cpp``.

        ``base`` is a file name without extension; ``None`` restores the document
        default.  Only definitions created *while the block is open* are affected,
        which is exactly the lexical reading.
        """
        self._ctx.cpp_files.append(base)
        try:
            yield self
        finally:
            self._ctx.cpp_files.pop()


class ClassBuilder(_Scope[Class]):
    """A class or struct under construction."""

    _in_class = True

    def __init__(
        self,
        name: str,
        *,
        extends: str | Sequence[str] | None = None,
        final: bool = False,
        comment: str | None = None,
        template: str | None = None,
        struct: bool = False,
        ctx: _DocContext | None = None,
        type_qualifier: str = "",
    ) -> None:
        if not name:
            raise ValidationError("a class needs a name")
        qualified = f"{type_qualifier}::{name}" if type_qualifier else name
        super().__init__(ctx, type_qualifier=qualified)
        self.name = name
        self.qualified_name = qualified
        """How this class is spelled from a source file: the enclosing class chain
        plus its own name.  Namespaces are not included, because a source file is
        written inside its namespace already."""

        self.extends = _extends(extends)
        self.final = final
        self.comment = comment
        self.template = template
        self.struct = struct

    @property
    def type(self) -> Type:
        """This class as a :class:`Type`, qualified for use in a source file."""
        return Type(self.name, self.qualified_name if self.qualified_name != self.name else None)

    def nested(self, name: str) -> Type:
        """A type declared inside this class, qualified for use in a source file.

        Use it for anything this class declares that the builder does not know
        about -- a typedef spelled with :meth:`using`, say::

            cls.using("Id", "U32")
            cls.function("id", ret=cls.nested("Id"), const=True)
        """
        return Type(name, f"{self.qualified_name}::{name}")

    # -- access sections ---------------------------------------------

    def public(self, comment: str | None = None) -> AccessSection:
        """Start a ``public:`` section."""
        return AccessSection(self, "public", comment)

    def protected(self, comment: str | None = None) -> AccessSection:
        """Start a ``protected:`` section."""
        return AccessSection(self, "protected", comment)

    def private(self, comment: str | None = None) -> AccessSection:
        """Start a ``private:`` section."""
        return AccessSection(self, "private", comment)

    # -- members ------------------------------------------------------

    def constructor(self, **kwargs: Any) -> ConstructorBuilder:
        """Add a constructor.  See :class:`ConstructorBuilder` for the arguments."""
        kwargs.setdefault("cpp_file", self._ctx.cpp_file)
        return self._add(ConstructorBuilder(**kwargs))

    def destructor(self, **kwargs: Any) -> DestructorBuilder:
        """Add a destructor.  See :class:`DestructorBuilder` for the arguments."""
        kwargs.setdefault("cpp_file", self._ctx.cpp_file)
        return self._add(DestructorBuilder(**kwargs))

    def function(self, name: str, **kwargs: Any) -> FunctionBuilder:
        """Add a member function.  See :class:`FunctionBuilder` for the arguments."""
        kwargs.setdefault("cpp_file", self._ctx.cpp_file)
        return self._add(FunctionBuilder(name, **kwargs))

    def class_(self, name: str, **kwargs: Any) -> ClassBuilder:
        """Add a nested class."""
        kwargs.setdefault("ctx", self._ctx)
        kwargs.setdefault("type_qualifier", self._type_qualifier)
        return self._add(ClassBuilder(name, **kwargs))

    def struct_(self, name: str, **kwargs: Any) -> ClassBuilder:
        """Add a nested struct."""
        kwargs["struct"] = True
        return self.class_(name, **kwargs)

    def friend(self, declaration: str, *, comment: str | None = None) -> None:
        """Add a ``friend`` declaration, written verbatim after the keyword."""
        self.raw(
            [
                *write_doxygen_comment_opt(comment),
                *_lines(f"friend {declaration};"),
            ]
        )

    def build(self) -> Class:
        return Class(
            self.name,
            superclass_decls=self.extends,
            members=self._built_members(),
            comment=self.comment,
            final=self.final,
            template=self.template,
            struct=self.struct,
        )

    def __enter__(self) -> ClassBuilder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _MemberScope(_Scope[_T], Generic[_T]):
    """Document and namespace scope: classes, free functions, nested namespaces."""

    def include(
        self,
        *paths: str,
        output: Output = Output.HPP,
        cpp_file: str | None = None,
    ) -> None:
        """Append quoted ``#include`` directives for project headers."""
        if not paths:
            return
        self.raw(
            [blank(), *(_line(include(p)) for p in paths)],
            output=output,
            cpp_file=cpp_file,
        )

    def system_include(
        self,
        *paths: str,
        output: Output = Output.HPP,
        cpp_file: str | None = None,
    ) -> None:
        """Append angle-bracket ``#include`` directives for system headers."""
        if not paths:
            return
        self.raw(
            [blank(), *(_line(system_include(p)) for p in paths)],
            output=output,
            cpp_file=cpp_file,
        )

    def class_(self, name: str, **kwargs: Any) -> ClassBuilder:
        """Add a class."""
        kwargs.setdefault("ctx", self._ctx)
        return self._add(ClassBuilder(name, **kwargs))

    def struct_(self, name: str, **kwargs: Any) -> ClassBuilder:
        """Add a struct."""
        kwargs["struct"] = True
        return self.class_(name, **kwargs)

    def function(self, name: str, **kwargs: Any) -> FunctionBuilder:
        """Add a free function.

        The class-only qualifiers are rejected here rather than silently producing
        code that will not compile.
        """
        for bad in ("const", "virtual", "pure_virtual", "override", "final"):
            if kwargs.get(bad):
                raise ValidationError(
                    f"{bad!r} only means something for a member function; "
                    f"{name!r} is at namespace scope"
                )
        kwargs.setdefault("cpp_file", self._ctx.cpp_file)
        return self._add(FunctionBuilder(name, **kwargs))

    def namespace(self, *names: str) -> NamespaceBuilder:
        """Add a namespace, or a chain of nested ones.

        ``namespace("Fw", "Cfg")`` opens both and returns the innermost, so members
        added to the result land in ``Fw::Cfg``.
        """
        if not names:
            raise ValidationError("namespace() needs at least one name")
        outer = NamespaceBuilder(names[0], ctx=self._ctx)
        self._add(outer)
        inner = outer
        for name in names[1:]:
            inner = inner._add(NamespaceBuilder(name, ctx=self._ctx))
        return inner

    def anonymous_namespace(self) -> NamespaceBuilder:
        """Add an unnamed namespace, giving everything in it internal linkage."""
        return self._add(NamespaceBuilder("", ctx=self._ctx))


class NamespaceBuilder(_MemberScope[Namespace]):
    """A namespace under construction."""

    def __init__(self, name: str, *, ctx: _DocContext | None = None) -> None:
        super().__init__(ctx)
        self.name = name

    def build(self) -> Namespace:
        return Namespace(self.name, self._built_members())

    def __enter__(self) -> NamespaceBuilder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class CppDocBuilder(_MemberScope[CppDoc]):
    """A whole C++ document: one header and one or more source files."""

    def __init__(
        self,
        file_base: str,
        *,
        description: str | None = None,
        include_guard: str | None = None,
        namespaces: Sequence[str] = (),
        tool_name: str | None = None,
        file_banner: FileBanner | None = None,
        hpp_extension: str = "hpp",
        cpp_extension: str = "cpp",
    ) -> None:
        """Start a document whose files are named after ``file_base``.

        ``include_guard`` defaults to one derived from ``file_base`` and
        ``namespaces``; ``namespaces`` is used for nothing else, so pass it when you
        want ``Fw_Cfg_MyClass_HPP`` without spelling the macro out.
        """
        super().__init__(_DocContext())
        if not file_base:
            raise ValidationError("a document needs a file name base")
        self.file_base = file_base
        self.description = description if description is not None else file_base
        self.hpp_extension = hpp_extension
        self.cpp_extension = cpp_extension
        self.tool_name = tool_name
        self.file_banner = file_banner
        """Overrides the ``\\title``/``\\author``/``\\brief`` block atop each file.
        Distinct from :meth:`banner`, which emits a section comment."""

        self.include_guard = (
            include_guard
            if include_guard is not None
            else _default_guard(file_base, namespaces, hpp_extension)
        )

    @property
    def hpp_name(self) -> str:
        """The header file name, e.g. ``"MyClass.hpp"``."""
        return f"{self.file_base}.{self.hpp_extension}"

    @property
    def cpp_name(self) -> str:
        """The default source file name, e.g. ``"MyClass.cpp"``."""
        return f"{self.file_base}.{self.cpp_extension}"

    def build(self) -> CppDoc:
        return CppDoc(
            description=self.description,
            hpp_file=HppFile(self.hpp_name, self.include_guard),
            cpp_file_name=self.cpp_name,
            members=self._built_members(),
            tool_name=self.tool_name,
            banner=self.file_banner,
        )

    # -- output -------------------------------------------------------

    def render_hpp(self) -> str:
        """Render the header as text."""
        return render_hpp(self.build())

    def render_cpp(self, cpp_file: str | None = None) -> str:
        """Render one source file as text.  ``None`` selects the default one."""
        return render_cpp(self.build(), cpp_file)

    def files(self, cpp_files: Sequence[str] | None = None) -> dict[str, str]:
        """Render every file this document owns, as a name-to-text mapping."""
        return doc_files(self.build(), cpp_files)

    def write(
        self,
        directory: str | Path = ".",
        cpp_files: Sequence[str] | None = None,
        *,
        skip_unchanged: bool = True,
        encoding: str = "utf-8",
    ) -> WriteResult:
        """Write every file this document owns into ``directory``.

        Supplemental source files are discovered automatically, so nothing is
        silently dropped for want of naming it here.
        """
        return write_doc(
            self.build(),
            directory,
            cpp_files,
            skip_unchanged=skip_unchanged,
            encoding=encoding,
        )

    def __enter__(self) -> CppDocBuilder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _default_guard(
    file_base: str, namespaces: Sequence[str], hpp_extension: str
) -> str:
    """Derive an include guard from the file base, namespaces and extension."""
    return include_guard(file_base, *namespaces, extension=hpp_extension.upper())
