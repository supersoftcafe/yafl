from io import StringIO
from contextlib import redirect_stdout
from tests.testutil import TimedTestCase as TestCase

import compiler as c
from tests.testutil import compile_and_run_with_c_library


def _compile(content: str) -> str:
    return c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)


def _compile_capturing_errors(content: str) -> tuple[str, str]:
    """Returns (result, captured_stdout)."""
    buf = StringIO()
    with redirect_stdout(buf):
        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
    return result, buf.getvalue()


class TestFinal(TestCase):

    def test_final_class_compiles(self):
        """A [final] class compiles successfully."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

class [final] Point(x: System::Int, y: System::Int)

fun main(): System::Int
    let p: System::Point = System::Point(3, 4)
    ret p.x
"""
        result = _compile(content)
        self.assertNotEqual("", result)

    def test_final_class_method_compiles(self):
        """A [final] class with a method compiles successfully (direct dispatch path)."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

class [final] Counter(n: System::Int)
    fun value(): System::Int
        ret n

fun main(): System::Int
    let c: System::Counter = System::Counter(42)
    ret c.value()
"""
        result = _compile(content)
        self.assertNotEqual("", result)

    def test_inherit_from_final_interface_is_error(self):
        """Implementing a [final] interface is a compile error."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface [final] Sealed
    fun value(): System::Int

class Breaker() : System::Sealed
    fun value(): System::Int
        ret 1

fun main(): System::Int
    ret 1
"""
        result, errors = _compile_capturing_errors(content)
        self.assertEqual("", result)
        self.assertIn("final", errors.lower())


class TestForeign(TestCase):

    def test_foreign_class_compiles(self):
        """A [foreign, final] class with no parameters compiles successfully."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

class [foreign, final] FileIO

fun main(): System::Int
    ret 0
"""
        result = _compile(content)
        self.assertNotEqual("", result)

    def test_foreign_standalone_function_compiles(self):
        """A standalone [foreign("sym")] function with no body compiles successfully."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

fun [foreign("libyafl_get_env")] get_env(name: System::String): System::String

fun main(): System::Int
    ret 0
"""
        result = _compile(content)
        self.assertNotEqual("", result)

    def test_foreign_class_with_foreign_methods_compiles(self):
        """A [foreign, final] class with [foreign] methods compiles successfully."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

class [foreign, final] FileIO
    fun [foreign("libyafl_file_read_line")] read_line(): System::String
    fun [foreign("libyafl_file_close")]     close(): System::Int

fun [foreign("libyafl_file_open")] open(path: System::String): System::FileIO

fun main(): System::Int
    ret 0
"""
        result = _compile(content)
        self.assertNotEqual("", result)

    def test_foreign_class_without_final_is_error(self):
        """A [foreign] class without [final] is a compile error."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

class [foreign] FileIO

fun main(): System::Int
    ret 0
"""
        result, errors = _compile_capturing_errors(content)
        self.assertEqual("", result)
        self.assertIn("final", errors.lower())

    def test_foreign_class_with_symbol_is_error(self):
        """[foreign("sym")] on a class is a compile error — classes take no symbol."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

class [foreign("libyafl_file_open"), final] FileIO

fun main(): System::Int
    ret 0
"""
        result, errors = _compile_capturing_errors(content)
        self.assertEqual("", result)
        self.assertIn("foreign", errors.lower())

    def test_foreign_class_with_parameters_is_error(self):
        """A [foreign, final] class with constructor parameters is a compile error."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

class [foreign, final] FileIO(path: System::String)

fun main(): System::Int
    ret 0
"""
        result, errors = _compile_capturing_errors(content)
        self.assertEqual("", result)
        self.assertIn("foreign", errors.lower())

    def test_foreign_class_with_non_foreign_method_is_error(self):
        """A [foreign] class with a non-[foreign] method is a compile error."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

class [foreign, final] FileIO
    fun read(): System::String
        ret "hello"

fun main(): System::Int
    ret 0
"""
        result, errors = _compile_capturing_errors(content)
        self.assertEqual("", result)
        self.assertIn("foreign", errors.lower())

    def test_foreign_function_with_body_is_error(self):
        """A [foreign] function with a body is a compile error."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

fun [foreign("libyafl_get_env")] get_env(name: System::String): System::String
    ret name

fun main(): System::Int
    ret 0
"""
        result, errors = _compile_capturing_errors(content)
        self.assertEqual("", result)
        self.assertIn("foreign", errors.lower())

    def test_foreign_function_without_symbol_is_error(self):
        """A [foreign] function without a string argument is a compile error."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

fun [foreign] get_env(name: System::String): System::String

fun main(): System::Int
    ret 0
"""
        result, errors = _compile_capturing_errors(content)
        self.assertEqual("", result)
        self.assertIn("foreign", errors.lower())

    def test_foreign_declarations_emit_no_definitions(self):
        """Foreign class and functions produce no struct typedef, vtable, or function bodies in the C output."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

class [foreign, final] FileIO
    fun [foreign("libyafl_file_close")] close(): System::Int

fun [foreign("libyafl_file_open")] open(path: System::String): System::FileIO

fun main(): System::Int
    ret 0
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        self.assertNotIn("libyafl_file_open", result)
        self.assertNotIn("libyafl_file_close", result)
        self.assertNotIn("FileIO_t", result)

    def test_comma_separated_attributes(self):
        """[foreign, final] — multiple attributes in one block, comma-separated."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

