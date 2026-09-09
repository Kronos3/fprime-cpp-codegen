"""Generate a small C++ class: a fixed-capacity ring buffer.

Run it to write ``Ring.hpp`` and ``Ring.cpp`` into a directory of your choosing::

    python examples/ring_buffer.py build-artifacts
"""

from __future__ import annotations

import sys

from fprime_cpp_codegen import CppDocBuilder, Output


def build() -> CppDocBuilder:
    """Build the ring-buffer document."""
    doc = CppDocBuilder(
        "Ring",
        description="a fixed-capacity ring buffer",
        namespaces=["Demo"],
        tool_name="ring-buffer-example",
    )
    doc.include("Fw/FPrimeBasicTypes.hpp")
    doc.include("Ring.hpp", output=Output.CPP)

    with doc.namespace("Demo") as ns:
        with ns.class_("Ring", comment="A ring buffer of fixed capacity") as cls:
            with cls.public("Types"):
                status = cls.enum_class(
                    "Status", underlying="U8", comment="The result of an operation"
                )
                status.constant("OK", 0, comment="The item was stored")
                status.constant("FULL", 1, comment="The buffer is at capacity")

            with cls.public("Constructors and destructors"):
                ctor = cls.constructor(explicit=True, comment="Construct an empty ring")
                ctor.param("U32", "capacity", comment="The capacity, at most CAPACITY")
                ctor.init("m_head(0)", "m_size(0)", "m_capacity(capacity)")

                cls.constructor(
                    params=[("const Ring&", "other")],
                    deleted=True,
                    comment="Copying a ring is not supported",
                )
                cls.destructor(defaulted=True)

            with cls.public("Public member functions"):
                push = cls.function("push", ret=status.type, comment="Append one item")
                push.param("U32", "item", comment="The item to append")
                with push.body as b:
                    with b.if_("m_size == m_capacity"):
                        b.line("return Status::FULL;")
                    b.line("m_data[(m_head + m_size) % CAPACITY] = item;")
                    b.line("m_size++;")
                    b.line("return Status::OK;")

                cls.function(
                    "size",
                    ret="U32",
                    const=True,
                    inline=True,
                    body="return m_size;",
                    comment="The number of items currently stored",
                )

                total = cls.function(
                    "total", ret="U32", const=True, comment="The sum of every item"
                )
                with total.body as b:
                    b.line("U32 sum = 0;")
                    with b.for_("U32 i = 0", "i < m_size", "i++"):
                        b.line("sum += m_data[(m_head + i) % CAPACITY];")
                    b.line("return sum;")

            with cls.private("Member variables"):
                cls.var(
                    "U32",
                    "CAPACITY",
                    init="64",
                    static=True,
                    constexpr=True,
                    comment="The largest capacity a ring can have",
                )
                cls.var("U32", "m_data", array="CAPACITY", comment="The stored items")
                cls.var("U32", "m_head", comment="Index of the oldest item")
                cls.var("U32", "m_size", comment="How many items are stored")
                cls.var("U32", "m_capacity", const=True, comment="The chosen capacity")

    return doc


if __name__ == "__main__":
    doc = build()
    if len(sys.argv) > 1:
        result = doc.write(sys.argv[1])
        for path in result.written:
            print(f"wrote {path}")
        for path in result.unchanged:
            print(f"unchanged {path}")
    else:
        for name, text in doc.files().items():
            print(f"===== {name} =====")
            print(text)
