"""The C++ document IR: one ``.hpp`` file plus one or more ``.cpp`` files.

This is the layer the writers consume.  You can build it by hand -- it is a plain
tree of frozen dataclasses -- but :mod:`fprime_cpp_codegen.builder` is the
comfortable way in.

A single :class:`CppDoc` describes a header and *any number* of source files.
Every definition that has a body (function, constructor, destructor) and every
block of raw lines can name the ``.cpp`` file it belongs to via ``cpp_file``;
definitions that name nothing land in the document's default ``.cpp``.  The header
always gets everything.  That is how a generator splits one large class across
several translation units without duplicating its declaration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Union, runtime_checkable

from .lines import Line

__all__ = [
    "VOID",
    "Class",
    "ClassMember",
    "Constructor",
    "CppDoc",
    "DefaultFileBanner",
    "Definition",
    "Destructor",
    "FileBanner",
    "Function",
    "HppFile",
    "Lines",
    "Member",
    "Namespace",
    "Output",
    "Param",
    "SVQualifier",
    "Type",
    "Variable",
    "as_type",
]


class Output(Enum):
    """Which of a document's files a block of raw lines is emitted into."""

    HPP = "hpp"
    """Header only."""

    CPP = "cpp"
    """Source only."""

    BOTH = "both"
    """Both the header and the source."""


class SVQualifier(Enum):
    """A function's static/virtual specifier.

    These are mutually exclusive by construction, which is the point: it is not
    possible to ask for ``static override``.  ``OVERRIDE`` and ``FINAL`` render as
    trailing specifiers; ``STATIC``, ``VIRTUAL`` and ``PURE_VIRTUAL`` render as
    leading ones.  ``PURE_VIRTUAL`` also terminates the declaration with ``= 0``.
    """

    NONE = "none"
    STATIC = "static"
    VIRTUAL = "virtual"
    PURE_VIRTUAL = "pure-virtual"
    OVERRIDE = "override"
    FINAL = "final"


@dataclass(frozen=True)
class Type:
    """A C++ type.

    The spelling in the source file may need to differ from the spelling in the
    header -- typically because the header sits inside the namespace that
    qualifies the name and the source file does not.  ``cpp_type`` supplies that
    alternative spelling; when it is absent both files use ``hpp_type``.
    """

    hpp_type: str
    cpp_type: str | None = None

    @property
    def cpp(self) -> str:
        """The spelling to use in a ``.cpp`` file."""
        return self.cpp_type if self.cpp_type is not None else self.hpp_type

    @property
    def hpp(self) -> str:
        """The spelling to use in the ``.hpp`` file."""
        return self.hpp_type


#: The ``void`` type, and the default return type of a :class:`Function`.
VOID = Type("void")


def as_type(t: Type | str | tuple[str, str]) -> Type:
    """Coerce a type specification to a :class:`Type`.

    A single string is used in both files.  A ``(header, source)`` pair supplies
    the two spellings, which is what a nested type needs: ``Status`` inside the
    class, ``MyClass::Status`` in the source file where the return type precedes
    ``MyClass::``.
    """
    if isinstance(t, Type):
        return t
    if isinstance(t, tuple):
        hpp, cpp = t
        return Type(hpp, cpp)
    return Type(t)


@dataclass(frozen=True)
class Param:
    """A formal parameter of a function, constructor, or destructor."""

    type: Type
    name: str
    comment: str | None = None
    """A doxygen post-comment, rendered after the parameter in the header."""

    default: str | None = None
    """A default argument, rendered in the header declaration only."""


@dataclass(frozen=True)
class Lines:
    """A block of raw, already-rendered C++ lines.

    This is the escape hatch, and it is used heavily: access tags, banner
    comments, ``#include`` directives, member variable declarations, enums and
    structs are all just lines.  ``output`` decides which files see them.
    """

    content: list[Line] = field(default_factory=list)
    output: Output = Output.HPP
    cpp_file: str | None = None
    """Restrict source-file output to this ``.cpp`` base name.  Header output is
    unaffected."""


@dataclass(frozen=True, kw_only=True)
class Definition:
    """Fields shared by everything that has a body: where it goes, and whether.

    These are keyword-only so that subclasses can still take their own defining
    field -- a function's name, say -- as the first positional argument.

    ``deleted`` and ``defaulted`` replace the body with ``= delete`` or
    ``= default``; ``inline_body`` and ``template`` move the definition into the
    header, since a template's definition has to be visible at every use.  In all
    four cases the source file gets nothing.
    """

    body: list[Line] = field(default_factory=list)
    comment: str | None = None
    cpp_file: str | None = None
    """Which ``.cpp`` file the definition goes in.  ``None`` means the default."""

    noexcept: bool = False
    deleted: bool = False
    defaulted: bool = False
    inline_body: bool = False
    """Define in the header rather than the source file."""

    template: str | None = None
    """A template parameter list without the keyword, e.g. ``"typename T"``.
    Implies :attr:`inline_body`."""

    @property
    def defined_in_header(self) -> bool:
        """Whether this definition belongs in the header rather than a source file."""
        return self.inline_body or self.template is not None

    @property
    def has_definition(self) -> bool:
        """Whether there is a body to write at all."""
        return not (self.deleted or self.defaulted)


@dataclass(frozen=True)
class Function(Definition):
    """A C++ function, either free-standing or a class member."""

    name: str
    params: list[Param] = field(default_factory=list)
    ret_type: Type = VOID
    """A return type of ``Type("")`` emits no return type at all, which is how
    constructors of nested helper types and conversion operators are written."""

    sv: SVQualifier = SVQualifier.NONE
    const: bool = False
    constexpr: bool = False
    inline: bool = False

    @property
    def defined_in_header(self) -> bool:
        """Whether this definition belongs in the header rather than a source file.

        ``constexpr`` and ``inline`` force it there: both require the definition to
        be visible in every translation unit that uses the function, so putting it
        in a single ``.cpp`` would produce link errors.
        """
        return super().defined_in_header or self.constexpr or self.inline


