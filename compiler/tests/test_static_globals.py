"""Compile-time-constant object GRAPHS become C statics.

Strings and flat simple-class globals already emit statically. This covers the
rest: a global whose initialiser is a tree of constant-field objects (union
typed, vtable'd, nested) must land in static storage with NO runtime
initialisation — every `$si$` object may reference other static objects in its
initialiser, the lazy-init thunk folds away, and reads are direct.
"""
from __future__ import annotations

import subprocess
import tempfile
import os
from pathlib import Path

import compiler as c

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_CHAIN = """namespace Test
import System

class [final] Node(value: Int32, next: Node|None)

let nodes: Node|None = Node(1i32, Node(2i32, Node(3i32, None)))

fun sum(n: Node|None): Int32
  ret match(n)
    (x: Node)         => x.value + sum(x.next)
    (e: System::None) => 0i32

fun main(): Int
  ret match(nodes)
    (x: Node)         => sum(nodes) == 6i32 ? 0 : 1
    (e: System::None) => 1
"""


def _emit_c(src: str) -> str:
    code = c.compile([c.Input(src, "test.yafl")], use_stdlib=True,
                     just_testing=False, optimization_level=1)
    assert code, "compilation failed"
    return code


# Same shape but with the DEFAULT integer type (bigint literals become
# $integers globals — the plan inlines their constant), and the outer chain
# referencing a separately-declared static by NAME.
_CHAIN_BIGINT = """namespace Test
import System

class [final] Node(value: Int, next: Node|None)

let tail3: Node|None = Node(3, None)
let nodes: Node|None = Node(1, Node(2, tail3))

fun sum(n: Node|None): Int
  ret match(n)
    (x: Node)         => x.value + sum(x.next)
    (e: System::None) => 0

fun main(): Int
  ret sum(nodes) == 6 ? 0 : 1
"""


class TestStaticObjectGraphs(TestCase):
    def test_constant_chain_runs(self):
        rc, out = compile_and_run_stdlib_capture(_CHAIN, timeout=30,
                                                 optimization_level=1)
        self.assertEqual(0, rc, f"chain program failed; stdout:\n{out}")

    def test_constant_chain_is_fully_static(self):
        code = _emit_c(_CHAIN)
        # No runtime initialisation survives: the global's lazy-init thunk is
        # gone (nothing references it once the stub is pre-completed).
        self.assertNotIn("lambda_Test__nodes", code,
                         "the constant chain still carries a runtime init thunk")
        # All three Nodes are static object instances (each `_data` struct
        # opens with its vtable value, carrying VTABLE_TAG_BIT exactly as a
        # heap instance's header does — see yafl.h vtable_is_forward).
        self.assertGreaterEqual(
            code.count("(object_t*)((char*)obj_Test__Node"), 3,
            "expected three static Node instances")

    def test_bigint_fields_and_cross_reference_run(self):
        rc, out = compile_and_run_stdlib_capture(_CHAIN_BIGINT, timeout=30,
                                                 optimization_level=1)
        self.assertEqual(0, rc, f"bigint chain program failed; stdout:\n{out}")

    def test_bigint_fields_and_cross_reference_are_static(self):
        code = _emit_c(_CHAIN_BIGINT)
        self.assertNotIn("lambda_Test__nodes", code,
                         "the bigint chain still carries a runtime init thunk")
        self.assertNotIn("lambda_Test__tail3", code,
                         "the referenced static still carries a runtime init thunk")
        self.assertGreaterEqual(
            code.count("(object_t*)((char*)obj_Test__Node"), 3,
            "expected three static Node instances")

    def test_mutually_referencing_globals_compile(self):
        # A reference cycle between global initialisers must not recurse the
        # planner forever — the cycle falls back to the lazy path. (Compile
        # only: forcing a truly cyclic lazy at runtime is its own problem.)
        code = _emit_c("""namespace Test
import System

class [final] Node(value: Int, next: Node|None)

let a: Node|None = Node(1, b)
let b: Node|None = Node(2, a)

fun main(): Int
  ret 0
""")
        self.assertTrue(code, "cyclic globals failed to compile")
