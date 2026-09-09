"""Port of FPP's constants autocoder: generate the C++ for a set of FPP constants.

A document with no class in it: constants at namespace scope.

Run it to see the generated pair::

    python examples/fpp_constants.py

or write them out::

    python examples/fpp_constants.py build-artifacts

How a constant is spelled depends on its type:

* An integer constant becomes an anonymous ``enum``, which needs no definition in a
  source file and stays usable in a constant expression.
* Anything else needs a definition, so it is declared ``extern`` in the header and
  defined in the source file.

FPP scopes a constant two ways: a ``module`` becomes a C++ namespace, while constants
inside a component or state machine -- which are not namespaces -- flatten into a
prefixed name in the enclosing scope.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from fprime_cpp_codegen import CppDocBuilder, Output


@dataclass(frozen=True)
class ConstantDef:
    """One FPP constant."""

    name: str
    value: str
    type: str | None = None
    """``None`` marks an integer constant, which becomes an enum."""

    comment: str | None = None

    @property
    def is_integer(self) -> bool:
        """Whether this constant can live in the header as an enumerator."""
        return self.type is None


@dataclass(frozen=True)
class Scope:
    """A group of constants sharing a scope."""

    constants: list[ConstantDef]
    namespace: str | None = None
    """Emit inside ``namespace <name> { ... }``.  Used for an FPP ``module``."""

    prefix: str = ""
    """Prepend to each name instead of opening a namespace, for constants inside a
    component or state machine."""


def generate(
    scopes: list[Scope], *, file_base: str = "FppConstantsAc"
) -> CppDocBuilder:
    """Generate the C++ document for ``scopes``."""
    doc = CppDocBuilder(file_base, description="FPP constants", tool_name="fpp-to-cpp")
    doc.include("Fw/Types/BasicTypes.hpp")
    doc.include(f"{file_base}.hpp", output=Output.CPP)

    for scope in scopes:
        target = doc.namespace(scope.namespace) if scope.namespace else doc
        for constant in scope.constants:
            name = f"{scope.prefix}{constant.name}"
            if constant.is_integer:
                target.enum(comment=constant.comment, trailing_comma=False).constant(
                    name, int(constant.value)
                )
            else:
                assert constant.type is not None
                target.var(
                    constant.type,
                    name,
                    init=constant.value,
                    const=True,
                    extern=True,
                    comment=constant.comment,
                )

    return doc


def numbered() -> list[ConstantDef]:
    """The five constants ``fpp-to-cpp``'s test suite declares in every scope."""
    return [
        ConstantDef("a", "0", comment="Constant a"),
        ConstantDef("b", "1.0", "F64", comment="Constant b"),
        ConstantDef("c", "true", "bool", comment="Constant c"),
        ConstantDef("d", '"abc"', "char *const", comment="Constant d"),
        ConstantDef("e", "3", comment="Constant e"),
    ]


#: The constants from ``fpp-to-cpp``'s own test suite.
EXAMPLE = [
    Scope(numbered()),
    Scope(
        [
            ConstantDef("a", "0", comment="Constant a"),
            ConstantDef("b", "1.5", "F64", comment="Constant b"),
            ConstantDef("c", "true", "bool", comment="Constant c"),
            ConstantDef("d", '"abc"', "char *const", comment="Constant d"),
            ConstantDef("e", "3", comment="Constant e"),
            ConstantDef("shifted", "65280", comment="Constant with shift"),
        ],
        namespace="M",
    ),
    # Declared inside component C, which is not a C++ namespace.
    Scope(
        [
            *numbered(),
            ConstantDef("g", "1", comment="Constant g"),
            ConstantDef("j", "3.5", "F64", comment="Constant j"),
            ConstantDef("k", "3.7", "F64", comment="Constant k"),
        ],
        prefix="C_",
    ),
    # Declared inside state machine SM, likewise.
    Scope([ConstantDef("a", "0", comment="Constant a")], prefix="SM_"),
    Scope(
        [
            ConstantDef("shiftLeft", "16", comment="Constant with left shift"),
            ConstantDef("shiftRight", "64", comment="Constant with right shift"),
        ]
    ),
]


def build() -> CppDocBuilder:
    """Build the example document."""
    return generate(EXAMPLE)


if __name__ == "__main__":
    doc = build()
    if len(sys.argv) > 1:
        for path in doc.write(sys.argv[1]).all:
            print(f"wrote {path}")
    else:
        for name, text in doc.files().items():
            print(f"===== {name} =====")
            print(text)