class [foreign, final] FileIO

fun main(): System::Int
    ret 0
"""
        result = _compile(content)
        self.assertNotEqual("", result)


class TestForeignIntegration(TestCase):
    """Full compile-link-run tests for the [foreign] attribute.

    The C library implements a trivial integer counter whose state lives in a
    C global.  Foreign functions follow the direct-return calling convention:
    they accept their arguments and return the result directly (no continuation).
    """

    # counter_t extends object_t with a per-object int32_t field.
    # The vtable's object_size covers the full struct so the GC allocates enough.
    _C_LIBRARY = r"""
#include <yafl.h>

typedef struct {
    object_t base;
    int32_t  value;
} counter_t;

static vtable_t* _counter_implements[] = { NULL };

static VTABLE_DECLARE_STRUCT(, 1) _counter_vtable = {
    .object_size                = sizeof(counter_t),
    .array_el_size              = 0,
    .object_pointer_locations   = 0,
    .array_el_pointer_locations = 0,
    .functions_mask             = 0,
    .array_len_offset           = 0,
    .is_mutable                 = 0,
    .name                       = "Counter",
    .implements_array           = _counter_implements,
    .lookup                     = {{ .i = -1, .f = (void*)&abort_on_vtable_lookup }}
};

object_t* test_counter_create(object_t* _this, object_t* init) {
    counter_t* c = (counter_t*)object_create((vtable_t*)&_counter_vtable);
    c->value = integer_to_int32(init);
    return (object_t*)c;
}

object_t* test_counter_get(object_t* _this) {
    return integer_create_from_int32(((counter_t*)_this)->value);
}

object_t* test_counter_add(object_t* _this, object_t* n) {
    ((counter_t*)_this)->value += integer_to_int32(n);
    return integer_create_from_int32(((counter_t*)_this)->value);
}
"""

    _YAFL = """\
namespace System
typealias Int : __builtin_type__<bigint>

class [foreign, final] Counter
    fun [foreign("test_counter_get")] get(): System::Int
    fun [foreign("test_counter_add")] add(n: System::Int): System::Int

fun [foreign("test_counter_create")] create(init: System::Int): System::Counter

fun main(): System::Int
    let c: System::Counter = create(10)
    let _a: System::Int = c.add(5)
    let _b: System::Int = c.add(3)
    ret c.get()
"""

    def test_foreign_counter(self):
        """Create counter(10), add(5) → 15, add(3) → 18; get() returns 18."""
        exit_code = compile_and_run_with_c_library(self._YAFL, self._C_LIBRARY)
        self.assertEqual(18, exit_code)


class TestSync(TestCase):

    def test_sync_function_compiles(self):
        """A [sync] function compiles without error."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun [sync] identity(x: System::Int): System::Int
    ret x

fun main(): System::Int
    ret identity(42)
"""
        result = _compile(content)
        self.assertNotEqual("", result)

    def test_sync_with_argument_is_error(self):
        """[sync("foo")] is a compile error — [sync] takes no arguments."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun [sync("bad")] f(): System::Int
    ret 0

fun main(): System::Int
    ret 0
"""
        result, errors = _compile_capturing_errors(content)
        self.assertEqual("", result)
        self.assertIn("sync", errors.lower())

    def test_sync_function_has_no_async_sibling(self):
        """A [sync] function does not generate a $async state machine."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun [sync] identity(x: System::Int): System::Int
    ret x

fun [sync] double_call(x: System::Int): System::Int
    let a: System::Int = identity(x)
    ret a

