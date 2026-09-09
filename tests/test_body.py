"""Tests for the statement/body builder."""

from __future__ import annotations

import pytest

from fprime_cpp_codegen.body import Body
from fprime_cpp_codegen.errors import ScopeError
from fprime_cpp_codegen.lines import line, render


def text(body: Body) -> str:
    return render(body.build())


class TestSimpleStatements:
    def test_lines_and_raw(self) -> None:
        b = Body()
        b.line("a();")
        b.lines("b();\n|c();")
        b.raw([line("d();")])
        assert text(b) == "a();\nb();\nc();\nd();\n"

    def test_var_and_assign(self) -> None:
        b = Body()
        b.var("U32", "x")
        b.var("U32", "y", "0")
        b.assign("y", "x + 1")
        assert text(b) == "U32 x;\nU32 y = 0;\ny = x + 1;\n"

    def test_return_with_and_without_a_value(self) -> None:
        b = Body()
        b.ret()
        b.ret("0")
        assert text(b) == "return;\nreturn 0;\n"

    def test_break_and_continue(self) -> None:
        b = Body()
        b.break_()
        b.continue_()
        assert text(b) == "break;\ncontinue;\n"

    def test_call(self) -> None:
        b = Body()
        b.call("f")
        b.call("g", "a", "b")
        assert text(b) == "f();\ng(a, b);\n"

    def test_call_with_variable_args_is_exploded(self) -> None:
        b = Body()
        b.call("log", "id", variable_args=["a", "b"])
        assert text(b) == "log(\n  id,\n  a,\n  b\n);\n"

    def test_sum_with_a_prefix_hangs_under_it(self) -> None:
        b = Body()
        b.sum(["a", "b"], prefix="return ")
        assert text(b) == "return a +\n       b;\n"

    def test_blank_and_comments(self) -> None:
        b = Body()
        b.comment("plain")
        b.doc_comment("doc")
        b.blank()
        assert text(b) == "// plain\n\n//! doc\n\n"

    def test_chaining(self) -> None:
        b = Body()
        b.line("a();").line("b();").ret("0")
        assert text(b) == "a();\nb();\nreturn 0;\n"


class TestControlFlow:
    def test_if(self) -> None:
        b = Body()
        with b.if_("x > 0"):
            b.ret("x")
        assert text(b) == "if (x > 0) {\n  return x;\n}\n"

    def test_if_elif_else_chain(self) -> None:
        b = Body()
        with b.if_("a"):
            b.line("f();")
        with b.elif_("c"):
            b.line("g();")
        with b.else_():
            b.line("h();")
        assert text(b) == (
            "if (a) {\n  f();\n}\n"
            "else if (c) {\n  g();\n}\n"
            "else {\n  h();\n}\n"
        )

    def test_else_without_an_if_is_rejected(self) -> None:
        b = Body()
        b.line("a();")
        with pytest.raises(ScopeError, match="has no 'if' to attach to"):
            b.else_()

    def test_a_statement_between_if_and_else_breaks_the_chain(self) -> None:
        # Otherwise the else would silently attach to the wrong if.
        b = Body()
        with b.if_("a"):
            b.line("f();")
        b.line("unrelated();")
        with pytest.raises(ScopeError):
            b.else_()

    def test_an_empty_if_still_emits_so_a_following_else_stays_attached(self) -> None:
        b = Body()
        with b.if_("a"):
            pass
        with b.else_():
            b.line("h();")
        assert text(b) == "if (a) {\n}\nelse {\n  h();\n}\n"

    def test_omit_if_empty_drops_the_scope(self) -> None:
        b = Body()
        with b.if_("a", omit_if_empty=True):
            pass
        assert text(b) == ""

    def test_while_and_do_while(self) -> None:
        b = Body()
        with b.while_("go"):
            b.line("f();")
        with b.do_while("go"):
            b.line("g();")
        assert text(b) == (
            "while (go) {\n  f();\n}\ndo {\n  g();\n} while (go);\n"
        )

    def test_for_and_ranged_for(self) -> None:
        b = Body()
        with b.for_("U32 i = 0", "i < n", "i++"):
            b.line("f(i);")
        with b.for_range("auto& e", "m_list"):
            b.line("g(e);")
        assert text(b) == (
            "for (U32 i = 0; i < n; i++) {\n  f(i);\n}\n"
            "for (auto& e : m_list) {\n  g(e);\n}\n"
        )

    def test_staggered_for(self) -> None:
        b = Body()
        with b.for_("U32 i = 0", "i < n", "i++", staggered=True):
            b.line("f(i);")
        assert text(b) == "for (\n  U32 i = 0;\n  i < n;\n  i++\n) {\n  f(i);\n}\n"

    def test_block(self) -> None:
        b = Body()
        with b.block():
            b.var("U32", "tmp", "0")
        assert text(b) == "{\n  U32 tmp = 0;\n}\n"

    def test_nesting(self) -> None:
        b = Body()
        with b.for_("U32 i = 0", "i < n", "i++"):
            with b.if_("m_data[i] == 0"):
                b.continue_()
            b.line("total += m_data[i];")
        assert text(b) == (
            "for (U32 i = 0; i < n; i++) {\n"
            "  if (m_data[i] == 0) {\n"
            "    continue;\n"
            "  }\n"
            "  total += m_data[i];\n"
            "}\n"
        )

    def test_generic_scope(self) -> None:
        b = Body()
        with b.scope("try {", "} catch (...) {}"):
            b.line("risky();")
        assert text(b) == "try {\n  risky();\n} catch (...) {}\n"

    def test_if_directive_does_not_indent_its_contents(self) -> None:
        b = Body()
        with b.if_directive("#if FW_ENABLE_TEXT_LOGGING"):
            b.line("log();")
        assert text(b) == "\n#if FW_ENABLE_TEXT_LOGGING\nlog();\n\n#endif\n"

    def test_empty_if_directive_vanishes(self) -> None:
        b = Body()
        with b.if_directive("#ifdef X"):
            pass
        assert text(b) == ""


