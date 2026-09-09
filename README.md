# fprime-cpp-codegen

A Python package for generating C++ code for F Prime.

It builds C++ documents — one `.hpp` plus one or more `.cpp` files — through a
Builder-pattern API, where nesting in the generated C++ follows nesting in the
Python. It generates general-purpose C++: classes, structs, templates, namespaces,
enums, free functions, statements. Nothing in it knows about the FPP model, and it
has no runtime dependencies.

## Installation

```sh
pip install git+https://github.com/fprime-community/fprime-cpp-codegen.git
```

Requires Python 3.10 or newer.

## Quick start

```python
from fprime_cpp_codegen import CppDocBuilder, Output

doc = CppDocBuilder("Ring", description="a fixed-capacity ring buffer",
                    namespaces=["Demo"], tool_name="my-generator")
doc.include("Fw/FPrimeBasicTypes.hpp")
doc.include("Ring.hpp", output=Output.CPP)

with doc.namespace("Demo") as ns:
    with ns.class_("Ring", comment="A ring buffer of fixed capacity") as cls:
        with cls.public("Constructors and destructors"):
            ctor = cls.constructor(explicit=True, comment="Construct an empty ring")
            ctor.param("U32", "capacity", comment="The capacity")
            ctor.init("m_head(0)", "m_size(0)", "m_capacity(capacity)")

        with cls.public("Public member functions"):
            push = cls.function("push", ret="bool", comment="Append one item")
            push.param("U32", "item", comment="The item to append")
            with push.body as b:
                with b.if_("m_size == m_capacity"):
                    b.line("return false;")
                b.line("m_data[(m_head + m_size) % CAPACITY] = item;")
                b.line("m_size++;")
                b.line("return true;")

            cls.function("size", ret="U32", const=True, inline=True,
                         body="return m_size;", comment="How many items are stored")

        with cls.private("Member variables"):
            cls.var("U32", "CAPACITY", init="64", static=True, constexpr=True)
            cls.var("U32", "m_data", array="CAPACITY")
            cls.var("U32", "m_head")
            cls.var("U32", "m_size")
            cls.var("U32", "m_capacity", const=True)

doc.write("build-artifacts")
```

`write()` puts `Ring.hpp` and `Ring.cpp` in `build-artifacts/`, declarations in the
one and definitions in the other. `render_hpp()` / `render_cpp()` return the text
instead, and `files()` returns every file as a name-to-text mapping.

`with` is optional throughout — a builder attaches to its parent as soon as you
create it, so you can keep filling it in afterwards. It is worth using on access
sections and preprocessor guards, which delete themselves when nothing lands
inside them.

## Examples

Run any of these to print the C++ they generate, or pass a directory to write it:

```sh
python examples/ring_buffer.py           # print both files
python examples/ring_buffer.py build-dir # write them out
```

| Script                                          | What it covers                                                                                        |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| [`ring_buffer.py`](examples/ring_buffer.py)     | The class above, in full. Start here.                                                                 |
| [`fpp_constants.py`](examples/fpp_constants.py) | A document with no class in it: constants at namespace scope, split across the two files by `extern`. |
| [`fpp_enum.py`](examples/fpp_enum.py)           | A port of FPP's enum autocoder — the biggest one, and the closest to a real generator.                |

The two `fpp_*` scripts are ports of [`fpp-to-cpp`](https://github.com/nasa/fpp)'s
own autocoders, driven by a small Python data class in place of the FPP model. Both
are checked against unmodified reference output from `fpp`'s test suite, kept in
[`tests/goldens/fpp/`](tests/goldens/fpp), and reproduce it byte for byte — bar two
lines in the enum header where upstream's own indentation is inconsistent.

## Development

```sh
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python -m mypy    # strict
```

The compile-check tests need a C++ compiler on `PATH` (`g++`, `clang++` or `c++`)
and skip themselves if there is none.