@dataclass(frozen=True)
class Constructor(Definition):
    """A C++ constructor.  Its name is taken from the enclosing class."""

    params: list[Param] = field(default_factory=list)
    initializers: list[str] = field(default_factory=list)
    """Member-initializer-list entries, e.g. ``"m_size(size)"``.  Rendered wherever
    the definition goes, which is the source file unless it is inlined."""

    explicit: bool = False
    constexpr: bool = False

    @property
    def defined_in_header(self) -> bool:
        """Whether this definition belongs in the header rather than a source file."""
        return super().defined_in_header or self.constexpr


@dataclass(frozen=True)
class Destructor(Definition):
    """A C++ destructor.  Its name is taken from the enclosing class."""

    virtual: bool = False
    override: bool = False


@dataclass(frozen=True)
class Class:
    """A C++ class, possibly nested inside another class."""

    name: str
    superclass_decls: str | None = None
    """Everything after the colon, verbatim, e.g. ``"public Fw::Serializable"``.
    Multiple bases go in one string separated by commas."""

    members: list[ClassMember] = field(default_factory=list)
    comment: str | None = None
    final: bool = False
    template: str | None = None
    """A template parameter list without the keyword, e.g. ``"typename T"``.  A
    templated class defines all of its members in the header, so its source file
    output is empty."""

    struct: bool = False
    """Emit ``struct`` instead of ``class``, making members public by default."""


@dataclass(frozen=True)
class Variable:
    """A variable: a class data member, or a constant or global at namespace scope.

    Where the initialiser goes depends on what kind of variable this is, because
    C++ is particular about it:

    * A non-static data member takes its initialiser in the class body.
    * A static data member is only *declared* in the class; the definition, with
      the initialiser, goes in a source file.  A ``constexpr`` static is the
      exception -- it is initialised in the class, and needs no out-of-line
      definition unless something takes its address, which is what
      ``out_of_line_definition`` is for.
    * At namespace scope, ``extern`` splits the declaration from the definition the
      same way.  Without it the variable is defined where it is declared, which is
      what you want for a ``constexpr`` or ``const`` constant in a header.
    """

    name: str
    type: Type
    init: str | None = None
    array: str | None = None
    """An array extent, without brackets, e.g. ``"SIZE"`` for ``m_data[SIZE]``."""

    comment: str | None = None
    static: bool = False
    const: bool = False
    constexpr: bool = False
    mutable: bool = False
    extern: bool = False
    out_of_line_definition: bool = False
    """Emit a source-file definition for a ``constexpr`` static member as well."""

    cpp_file: str | None = None

    @property
    def declarator(self) -> str:
        """The name plus any array extent, e.g. ``"m_data[SIZE]"``."""
        return f"{self.name}[{self.array}]" if self.array is not None else self.name


@dataclass(frozen=True)
class Namespace:
    """A C++ namespace.  Nest instances to nest namespaces."""

    name: str
    members: list[Member] = field(default_factory=list)


#: What may appear at document or namespace scope.
Member = Union[Class, Lines, Function, Namespace, Variable]

#: What may appear at class scope.  Namespaces may not; constructors and
#: destructors may.
ClassMember = Union[Class, Lines, Function, Constructor, Destructor, Variable]


@runtime_checkable
class FileBanner(Protocol):
    """Supplies the ``\\title``/``\\author``/``\\brief`` lines atop each file.

    Implement this to take ownership of the banner -- for instance to write the
    invoking user as the author of a template file whose ownership passes to them
    once copied, which is what the F Prime tools do.
    """

    def title(self, file_name: str) -> str:
        """The ``\\title`` text for ``file_name``."""
        ...

    def author(self, file_name: str) -> str:
        """The ``\\author`` text for ``file_name``."""
        ...

    def description(self, file_name: str, generic_description: str) -> str:
        """The ``\\brief`` text for ``file_name``.

        ``generic_description`` is the writer's own phrasing, e.g.
        ``"hpp file for my component"``.
        """
        ...


@dataclass(frozen=True)
class DefaultFileBanner:
    """The banner used when a document does not supply one."""

    tool_name: str | None = None

    def title(self, file_name: str) -> str:
        return file_name

    def author(self, file_name: str) -> str:
        return f"Generated by {self.tool_name or 'fpp tools'}"

    def description(self, file_name: str, generic_description: str) -> str:
        return generic_description


@dataclass(frozen=True)
class HppFile:
    """The header file of a document."""

    name: str
    """The file name including extension, e.g. ``"MyClass.hpp"``."""

    include_guard: str
    """The include-guard macro, e.g. ``"Fw_MyClass_HPP"``."""


@dataclass(frozen=True)
class CppDoc:
    """A C++ document: one header, one default source file, and the members."""

    description: str
    """Used in the file banners, as ``"hpp file for <description>"``."""

    hpp_file: HppFile
    cpp_file_name: str
    """The default source file name including extension, e.g. ``"MyClass.cpp"``."""

    members: list[Member] = field(default_factory=list)
    tool_name: str | None = None
    banner: FileBanner | None = None

    @property
    def file_banner(self) -> FileBanner:
        """The document's banner, falling back to :class:`DefaultFileBanner`."""
        return self.banner if self.banner is not None else DefaultFileBanner(self.tool_name)
