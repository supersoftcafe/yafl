from unittest import TestCase

import compiler as c

class TestOptimiser(TestCase):
    def test_static_init_simple(self):
        """NewObject with all-literal fields should become a static global."""
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
                   "class Pair(left: System::Int, right: System::Int)\n"
                   "fun getPair(): System::Int\n"
                   "    let p: Pair = Pair(1, 2)\n"
                   "    ret p.left + p.right\n"
                   "fun main(): System::Int\n"
                   "    ret getPair()\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # After static-init optimization, Pair(1,2) should be a C static global, not heap-allocated
        self.assertNotIn("object_create(obj_System", result)
        print(result)

    def test_static_init_global_let(self):
        """Global let with all-literal fields should become a C static initializer (no lazy-init)."""
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "fun `+`(left: System::Int, right: System::Int): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"add\", left, right)\n"
                   "class Config(value: System::Int)\n"
                   "let defaultConfig: Config = Config(42)\n"
                   "fun main(): System::Int\n"
                   "    ret defaultConfig.value\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # After optimization, no runtime lazy-init call should be needed
        self.assertNotIn("lazy_global_init_complete", result)
        print(result)

    def test_dead_store_elim_removes_unused_trait_impls(self):
        """After inlining, trait objects whose methods are all inlined away should be eliminated.

        In `ret 1 + 3`, the BasicMath trait object is used only to resolve `+` at compile
        time. After inlining, the `this` StackVar holding the trait object becomes dead.
        Dead store elimination should remove it, which lets trim cascade and eliminate the
        entire vtable and all method implementations except the inlined call site.
        """
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface BasicPlus<TVal>
    fun `+`(left: TVal, right: TVal): TVal

interface BasicMath<TVal> : BasicPlus<TVal>
    fun `-`(left: TVal, right: TVal): TVal

class _BasicMathInt() : BasicMath<System::Int>
    fun `+`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_add", left, right)
    fun `-`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_sub", left, right)

let [trait] int_trait: _BasicMathInt = _BasicMathInt()

fun main(): System::Int where BasicMath<System::Int>
    ret 1 + 3
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # No vtable declarations — the entire _BasicMathInt implementation is dead
        self.assertNotIn("VTABLE_DECLARE", result)
        # No function bodies for the trait methods
        self.assertNotIn("integer_sub", result)

    def test_dead_store_elim_keeps_used_operations(self):
        """Dead store elimination must not remove operations whose results are observable.

        Both `+` and `-` are used in the return value.  After dead-store elimination the
        two direct C-level integer calls (`integer_add`, `integer_sub`) must still appear
        in the generated output; only the unreachable vtable method bodies for unused
        interface slots are allowed to disappear.
        """
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface BasicMath<TVal>
    fun `+`(left: TVal, right: TVal): TVal
    fun `-`(left: TVal, right: TVal): TVal

class _BasicMathInt() : BasicMath<System::Int>
    fun `+`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_add", left, right)
    fun `-`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_sub", left, right)

let [trait] int_trait: _BasicMathInt = _BasicMathInt()

fun main(): System::Int where BasicMath<System::Int>
    let a: System::Int = 10 + 3
    ret a - 2
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # Both arithmetic primitives must survive — they are the actual computation
        self.assertIn("integer_add", result)
        self.assertIn("integer_sub", result)

    def test_dead_store_elim_preserves_live_assignments(self):
        """StackVar assignments that ARE read must not be removed.

        In `ret 1 + 3`, the inlined code assigns integer-literal globals to StackVars
        (`left = p1`, `right = p3`) and then READS them as arguments to integer_add.
        Those assignments are live, not dead stores.

        If the pass incorrectly treated them as dead, each literal global would become
        unreferenced, be eliminated by the trim pass, and disappear from the C output.
        The assertions below would then fail, catching the bug.
        """
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface BasicPlus<TVal>
    fun `+`(left: TVal, right: TVal): TVal

class _BasicPlusInt() : BasicPlus<System::Int>
    fun `+`(left: System::Int, right: System::Int): System::Int
        ret __builtin_op__<bigint>("integer_add", left, right)

let [trait] int_trait: _BasicPlusInt = _BasicPlusInt()

fun main(): System::Int where BasicPlus<System::Int>
    ret 1 + 3
"""
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False, optimization_level=1)
        self.assertNotEqual("", result)
        # Both integer literal globals must survive — their StackVar assignments are live
        # (read as arguments to integer_add).  Absence of either means a live store was dropped.
        self.assertIn("INTEGER_LITERAL_1(0, 1)", result)
        self.assertIn("INTEGER_LITERAL_1(0, 3)", result)
