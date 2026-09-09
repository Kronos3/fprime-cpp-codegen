"""Scopes: the things that hold an ordered list of members.

A class body, a namespace, and the document itself all share the member-adding
vocabulary in :class:`_Scope`, and differ in what a member may be.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from typing import Any, Generic

from ..comments import (
    write_banner_comment,
    write_doxygen_comment,
    write_doxygen_comment_opt,
)
from ..doc import Class, Lines, Namespace, Output, Type, Variable, as_type
from ..errors import ValidationError
from ..lines import Line, blank
from ..lines import line as _line
from ..lines import lines as _lines
from ..utils import Radix, include, system_include
from .base import _Builder, _DocContext, _resolve, _T, _T2
from .coercion import _extends
from .decoration import AccessSection, _Guard, _GuardClose, _GuardOpen
from .definitions import (
    ConstructorBuilder,
    DestructorBuilder,
    EnumBuilder,
    FunctionBuilder,
)


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
        """How a type declared in this scope is spelled from a source file: the
        enclosing class chain, or empty at namespace scope."""

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

        Takes output from :mod:`fprime_cpp_codegen.utils` and
        :mod:`fprime_cpp_codegen.fprime`::

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

        Unconditional: it goes into both files unless ``output`` says otherwise.  An
        access section's banner instead follows its members.
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

        An anonymous enum carries an integer constant in the header without needing a
        definition in a source file.
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
    ) -> Generator[Any]:
        """Bracket the members added inside with a preprocessor guard.

        ``directive`` is written verbatim and must include its ``#``.  A guard with no
        members inside it is not emitted, and a block that raises discards whatever
        it added.

        The guard is repeated into every source file receiving one of the guarded
        definitions, so a definition sent to a supplemental ``.cpp`` stays guarded
        there.
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
    def cpp_file(self, base: str | None) -> Generator[Any]:
        """Send definitions created inside this block to ``<base>.cpp``.

        ``base`` is a file name without extension; ``None`` restores the document
        default.  Only definitions created while the block is open are affected.
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
        plus its own name.  Namespaces are excluded, since a source file is written
        inside its namespace."""

        self.extends = _extends(extends)
        self.final = final
        self.comment = comment
        self.template = template
        self.struct = struct

    @property
    def type(self) -> Type:
        """This class as a :class:`Type`, qualified for use in a source file."""
        return Type(
            self.name, self.qualified_name if self.qualified_name != self.name else None
        )

    def nested(self, name: str) -> Type:
        """A type declared inside this class, qualified for use in a source file.

        For anything this class declares that the builder does not know about, such as
        an alias from :meth:`using`::

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
        """Add a free function.  The class-only qualifiers are rejected here."""
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
