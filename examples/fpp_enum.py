"""Port of FPP's enum autocoder: generate the C++ for an F Prime enum type.

This mirrors what ``fpp-to-cpp`` produces for an FPP ``enum`` definition -- the
same shape as its ``EnumCppWriter``, but driven by a small Python data class
instead of an FPP model.  It is the largest thing in this repository that exercises
the API, and a good place to look for how a real generator is put together.

Run it to see the generated pair::

    python examples/fpp_enum.py

or write them out::

    python examples/fpp_enum.py build-artifacts

What it demonstrates:

* a class deriving from ``Fw::Serializable``, with seven access sections
* ``using`` aliases, a raw unscoped ``enum``, and an anonymous ``enum`` of constants
* constructors defined inline in the header
* a conversion operator, which has no return type at all
* operators defined out of line in the source file
* ``#ifdef BUILD_UT`` and ``#if FW_SERIALIZABLE_TO_STRING`` guards, both around
  whole members and around a few statements inside a body
* a friend ``operator<<`` declared in the header and defined in the source
* member variables with in-class initialisers and multi-line comments
* a ``switch`` in the compact brace-less style F Prime autocode uses
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from fprime_cpp_codegen import (
    ClassBuilder,
    CppDocBuilder,
    Line,
    Output,
    Type,
    fprime,
    lines,
)


@dataclass(frozen=True)
class Constant:
    """One enumerated constant of the FPP enum."""

    name: str
    value: int


@dataclass(frozen=True)
class EnumModel:
    """The bits of an FPP enum definition this generator needs.

    Standing in for the FPP model, so the generator below has the shape it would
    have in a real tool without depending on one.
    """

    name: str
    constants: list[Constant]
    comment: str | None = None
    serial_type: str = "I32"
    """The C++ integer type the enum serializes as."""

    format_specifier: str = "PRIi32"
    """The ``inttypes.h`` macro matching :attr:`serial_type`."""

    namespaces: list[str] = field(default_factory=list)

    @property
    def file_base(self) -> str:
        """The generated file name base, e.g. ``"EEnumAc"``."""
        return f"{self.name}EnumAc"

    @property
    def is_contiguous(self) -> bool:
        """Whether the values form one unbroken run, so validity is a range test."""
        values = sorted(c.value for c in self.constants)
        return bool(values) and values == list(
            range(values[0], values[0] + len(values))
        )


def generate(model: EnumModel) -> CppDocBuilder:
    """Generate the C++ document for ``model``."""
    doc = CppDocBuilder(
        model.file_base,
        description=f"{model.name} enum",
        namespaces=model.namespaces,
        tool_name="fpp-to-cpp",
    )

    doc.include(
        "Fw/FPrimeBasicTypes.hpp",
        "Fw/Types/Assert.hpp",
        "Fw/Types/Serializable.hpp",
        "Fw/Types/String.hpp",
    )
    doc.system_include("cstring", "limits", output=Output.CPP)
    doc.include(f"{model.file_base}.hpp", output=Output.CPP)

    scope = doc.namespace(*model.namespaces) if model.namespaces else doc
    with scope.class_(
        model.name, extends="public Fw::Serializable", comment=model.comment
    ) as cls:
        types(cls, model)
        constants(cls, model)
        constructors(cls, model)
        operators(cls, model)
        member_functions(cls, model)
        static_functions(cls, model)
        member_variables(cls, model)

    return doc


def types(cls: ClassBuilder, model: EnumModel) -> None:
    """The serial representation alias, the raw enum, and the legacy alias."""
    with cls.public("Types"):
        cls.using(
            "SerialType", model.serial_type, comment="The serial representation type"
        )
        raw = cls.enum("T", comment="The raw enum type")
        for constant in model.constants:
            raw.constant(constant.name, constant.value)
        cls.using("t", "enum T", comment="For backwards compatibility")


def constants(cls: ClassBuilder, model: EnumModel) -> None:
    """Sizes and counts, as an anonymous enum so no definition is needed."""
    with cls.public("Constants"):
        sizes = cls.enum(comment_above=True)
        sizes.constant(
            "SERIALIZED_SIZE",
            "sizeof(SerialType)",
            comment="The size of the serial representation",
        )
        sizes.constant(
            "NUM_CONSTANTS",
            len(model.constants),
            comment="The number of enumerated constants",
        )


def constructors(cls: ClassBuilder, model: EnumModel) -> None:
    """Four constructors, all defined inline in the header."""
    default_value = model.constants[0].name
    with cls.public("Constructors"):
        cls.constructor(
            comment=f"Constructor (default value of {default_value})",
            inline_body=True,
            body=f"this->e = {default_value};",
        )

        raw = cls.constructor(
            comment="Constructor (user-provided value)", inline_body=True
        )
        raw.param("const enum T", "e1", comment="The raw enum value")
        raw.body.add(assert_valid("e1"), "this->e = e1;")

        serial = cls.constructor(
            comment="Constructor (serial representation value)", inline_body=True
        )
        serial.param(
            "const SerialType", "e1", comment="The serial representation value"
        )
        serial.body.add(assert_valid("e1"), "this->e = static_cast<enum T>(e1);")

        copy = cls.constructor(comment="Copy constructor", inline_body=True)
        copy.param(f"const {model.name}&", "obj", comment="The source object")
        copy.body.line("this->e = obj.e;")
        with copy.body.if_directive(fprime.BUILD_UT, spaced=False):
            copy.body.line("this->m_serializeValueIsSet = obj.m_serializeValueIsSet;")
            copy.body.line("this->m_serializeValue = obj.m_serializeValue;")


def operators(cls: ClassBuilder, model: EnumModel) -> None:
    """Assignment, conversion, comparison, and the unit-test ostream operator."""
    name = model.name
    reference = f"{name}&"
    with cls.public("Operators"):
        assign_obj = cls.function(
            "operator=", ret=reference, comment="Copy assignment operator (object)"
        )
        assign_obj.param(f"const {name}&", "obj", comment="The source object")
        assign_obj.body.line("this->e = obj.e;")
        with assign_obj.body.if_directive(fprime.BUILD_UT, spaced=False):
            assign_obj.body.line(
                "this->m_serializeValueIsSet = obj.m_serializeValueIsSet;"
            )
            assign_obj.body.line("this->m_serializeValue = obj.m_serializeValue;")
        assign_obj.body.line("return *this;")

        # Upstream's wording is not quite uniform across these two, so carry it
        # verbatim rather than deriving it.
        assignments = (
            (
                "SerialType",
                "The serial representation value",
                "static_cast<enum T>(e1)",
                "Assignment operator (serial representation value)",
            ),
            ("enum T", "The enum value", "e1", "Copy assignment operator (raw enum)"),
        )
        for param_type, param_comment, conversion, comment in assignments:
            fn = cls.function("operator=", ret=reference, comment=comment)
            fn.param(param_type, "e1", comment=param_comment)
            fn.body.add(assert_valid("e1"), f"this->e = {conversion};")
            with fn.body.if_directive(fprime.BUILD_UT, spaced=False):
                fn.body.line("this->m_serializeValueIsSet = false;")
                fn.body.line("this->m_serializeValue = 0;")
            fn.body.line("return *this;")

        # A conversion operator names its type instead of returning one, so there
        # is no return type to write.
        cls.function(
            "operator enum T",
            ret=Type(""),
            const=True,
            inline_body=True,
            comment="Conversion operator",
            body="return this->e;",
        )
        cls.function(
            "operator==",
            ret="bool",
            params=[("enum T", "e1")],
            const=True,
            inline_body=True,
            comment="Equality operator",
            body="return this->e == e1;",
        )
        cls.function(
            "operator!=",
            ret="bool",
            params=[("enum T", "e1")],
            const=True,
            inline_body=True,
            comment="Inequality operator",
            body="return !(*this == e1);",
        )
        cls.member(
            *fprime.write_ostream_operator(
                name,
                lines("""|Fw::String s;
                       |obj.toString(s);
                       |os << s;
                       |return os;"""),
            )
        )


def member_functions(cls: ClassBuilder, model: EnumModel) -> None:
    """Validity, serialization, stringification, and the unit-test override."""
    name = model.name
    buffer_param = ("Fw::SerialBufferBase&", "buffer", "The serial buffer")
    mode_param = (
        "Fw::Endianness",
        "mode",
        "Endianness of serialized buffer",
        "Fw::Endianness::BIG",
    )
    with cls.public("Member functions"):
        cls.function(
            "isValid",
            ret="bool",
            const=True,
            comment="Check raw enum value for validity",
            body=f"return {name}::isValid(this->e);",
        )

        serialize = cls.function(
            "serializeTo",
            ret="Fw::SerializeStatus",
            const=True,
            comment="Serialize raw enum value to SerialType",
            params=[buffer_param, mode_param],
        )
        with serialize.body as b:
            b.line("SerialType es = static_cast<SerialType>(this->e);")
            with b.if_directive(fprime.BUILD_UT, spaced=False):
                b.comment(
                    "Unit testing only: On request, override the enum value\n"
                    "with the numeric value, which is allowed to be invalid"
                )
                with b.if_("this->m_serializeValueIsSet"):
                    b.line("es = this->m_serializeValue;")
            b.line("const Fw::SerializeStatus status = buffer.serializeFrom(es, mode);")
            b.line("return status;")

        deserialize = cls.function(
            "deserializeFrom",
            ret="Fw::SerializeStatus",
            comment="Deserialize raw enum value from SerialType",
            params=[buffer_param, mode_param],
        )
        with deserialize.body as b:
            b.line("SerialType es;")
            b.line("Fw::SerializeStatus status = buffer.deserializeTo(es, mode);")
            with b.if_(f"(status == Fw::FW_SERIALIZE_OK) && !{name}::isValid(es)"):
                b.line("status = Fw::FW_DESERIALIZE_FORMAT_ERROR;")
            with b.if_("status == Fw::FW_SERIALIZE_OK"):
                b.line("this->e = static_cast<enum T>(es);")
            b.line("return status;")

        with cls.if_directive("#if FW_SERIALIZABLE_TO_STRING"):
            to_string = cls.function(
                "toString",
                const=True,
                comment="Convert enum to string",
                params=[
                    (
                        "Fw::StringBase&",
                        "sb",
                        "The StringBase object to hold the result",
                    )
                ],
            )
            with to_string.body as b:
                b.line("Fw::String s;")
                with b.switch("e") as sw:
                    for constant in model.constants:
                        with sw.case(constant.name, braces=False):
                            b.line(f's = "{constant.name}";')
                    with sw.default(braces=False):
                        b.line('s = "[invalid]";')
                b.line(
                    f'sb.format("%s (%" {model.format_specifier} ")", s.toChar(), e);'
                )

        with cls.if_directive(fprime.BUILD_UT):
            setter = cls.function(
                "setSerializeValue",
                comment="Set the value to use for serialization (unit testing only)",
                params=[("SerialType", "serializeValue", "The serialize value")],
            )
            setter.body.line("this->m_serializeValue = serializeValue;")
            setter.body.line("this->m_serializeValueIsSet = true;")


def static_functions(cls: ClassBuilder, model: EnumModel) -> None:
    """The static validity check: a range test when the values are contiguous."""
    names = [c.name for c in model.constants]
    if model.is_contiguous:
        check = f"(serialTypeValue >= {names[0]}) && (serialTypeValue <= {names[-1]})"
    else:
        check = " || ".join(f"(serialTypeValue == {n})" for n in names)

    with cls.public("Static functions"):
        cls.function(
            "isValid",
            ret="bool",
            static=True,
            comment="Check serial type value for validity",
            params=[("SerialType", "serialTypeValue", "The serial type value")],
            body=f"return ({check});",
        )


def member_variables(cls: ClassBuilder, model: EnumModel) -> None:
    """The public raw value, and the private unit-test serialization override."""
    with cls.public("Public member variables"):
        cls.var("enum T", "e", comment="The raw enum value")

    with cls.private("Private member variables"):
        with cls.if_directive(fprime.BUILD_UT):
            cls.var(
                "bool",
                "m_serializeValueIsSet",
                init="false",
                comment=(
                    "Whether the serialize value is set (unit testing only).\n"
                    "When this flag is set to true, the serializeTo function\n"
                    "uses the serialize value instead of the raw enum value\n"
                    "when serializing the enum instance. This allows serialization\n"
                    "of invalid values that can't be represented as the raw enum type."
                ),
            )
            cls.var(
                "SerialType",
                "m_serializeValue",
                init="0",
                comment="The serialize value",
            )


def assert_valid(expression: str) -> list[Line]:
    """``FW_ASSERT`` that ``expression`` is a valid value for this enum."""
    return fprime.write_assert(
        f"isValid({expression})", f"static_cast<FwAssertArgType>({expression})"
    )


#: The enum from ``fpp-to-cpp``'s own test suite: ``enum E { X, Y }``.
EXAMPLE = EnumModel(
    name="E",
    comment="An identical enum outside the component",
    constants=[Constant("X", 0), Constant("Y", 1)],
)


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
