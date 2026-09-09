"""The example autocoder ports against ``fpp-to-cpp``'s own reference output.

``tests/goldens/fpp/`` holds unmodified reference files from the native ``fpp``
compiler's test suite.  The generated C++ is also compiled against the stub headers in
:mod:`tests.conftest`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import FPRIME_STUB_HEADERS, assert_compiles
from .test_examples import load

REFERENCES = Path(__file__).resolve().parent / "goldens" / "fpp"


def reference(name: str) -> str:
    """Read one of the unmodified ``fpp-to-cpp`` reference files."""
    return (REFERENCES / name).read_text()


def assert_identical(generated: str, ref_name: str) -> None:
    """Assert the generated text matches the reference byte for byte."""
    expected = reference(ref_name)
    if generated != expected:
        import difflib

        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                generated.splitlines(),
                fromfile=f"fpp-to-cpp/{ref_name}",
                tofile="generated",
                lineterm="",
            )
        )
        pytest.fail(f"{ref_name} does not match fpp-to-cpp output:\n\n{diff}")


def assert_identical_but_for_indent(
    generated: str, ref_name: str, indent_only_lines: list[int]
) -> None:
    """Assert the only differences are indentation, on exactly the lines given.

    Fails if anything else differs, or if these lines stop differing.
    """
    expected = reference(ref_name).splitlines()
    actual = generated.splitlines()
    assert len(actual) == len(expected), "line counts differ"
    differing = [n for n, (a, b) in enumerate(zip(actual, expected), 1) if a != b]
    assert (
        differing == indent_only_lines
    ), f"unexpected differences on lines {differing}"
    for n in differing:
        assert (
            actual[n - 1].strip() == expected[n - 1].strip()
        ), f"line {n} differs by more than indentation"


class TestEnumPort:
    """``examples/fpp_enum.py`` against ``EEnumAc.ref.*``."""

    def test_source_is_identical_to_fpp_output(self) -> None:
        assert_identical(load("fpp_enum").build().render_cpp(), "EEnumAc.ref.cpp")

    def test_header_differs_only_in_two_indents(self) -> None:
        # The reference indents the BUILD_UT block inside the inline copy constructor
        # to four spaces while the statements around it sit at six.
        assert_identical_but_for_indent(
            load("fpp_enum").build().render_hpp(), "EEnumAc.ref.hpp", [88, 89]
        )

    def test_generated_files_compile(self) -> None:
        assert_compiles(
            load("fpp_enum").build().files(),
            stubs={**FPRIME_STUB_HEADERS, **FW_TYPE_STUBS},
        )

    def test_generated_files_compile_with_the_guards_enabled(self) -> None:
        # Without these defines the guarded blocks are never compiled at all.
        assert_compiles(
            load("fpp_enum").build().files(),
            stubs={**FPRIME_STUB_HEADERS, **FW_TYPE_STUBS},
            defines=["BUILD_UT", "FW_SERIALIZABLE_TO_STRING=1"],
        )

    def test_a_non_contiguous_enum_uses_equality_tests(self) -> None:
        module = load("fpp_enum")
        model = module.EnumModel(
            name="Sparse",
            constants=[
                module.Constant("A", 1),
                module.Constant("B", 4),
            ],
        )
        hpp = module.generate(model).render_hpp()
        cpp = module.generate(model).render_cpp()
        assert "NUM_CONSTANTS = 2," in hpp
        assert "(serialTypeValue == A) || (serialTypeValue == B)" in cpp

    def test_namespaces_wrap_the_class_and_shape_the_guard(self) -> None:
        module = load("fpp_enum")
        model = module.EnumModel(
            name="E",
            constants=[module.Constant("X", 0)],
            namespaces=["Fw", "Cfg"],
        )
        doc = module.generate(model)
        hpp = doc.render_hpp()
        assert doc.include_guard == "Fw_Cfg_EEnumAc_HPP"
        assert hpp.index("namespace Fw {") < hpp.index("namespace Cfg {")
        assert hpp.index("namespace Cfg {") < hpp.index("class E :")


class TestConstantsPort:
    """``examples/fpp_constants.py`` against ``FppConstantsAc.ref.*``."""

    def test_header_is_identical_to_fpp_output(self) -> None:
        assert_identical(
            load("fpp_constants").build().render_hpp(), "FppConstantsAc.ref.hpp"
        )

    def test_source_is_identical_to_fpp_output(self) -> None:
        assert_identical(
            load("fpp_constants").build().render_cpp(), "FppConstantsAc.ref.cpp"
        )

    def test_generated_files_compile(self) -> None:
        assert_compiles(
            load("fpp_constants").build().files(), stubs=FW_BASIC_TYPE_STUBS
        )

    def test_an_integer_constant_stays_in_the_header(self) -> None:
        module = load("fpp_constants")
        doc = module.generate(
            [module.Scope([module.ConstantDef("SIZE", "10", comment="The size")])]
        )
        assert "SIZE = 10" in doc.render_hpp()
        assert "SIZE" not in doc.render_cpp()

    def test_a_typed_constant_is_split_across_the_files(self) -> None:
        module = load("fpp_constants")
        doc = module.generate(
            [module.Scope([module.ConstantDef("RATE", "1.5", "F64")])]
        )
        assert "extern const F64 RATE;" in doc.render_hpp()
        assert "const F64 RATE = 1.5;" in doc.render_cpp()


#: Just enough of ``Fw/Types/BasicTypes.hpp`` to compile generated constants.
FW_BASIC_TYPE_STUBS = {
    "Fw/Types/BasicTypes.hpp": (
        "#ifndef FW_BASIC_TYPES_HPP\n"
        "#define FW_BASIC_TYPES_HPP\n"
        "typedef double F64;\n"
        "#endif\n"
    ),
}

#: Just enough of the F Prime serialization surface to compile a generated enum.
FW_TYPE_STUBS = {
    "Fw/Types/Assert.hpp": (
        "#ifndef FW_ASSERT_HPP\n"
        "#define FW_ASSERT_HPP\n"
        "typedef long FwAssertArgType;\n"
        "#define FW_ASSERT(...) ((void) 0)\n"
        "#endif\n"
    ),
    "Fw/Types/Serializable.hpp": (
        "#ifndef FW_SERIALIZABLE_HPP\n"
        "#define FW_SERIALIZABLE_HPP\n"
        "namespace Fw {\n"
        "  enum SerializeStatus { FW_SERIALIZE_OK, FW_DESERIALIZE_FORMAT_ERROR };\n"
        "  enum class Endianness { BIG, LITTLE };\n"
        "  class StringBase;\n"
        "  class SerialBufferBase {\n"
        "    public:\n"
        "      template <typename T>\n"
        "      SerializeStatus serializeFrom(const T&, Endianness) { return FW_SERIALIZE_OK; }\n"
        "      template <typename T>\n"
        "      SerializeStatus deserializeTo(T&, Endianness) { return FW_SERIALIZE_OK; }\n"
        "  };\n"
        "  class Serializable {\n"
        "    public:\n"
        "      virtual ~Serializable() {}\n"
        "  };\n"
        "}\n"
        "#endif\n"
    ),
    "Fw/Types/String.hpp": (
        "#ifndef FW_STRING_HPP\n"
        "#define FW_STRING_HPP\n"
        "#include <cinttypes>\n"
        "#include <ostream>\n"
        "namespace Fw {\n"
        "  class StringBase {\n"
        "    public:\n"
        "      virtual ~StringBase() {}\n"
        "      const char* toChar() const { return m_buf; }\n"
        "      void format(const char*, ...) {}\n"
        "      char m_buf[64] = {0};\n"
        "  };\n"
        "  class String : public StringBase {\n"
        "    public:\n"
        "      String& operator=(const char*) { return *this; }\n"
        "  };\n"
        "  inline std::ostream& operator<<(std::ostream& os, const StringBase& s) {\n"
        "    return os << s.toChar();\n"
        "  }\n"
        "}\n"
        "#endif\n"
    ),
}