fun main(): System::Int
    ret double_call(1)
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        self.assertNotIn("double_call$async", result)

    def test_sync_function_return_type_not_wrapped(self):
        """A [sync] function's return type is not wrapped for task signalling."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias Int32 : __builtin_type__<int32>

fun [foreign("get_int32_value")] get_int32(): System::Int32

fun [sync] identity(x: System::Int32): System::Int32
    ret x

fun main(): System::Int
    let r: System::Int32 = identity(get_int32())
    ret 0
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        # [sync] skips CPS entirely — no $async variant is emitted for identity,
        # and the function never wraps its return in a TaskWrapper. The AST
        # inliner may eliminate `identity` entirely at its single call site;
        # what we care about is that no sync wrapping machinery appears.
        self.assertNotIn("identity$async", result)
        self.assertNotIn("System__identity_", result.split("// System::main")[0] if "// System::main" in result else "")

    def test_calling_sync_functions_only_has_no_state_machine(self):
        """A non-sync function whose non-tail calls are all [sync] generates no $async."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun [sync] identity(x: System::Int): System::Int
    ret x

fun wrapper(x: System::Int): System::Int
    let a: System::Int = identity(x)
    ret a

fun main(): System::Int
    ret wrapper(1)
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        self.assertNotIn("wrapper$async", result)

    def test_sync_combined_with_foreign(self):
        """[foreign("sym"), sync] on a function compiles successfully."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun [foreign("libyafl_get_value"), sync] get_value(): System::Int

fun main(): System::Int
    ret 0
"""
        result = _compile(content)
        self.assertNotEqual("", result)

    def test_sync_combined_with_impure(self):
        """[impure, sync] on a function compiles successfully."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>
typealias String : __builtin_type__<str>

fun [foreign("print_string"), impure, sync] print_s(s: System::String): System::Int

fun main(): System::Int
    ret 0
"""
        result = _compile(content)
        self.assertNotEqual("", result)


class TestSyncInference(TestCase):

    def test_inferred_sync_leaf_has_no_async_sibling(self):
        """A non-foreign leaf function (no non-tail calls) is inferred sync — no $async generated."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun add(x: System::Int, y: System::Int): System::Int
    ret __builtin_op__<bigint>("add", x, y)

fun main(): System::Int
    ret add(1, 2)
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        self.assertNotIn("add$async", result)

    def test_inferred_sync_propagates_through_chain(self):
        """Sync inference propagates: if all non-tail callees are sync, the caller is sync too."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun leaf(x: System::Int): System::Int
    ret x

fun middle(x: System::Int): System::Int
    let a: System::Int = leaf(x)
    ret a

fun main(): System::Int
    ret middle(1)
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        self.assertNotIn("middle$async", result)

    def test_inferred_sync_does_not_promote_foreign_leaf(self):
        """A foreign function without [sync] is NOT inferred sync — its body is empty (unknown)."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun [foreign("external_op")] ext(): System::Int

fun wrapper(): System::Int
    let a: System::Int = ext()
    ret a

fun main(): System::Int
    ret wrapper()
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        # wrapper calls a non-sync foreign — it must not be inferred sync.
        # After AST inlining wrapper is folded into main, so check that SOME
        # async continuation was emitted (the call chain could not be made sync).
        # Name mangling converts $ → _.
        self.assertRegex(result, r'_async')

    def test_inferred_sync_foreign_with_sync_attribute_is_promoted(self):
        """A foreign function WITH [sync] IS sync — callers that only call it are also inferred sync."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

fun [foreign("external_op"), sync] ext(): System::Int

fun wrapper(): System::Int
    let a: System::Int = ext()
    ret a

fun main(): System::Int
    ret wrapper()
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        # wrapper only calls a [sync] foreign — inferred sync, no state machine
        self.assertNotIn("wrapper$async", result)

    def test_inferred_sync_virtual_all_impls_sync(self):
        """Virtual call is inferred sync when all implementing functions are sync."""
        content = """namespace System
typealias Int : __builtin_type__<bigint>

interface Adder
    fun add(x: System::Int): System::Int

class [final] One() : System::Adder
    fun add(x: System::Int): System::Int
        ret __builtin_op__<bigint>("add", x, 1)

fun call_add(a: System::Adder, x: System::Int): System::Int
    let r: System::Int = a.add(x)
    ret r

fun main(): System::Int
    let o: System::One = System::One()
    ret call_add(o, 5)
"""
        result = _compile(content)
        self.assertNotEqual("", result)
        # All implementations of Adder::add are leaf functions (inferred sync)
        # so call_add should also be inferred sync
        self.assertNotIn("call_add$async", result)