class TestSwitch:
    def test_cases_get_braces_and_an_automatic_break(self) -> None:
        b = Body()
        with b.switch("kind") as sw:
            with sw.case("Kind::A"):
                b.line("a();")
            with sw.default():
                b.line("d();")
        assert text(b) == (
            "switch (kind) {\n"
            "  case Kind::A: {\n"
            "    a();\n"
            "    break;\n"
            "  }\n"
            "  default: {\n"
            "    d();\n"
            "    break;\n"
            "  }\n"
            "}\n"
        )

    def test_fallthrough_omits_the_break(self) -> None:
        b = Body()
        with b.switch("k") as sw:
            with sw.case("A", fallthrough=True):
                b.line("a();")
        assert "break;" not in text(b)

    def test_several_labels_share_one_body(self) -> None:
        b = Body()
        with b.switch("k") as sw:
            with sw.case("A", "B", "C"):
                b.ret("1")
        out = text(b)
        assert "case A:\n" in out and "case B:\n" in out and "case C: {" in out

    def test_case_needs_a_label(self) -> None:
        b = Body()
        with b.switch("k") as sw:
            with pytest.raises(ScopeError, match="at least one label"):
                sw.case()

    def test_case_on_a_switch_that_is_not_innermost_is_rejected(self) -> None:
        b = Body()
        with b.switch("k") as sw:
            with sw.case("A"):
                with pytest.raises(ScopeError, match="not the innermost open scope"):
                    sw.case("B")

    def test_nested_switch(self) -> None:
        b = Body()
        with b.switch("outer") as osw:
            with osw.case("A"):
                with b.switch("inner") as isw:
                    with isw.case("B"):
                        b.line("f();")
        out = text(b)
        assert "switch (outer)" in out and "switch (inner)" in out

    def test_empty_switch_can_be_omitted(self) -> None:
        b = Body()
        with b.switch("k", omit_if_empty=True):
            pass
        assert text(b) == ""


class TestFragments:
    def test_a_body_can_be_built_standalone_and_spliced(self) -> None:
        def guard(name: str) -> Body:
            frag = Body()
            with frag.if_(f"{name} == nullptr"):
                frag.ret("Status::INVALID")
            return frag

        b = Body()
        b.extend(guard("p"))
        b.extend(guard("q"))
        b.ret("Status::OK")
        assert text(b).count("== nullptr") == 2

    def test_extend_accepts_plain_lines(self) -> None:
        b = Body()
        b.extend([line("a();")])
        assert text(b) == "a();\n"

    def test_initial_lines(self) -> None:
        assert text(Body([line("a();")])) == "a();\n"

    def test_str_renders(self) -> None:
        b = Body()
        b.line("a();")
        assert str(b) == "a();\n"

    def test_truthiness_reflects_content(self) -> None:
        b = Body()
        assert not b
        b.line("a();")
        assert b

    def test_iteration_yields_lines(self) -> None:
        b = Body()
        b.line("a();")
        assert list(b) == [line("a();")]


class TestErrorHandling:
    def test_an_exception_inside_a_scope_leaves_the_body_unchanged(self) -> None:
        b = Body()
        b.line("before();")
        with pytest.raises(RuntimeError):
            with b.if_("a"):
                b.line("partial();")
                raise RuntimeError("boom")
        assert text(b) == "before();\n"

    def test_an_exception_inside_a_case_leaves_the_switch_usable(self) -> None:
        b = Body()
        with b.switch("k") as sw:
            with pytest.raises(RuntimeError):
                with sw.case("A"):
                    raise RuntimeError("boom")
            with sw.case("B"):
                b.line("b();")
        out = text(b)
        assert "case B:" in out and "case A:" not in out

    def test_building_with_a_scope_still_open_is_rejected(self) -> None:
        b = Body()
        cm = b.if_("a")
        cm.__enter__()
        with pytest.raises(ScopeError, match="still open"):
            b.build()


