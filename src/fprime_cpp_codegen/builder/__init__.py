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

``with`` is optional almost everywhere.  A builder attaches to its parent when you
create it, fixing its position in the output, so you can keep filling it in
afterwards::

    fn = cls.function("bump", ret="U32")
    fn.param("U32", "by", default="1")
    fn.body.line("return m_count + by;")

On access sections and preprocessor guards, ``with`` additionally makes an empty
section disappear instead of leaving a stray ``public:`` or an empty ``#if``.

A helper can build a fragment and return it for the caller to splice in with
:meth:`ClassBuilder.member`::

    def accessor(cls, name, type_name):
        fn = cls.function(f"get{name}", ret=type_name, const=True)
        fn.body.line(f"return m_{name};")

    for name, type_name in model.fields:
        accessor(cls, name, type_name)

The implementation is split across submodules: :mod:`~.base` (the builder protocol
and per-document state), :mod:`~.coercion` (argument shapes), :mod:`~.definitions`
(functions, constructors, enums), :mod:`~.decoration` (banners, guards, access
sections), :mod:`~.scopes` (classes and namespaces) and :mod:`~.document` (the
document itself).  Import from :mod:`fprime_cpp_codegen` or from here.
"""

from __future__ import annotations

from .base import BodyLike
from .decoration import AccessSection
from .definitions import (
    ConstructorBuilder,
    DestructorBuilder,
    EnumBuilder,
    FunctionBuilder,
)
from .document import CppDocBuilder
from .scopes import ClassBuilder, NamespaceBuilder

__all__ = [
    "AccessSection",
    "BodyLike",
    "ClassBuilder",
    "ConstructorBuilder",
    "CppDocBuilder",
    "DestructorBuilder",
    "EnumBuilder",
    "FunctionBuilder",
    "NamespaceBuilder",
]