class TestCodeCoercion:
    def test_stmts_accepts_every_shape(self) -> None:
        from fprime_cpp_codegen.body import stmts

        frag = Body()
        frag.line("x();")
        result = stmts(["a();", line("b();"), [frag, None]], "c();")
        assert [str(l) for l in result] == ["a();", "b();", "x();", "c();"]

    def test_none_contributes_nothing(self) -> None:
        # This is what lets a caller write `b.add(frag if cond else None)`.
        from fprime_cpp_codegen.body import stmts

        assert stmts(None) == []

    def test_a_string_is_taken_verbatim_with_no_punctuation_added(self) -> None:
        from fprime_cpp_codegen.body import stmts

        assert [str(l) for l in stmts("a()")] == ["a()"]

    def test_an_unusable_value_is_rejected(self) -> None:
        from fprime_cpp_codegen.body import stmts
        from fprime_cpp_codegen.errors import ValidationError

        with pytest.raises(ValidationError, match="not usable as C\\+\\+ statements"):
            stmts(42)  # type: ignore[arg-type]

    def test_add_takes_several_shapes_at_once(self) -> None:
        frag = Body()
        frag.ret("0")
        b = Body()
        b.add(None, "a();", [frag])
        assert text(b) == "a();\nreturn 0;\n"


class TestTermination:
    def test_terminating_statements_are_tracked(self) -> None:
        for method, arg in (("ret", None), ("break_", None), ("continue_", None), ("throw", None)):
            b = Body()
            getattr(b, method)() if arg is None else getattr(b, method)(arg)
            assert b.terminated, method

    def test_an_ordinary_statement_clears_termination(self) -> None:
        b = Body()
        b.ret("0")
        b.line("unreachable();")
        assert not b.terminated

    def test_a_nested_return_does_not_terminate_the_outer_level(self) -> None:
        # The if may not be taken, so what follows is still reachable.
        b = Body()
        with b.if_("x"):
            b.ret("0")
        assert not b.terminated

    def test_no_unreachable_break_after_a_return(self) -> None:
        b = Body()
        with b.switch("k") as sw:
            with sw.case("A"):
                b.ret("1")
        assert "break;" not in text(b)

    def test_a_break_is_still_emitted_when_the_arm_falls_through(self) -> None:
        b = Body()
        with b.switch("k") as sw:
            with sw.case("A"):
                b.call("handle")
        assert "break;" in text(b)

    def test_a_conditional_return_still_gets_its_break(self) -> None:
        b = Body()
        with b.switch("k") as sw:
            with sw.case("A"):
                with b.if_("x"):
                    b.ret("1")
        assert "break;" in text(b)

    def test_depth_reports_open_scopes(self) -> None:
        b = Body()
        assert b.depth == 0
        with b.if_("x"):
            assert b.depth == 1
            with b.block():
                assert b.depth == 2
        assert b.depth == 0


class TestBranch:
    def test_branch_opens_an_if_then_continues_the_chain(self) -> None:
        b = Body()
        for i, cond in enumerate(("a", "b", "c")):
            with b.branch(cond):
                b.line(f"f{i}();")
        with b.else_():
            b.line("other();")
        assert text(b) == (
            "if (a) {\n  f0();\n}\n"
            "else if (b) {\n  f1();\n}\n"
            "else if (c) {\n  f2();\n}\n"
            "else {\n  other();\n}\n"
        )

    def test_branch_restarts_after_the_chain_is_broken(self) -> None:
        b = Body()
        with b.branch("a"):
            b.line("f();")
        b.line("between();")
        with b.branch("c"):
            b.line("g();")
        assert text(b).count("if (") == 2
        assert "else if" not in text(b)


class TestMoreStatements:
    def test_expr(self) -> None:
        b = Body()
        b.expr("m_count++")
        assert text(b) == "m_count++;\n"

    def test_compound_assignment(self) -> None:
        b = Body()
        b.assign("total", "x", op="+=")
        assert text(b) == "total += x;\n"

    def test_throw(self) -> None:
        b = Body()
        b.throw("std::runtime_error(\"bad\")")
        b2 = Body()
        b2.throw()
        assert text(b) == 'throw std::runtime_error("bad");\n'
        assert text(b2) == "throw;\n"

    def test_var_decorations(self) -> None:
        b = Body()
        b.var("U32", "n", "0", static=True, constexpr=True)
        b.var("bool", "flags", array="SIZE")
        b.var("U32", "k", "3", comment="why")
        assert text(b) == (
            "static constexpr U32 n = 0;\nbool flags[SIZE];\n// why\nU32 k = 3;\n"
        )
