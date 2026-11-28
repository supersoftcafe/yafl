"""Literal discovery (#159): constructions become literals, literals statics.

Code builds values with operations a compiler cannot see through: an append
pins, finds the end, maybe writes, unpins; a Dict put walks and rebalances a
tree. Given a LITERAL — an object the function builds from constants — and
one such operation, the result is again a literal. This pass works in those
pairs, repeated:

  * Stage 1 (`fold_literal_calls`, after inlining): a call whose arguments are
    literals is run by a small interpreter over the IR, and its value written
    back into the function as plain constructions — a NewObject and its fresh
    initialisation stores per object, an array's elements stored one by one,
    no fill loop, no pin. That construction is a literal for the next call to
    consume. Inputs the run did not write are reused, not rebuilt.
  * Stage 2 (lowering/staticinit.py, `settle_globals` here): a construction
    of literals becomes a static global; a lazy global whose initialiser is
    now just a constant is that constant.

A call that aborts, has an effect (an `[impure]` or foreign-impure call, a
write to a global or a static), runs out of budget, reaches an operation the
interpreter does not model, or makes too much data stays exactly where it is:
nothing is ever run ahead of where the program runs it.

The interpreter executes the pre-async IR as C would: fixed-width integers
wrap; a failed bounds check or a division by zero aborts. Int (bigint) add, subtract, multiply, divide and compare are exact;
String hashing and equality are the runtime's (yafllib str_hash, str_eq), so a
Dict or Set keyed by strings is a literal too. The stdlib's pin and unpin are
a lock the run needs no part of, and a late write under the pin
(object_pin_set) fills an empty field as the runtime does. Values are Python
ints, `Ref` (a static object), `Obj` (one the run built), `Fun` (a
closure), `Struct`, `Atom` (a constant it carries whole: a bigint
or string literal, a float, a zero) and `NULL`.

A [pinnable] object with a capacity (an array buffer) is trimmed to its
length — exactly what the runtime's compaction does — so as a literal it has
no room a late write could fill, and may be static. Any other [pinnable]
object (a list node, whose `_next` an append may still link) is a literal in
code but never a shared static.
"""
from __future__ import annotations

import dataclasses
import re

from codegen.gen import Application
from codegen.ir import Function, Global, Object
from codegen.ops import Call, Jump, JumpIf, Label, Move, NewObject, Phi, Return
from codegen.param import (ArrayElement, GlobalFunction, GlobalVar, InitArray,
                           IntEqConst, Integer, NewStruct, NewStructTyped,
                           NullPattern, NullPointer, ObjectField, ObjVtableEq, RParam,
                           RuntimeInvoke, StackVar, StaticObjectRef, String, Float, StructField,
                           VirtualFunction, VtableDiscriminator, ZeroOf, FieldOffset)
from codegen.typedecl import Array, DataPointer, FuncPointer, Int, IntPtr, Struct, Type
import lowering.eager_globals

STEP_LIMIT = 10_000       # interpreted operations per evaluated call
DEPTH_LIMIT = 200         # nested calls per evaluated call
DATA_LIMIT = 64 * 1024    # bytes of new static data per evaluated call

_STUB_PREFIX = "Lazy$"
_FETCH_PREFIX = "lazy_fetch$"
_STATIC_PREFIX = "$literal$"


# ── Why a run stopped ────────────────────────────────────────────────────────

ABORT = "abort"        # the call aborts
EFFECT = "effect"      # the call has an effect
BUDGET = "budget"      # too many steps: it may never finish
SHARED = "shared"      # it builds an object no two callers may share
OPAQUE = "opaque"      # an operation the interpreter does not model
LARGE = "large"        # its data is too large to emit


class Stop(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ── Values ───────────────────────────────────────────────────────────────────

class _Null:
    def __repr__(self) -> str:
        return "NULL"


NULL = _Null()


@dataclasses.dataclass(frozen=True)
class Ref:
    """An existing static object: the Global named `name`."""
    name: str


class Obj:
    """An object the run built."""
    def __init__(self, cls: str, items: list | None):
        self.cls = cls
        self.fields: dict[str, object] = {}
        self.items = items
        self.pinned = False


@dataclasses.dataclass(frozen=True)
class Fun:
    """A closure: code `name` over environment `env` (NULL for none)."""
    name: str | None
    env: object


@dataclasses.dataclass(frozen=True)
class Atom:
    """A constant the interpreter carries but cannot look inside, and the
    global that holds it (`home`), if one does. A bigint or string literal
    is static data in an initialiser but a compound literal — stack storage —
    in code, so code reads it from a global."""
    rparam: RParam
    home: str | None = None


def _big(v: object) -> int | None:
    """The value of a bigint (Int) constant, or None."""
    if isinstance(v, Atom) and isinstance(v.rparam, Integer) and v.rparam.precision == 0:
        return v.rparam.value
    return None


def _big_atom(value: int) -> Atom:
    return Atom(Integer(value, 0))


@dataclasses.dataclass
class Struct_:
    fields: dict[str, object]


def _wrap(value: int, bits: int) -> int:
    mask = (1 << bits) - 1
    value &= mask
    return value - (1 << bits) if value >> (bits - 1) else value


def _zero(ty: Type) -> object:
    if isinstance(ty, Int):
        return 0
    if isinstance(ty, IntPtr):
        return 0
    if isinstance(ty, DataPointer):
        return NULL
    if isinstance(ty, FuncPointer):
        return Fun(None, NULL)
    if isinstance(ty, Struct):
        return Struct_({n: _zero(ft) for n, ft in ty.fields})
    return Atom(ZeroOf(ty))


# ── Runtime operations the interpreter models ────────────────────────────────

_INT_OP = re.compile(r"^int(8|16|32|64)_(add|sub|mul|neg|inv|and|or|xor|andnot|shl|shr|div|rem|"
                     r"test_lt|test_eq|test_gt|max)$")
_INT_CONV = re.compile(r"^int(8|16|32|64)_from_int(8|16|32|64)$")


def _int_op(bits: int, op: str, args: list) -> int:
    if not all(isinstance(a, int) for a in args):
        raise Stop(OPAQUE)
    a = args[0]
    b = args[1] if len(args) > 1 else 0
    match op:
        case "add":     return _wrap(a + b, bits)
        case "sub":     return _wrap(a - b, bits)
        case "mul":     return _wrap(a * b, bits)
        case "neg":     return _wrap(-a, bits)
        case "inv":     return _wrap(~a, bits)
        case "and":     return _wrap(a & b, bits)
        case "or":      return _wrap(a | b, bits)
        case "xor":     return _wrap(a ^ b, bits)
        case "andnot":  return _wrap(a & ~b, bits)
        case "shl":     return _wrap(a << (b & (bits - 1)), bits)
        case "shr":     return a >> (b & (bits - 1))      # arithmetic
        case "div" | "rem":
            if b == 0:
                raise Stop(ABORT)                          # a trap in C
            if b == -1:
                return _wrap(-a, bits) if op == "div" else 0
            q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)   # C truncates
            return _wrap(q, bits) if op == "div" else _wrap(a - q * b, bits)
        case "test_lt": return 1 if a < b else 0
        case "test_eq": return 1 if a == b else 0
        case "test_gt": return 1 if a > b else 0
        case "max":     return a if a > b else b
    raise Stop(OPAQUE)


_BIG_OP = re.compile(r"^integer_(add|sub|mul|div|rem|test_lt|test_le|test_eq|test_ge|test_gt)$")
_BIG_FROM = re.compile(r"^integer_from_int(8|16|32|64)$")
_BIG_TO = re.compile(r"^int(8|16|32|64)_from_integer_truncate$")


def _big_op(op: str, args: list) -> object:
    """Int (bigint) arithmetic, exact, as yafllib's integer.c: division
    truncates, and by zero aborts. The rest of Int is not modelled."""
    xs = [_big(a) for a in args]
    if len(xs) != 2 or None in xs:
        raise Stop(OPAQUE)
    a, b = xs
    match op:
        case "add":     return _big_atom(a + b)
        case "sub":     return _big_atom(a - b)
        case "mul":     return _big_atom(a * b)
        case "div" | "rem":
            if b == 0:
                raise Stop(ABORT)                      # yafllib aborts
            q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)   # truncates
            return _big_atom(q if op == "div" else a - q * b)
        case "test_lt": return 1 if a < b else 0
        case "test_le": return 1 if a <= b else 0
        case "test_eq": return 1 if a == b else 0
        case "test_ge": return 1 if a >= b else 0
        case "test_gt": return 1 if a > b else 0
    raise Stop(OPAQUE)


# yafllib's str_hash (yafl.h): the UTF-8 bytes, 8 per multiply, the length
# mixed in, 31 bits, never 0. A string of up to 15 bytes is an INLINE value,
# hashed as its two zero-padded words; a longer one in 8-byte words, the last
# one partial.
_STR_HASH_SEED = 0x243F6A8885A308D3
_M64 = (1 << 64) - 1


def _str_mix(h: int, w: int) -> int:
    h = ((h ^ w) * 0x9E3779B97F4A7C15) & _M64
    return h ^ (h >> 32)


def _str_hash(text: str) -> int:
    data = text.encode("utf-8")
    n = len(data)
    h = _STR_HASH_SEED ^ n
    if n <= 15:
        padded = data + bytes(16 - n)
        h = _str_mix(h, int.from_bytes(padded[0:8], "little"))
        h = _str_mix(h, int.from_bytes(padded[8:16], "little"))
    else:
        for i in range(0, n, 8):
            h = _str_mix(h, int.from_bytes(data[i:i + 8], "little"))
    h ^= h >> 29
    h = (h * 0xBF58476D1CE4E5B9) & _M64
    h ^= h >> 32
    m = h & 0x7FFFFFFF
    return m if m else 1


def _text(v: object) -> str | None:
    """The value of a String constant, or None."""
    if isinstance(v, Atom) and isinstance(v.rparam, String):
        return v.rparam.value
    return None


# ── The interpreter ──────────────────────────────────────────────────────────

class Machine:
    def __init__(self, app: Application):
        self.app = app
        self.steps = 0
        self.depth = 0
        self.labels: dict[str, dict[str, int]] = {}
        self.statics: dict[str, dict] = {}
        self.written: set[int] = set()      # the objects this run has written

    # The values of an existing static's fields, decoded once.
    def _static_fields(self, name: str) -> tuple[Object, dict, list | None]:
        if name not in self.statics:
            g = self.app.globals.get(name)
            obj = self.app.objects.get(g.object_name) if g is not None and g.object_name else None
            if obj is None or obj.is_mutable or obj.is_foreign or not isinstance(g.init, NewStruct):
                raise Stop(OPAQUE)
            fields, items = {}, None
            for (fname, ftype), (_, v) in zip(obj.fields.fields[1:], g.init.values):
                if isinstance(ftype, Array):
                    items = [self.constant(x) for x in v.values] if isinstance(v, InitArray) else []
                else:
                    fields[fname] = self.constant(v)
            self.statics[name] = {"obj": obj, "fields": fields, "items": items}
        s = self.statics[name]
        return s["obj"], s["fields"], s["items"]

    def constant(self, p: RParam) -> object:
        """The value of an RParam that holds no variable (a static's data)."""
        match p:
            case Integer(value=v, precision=0):
                return Atom(p)
            case Integer(value=v, precision=bits):
                return _wrap(v, bits)
            case String() | Float():
                return Atom(p)
            case NullPointer():
                return NULL
            case ZeroOf(value_type=ty):
                return _zero(ty)
            case StaticObjectRef(name=n):
                return Ref(n)
            case GlobalVar(name=n):
                return self.global_value(n)
            case NewStruct(values=vs) | NewStructTyped(values=vs):
                return Struct_({n: self.constant(v) for n, v in vs})
            case GlobalFunction(name=n, object=o, external=False, c_symbol=None):
                return Fun(n, NULL if o is None else self.constant(o))
        raise Stop(OPAQUE)

    def global_value(self, name: str) -> object:
        g = self.app.globals.get(name)
        if g is None:
            raise Stop(OPAQUE)
        if g.object_name is not None:
            if g.object_name.startswith(_STUB_PREFIX) or g.lazy_init_function or g.init is None:
                raise Stop(OPAQUE)
            return Ref(name)
        if g.lazy_init_function or g.init is None:
            raise Stop(OPAQUE)
        if isinstance(g.init, (String, Float)) or (isinstance(g.init, Integer) and g.init.precision == 0):
            return Atom(g.init, name)
        return self.constant(g.init)

    def class_of(self, v: object) -> str:
        if isinstance(v, Obj):
            return v.cls
        if isinstance(v, Ref):
            g = self.app.globals[v.name]
            return g.object_name
        raise Stop(OPAQUE)

    def read(self, ptr: object, field: str, index: object | None) -> object:
        if isinstance(ptr, Obj):
            fields, items = ptr.fields, ptr.items
            obj = self.app.objects[ptr.cls]
        elif isinstance(ptr, Ref):
            obj, fields, items = self._static_fields(ptr.name)
        else:
            raise Stop(OPAQUE)
        if index is None:
            if field in fields:
                return fields[field]
            ftype = dict(obj.fields.fields).get(field)
            if ftype is None:
                raise Stop(OPAQUE)
            return _zero(ftype)
        if not isinstance(index, int) or items is None:
            raise Stop(OPAQUE)
        if index < 0 or index >= len(items):
            raise Stop(ABORT)
        return items[index]

    def write(self, ptr: object, field: str, index: object | None, value: object) -> None:
        if not isinstance(ptr, Obj):
            raise Stop(EFFECT if isinstance(ptr, Ref) else OPAQUE)
        self.written.add(id(ptr))
        if index is None:
            ptr.fields[field] = value
            return
        if not isinstance(index, int) or ptr.items is None or not 0 <= index < len(ptr.items):
            raise Stop(ABORT)
        ptr.items[index] = value

    def is_a(self, v: object, cls: str) -> int:
        if v is NULL:
            return 0
        c = self.class_of(v)
        return 1 if c == cls or cls in self.app.objects[c].extends else 0

    def eval(self, p: RParam, env: dict) -> object:
        match p:
            case StackVar(name=n):
                try:
                    return env[n]
                except KeyError:
                    raise Stop(OPAQUE) from None
            case ObjectField(pointer=ptr, field=f, index=idx):
                return self.read(self.eval(ptr, env), f, None if idx is None else self.eval(idx, env))
            case ArrayElement(pointer=ptr, field=f, index=idx):
                return self.read(self.eval(ptr, env), f, self.eval(idx, env))
            case StructField(struct=sp, field=f):
                s = self.eval(sp, env)
                if not isinstance(s, Struct_) or f not in s.fields:
                    raise Stop(OPAQUE)
                return s.fields[f]
            case NewStruct(values=vs) | NewStructTyped(values=vs):
                return Struct_({n: self.eval(v, env) for n, v in vs})
            case GlobalFunction(name=n, object=o, external=False, c_symbol=None):
                return Fun(n, NULL if o is None else self.eval(o, env))
            case RuntimeInvoke(function=fname, parameters=ps):
                return self.runtime(fname, self.eval(ps, env))
            case IntEqConst(value=v, const_val=c):
                x = self.eval(v, env)
                if isinstance(x, int):
                    return 1 if x == c else 0
                if c == 0 and (x is NULL or isinstance(x, (Obj, Ref))):
                    return 1 if x is NULL else 0           # a pointer against NULL
                raise Stop(OPAQUE)
            case VtableDiscriminator(value=v):
                return self.app.objects[self.class_of(self.eval(v, env))].discriminator
            case ObjVtableEq(value=v, class_name=cls) if cls is not None:
                return self.is_a(self.eval(v, env), cls)
            case NullPattern(tests=tests):
                for word, is_null in tests:
                    w = self.eval(word, env)
                    if isinstance(w, Atom):
                        raise Stop(OPAQUE)
                    null = w is NULL or w == 0 or (isinstance(w, Fun) and w.name is None)
                    if null != is_null:
                        return 0
                return 1
        return self.constant(p)

    def runtime(self, name: str, params: object) -> object:
        args = list(params.fields.values()) if isinstance(params, Struct_) else []
        if m := _INT_OP.match(name):
            return _int_op(int(m.group(1)), m.group(2), args)
        if m := _INT_CONV.match(name):
            if not isinstance(args[0], int):
                raise Stop(OPAQUE)
            return _wrap(args[0], int(m.group(1)))
        if m := _BIG_OP.match(name):
            return _big_op(m.group(1), args)
        if m := _BIG_FROM.match(name):
            if not isinstance(args[0], int):
                raise Stop(OPAQUE)
            return _big_atom(args[0])
        if m := _BIG_TO.match(name):
            b = _big(args[0])
            if b is None:
                raise Stop(OPAQUE)
            return _wrap(b, int(m.group(1)))
        if name == "str_hash":
            text = _text(args[0])
            if text is None:
                raise Stop(OPAQUE)
            return _str_hash(text)
        if name == "str_eq":
            a, b = _text(args[0]), _text(args[1])
            if a is None or b is None:
                raise Stop(OPAQUE)
            return 1 if a == b else 0
        if name == "array_index_check" and len(args) == 2:
            i, bound = args
            if not isinstance(i, int) or not isinstance(bound, int):
                raise Stop(OPAQUE)
            if not 0 <= i < bound:
                raise Stop(ABORT)
            return i
        if name == "object_same" and len(args) == 2:
            return 1 if _same(args[0], args[1]) else 0
        raise Stop(OPAQUE)

    def target(self, f: RParam, env: dict) -> tuple[str, object]:
        match f:
            case VirtualFunction(name=slot, object=op):
                this = self.eval(op, env)
                impl = dict(self.app.objects[self.class_of(this)].functions).get(slot)
                if impl is None:
                    raise Stop(OPAQUE)
                return impl, this
            case GlobalFunction(external=True) | GlobalFunction(c_symbol=str()):
                raise Stop(EFFECT if f.impure else OPAQUE)
        v = self.eval(f, env)
        if not isinstance(v, Fun) or v.name is None:
            raise Stop(OPAQUE)
        return v.name, v.env

    def call(self, name: str, this: object, args: list) -> object:
        fn = self.app.functions.get(name)
        if fn is None or fn.future or fn.bypass_async:
            raise Stop(OPAQUE)
        if fn.foreign_symbol is not None:
            raise Stop(OPAQUE)
        if self.depth >= DEPTH_LIMIT:
            raise Stop(BUDGET)
        self.depth += 1
        try:
            return self.run(fn, this, args)
        finally:
            self.depth -= 1

    def _labels(self, fn: Function) -> dict[str, int]:
        if fn.name not in self.labels:
            self.labels[fn.name] = {op.name: i for i, op in enumerate(fn.ops) if isinstance(op, Label)}
        return self.labels[fn.name]

    def run(self, fn: Function, this: object, args: list) -> object:
        params = fn.params.fields
        if len(args) != len(params) - 1:
            raise Stop(OPAQUE)
        env: dict[str, object] = {params[0][0]: this}
        for (pname, _), a in zip(params[1:], args):
            env[pname] = a
        labels = self._labels(fn)
        ops = fn.ops
        pc, cur, prev = 0, None, None
        while True:
            self.steps += 1
            if self.steps > STEP_LIMIT:
                raise Stop(BUDGET)
            if pc >= len(ops):
                raise Stop(OPAQUE)
            op = ops[pc]
            pc += 1
            match op:
                case Label(name=n):
                    prev, cur = cur, n
                case Phi():
                    # The joined values all read the edge just taken, together.
                    phis = [op]
                    while pc < len(ops) and isinstance(ops[pc], Phi):
                        phis.append(ops[pc])
                        pc += 1
                    values = []
                    for phi in phis:
                        src = dict(phi.sources).get(prev)
                        if src is None:
                            raise Stop(OPAQUE)
                        values.append(self.eval(src, env))
                    for phi, v in zip(phis, values):
                        if not isinstance(phi.target, StackVar):
                            raise Stop(OPAQUE)
                        env[phi.target.name] = v
                case Move(target=t, source=RuntimeInvoke(function="object_pin_set", parameters=NewStruct(
                        values=((_, po), (_, FieldOffset(field=fname)), (_, pv))))):
                    # A late write under the pin: the field is filled only if
                    # still empty, and the answer is what it held.
                    o, v = self.eval(po, env), self.eval(pv, env)
                    held = self.read(o, fname, None)
                    if held is NULL:
                        self.write(o, fname, None, v)
                    self.store(t, held, env)
                case Move(target=t, source=RuntimeInvoke(function="object_unpin", parameters=ps)):
                    # The one runtime operation with an effect on the run's
                    # objects: the end of a construction's early pin.
                    o = self.eval(ps, env)
                    o = next(iter(o.fields.values()), None) if isinstance(o, Struct_) else None
                    if not isinstance(o, Obj):
                        raise Stop(OPAQUE)
                    o.pinned = False
                    self.store(t, o, env)
                case Move(target=t, source=s):
                    self.store(t, self.eval(s, env), env)
                case Jump(name=n):
                    pc = labels[n]
                case JumpIf(label=n, condition=c, invert=inv):
                    v = self.eval(c, env)
                    if not isinstance(v, int):
                        raise Stop(OPAQUE)
                    if (v != 0) != inv:
                        pc = labels[n]
                case NewObject(name=cls, register=reg, size=size, pinned=pinned):
                    obj = self.app.objects.get(cls)
                    if obj is None or obj.is_mutable or obj.is_foreign:
                        raise Stop(OPAQUE)
                    items = None
                    if size is not None:
                        n = self.eval(size, env)
                        if not isinstance(n, int) or n < 0:
                            raise Stop(OPAQUE)
                        if n * 8 > DATA_LIMIT:
                            raise Stop(LARGE)
                        elem = obj.fields.fields[-1][1]
                        items = [_zero(elem.type if isinstance(elem, Array) else elem)] * n
                    o = Obj(cls, items)
                    o.pinned = pinned
                    self.store(reg, o, env)
                case Call(function=GlobalFunction(c_symbol="yafl_pin" | "yafl_unpin" as sym), parameters=ps,
                          register=reg):
                    # The stdlib's pin and unpin (System::Internal): a lock the
                    # run, alone, needs no part of. Its writes are its own.
                    args = self.eval(ps, env)
                    target = next(iter(args.fields.values()), None) if isinstance(args, Struct_) else None
                    if not isinstance(target, (Obj, Ref)):
                        raise Stop(OPAQUE)
                    if reg is not None:
                        self.store(reg, target if sym == "yafl_pin" else Struct_({}), env)
                case Call(function=f, parameters=ps, register=reg, impure=impure):
                    if impure or getattr(f, "impure", False):
                        raise Stop(EFFECT)
                    name, callee_this = self.target(f, env)
                    args = self.eval(ps, env)
                    result = self.call(name, callee_this,
                                       list(args.fields.values()) if isinstance(args, Struct_) else [])
                    if reg is not None:
                        self.store(reg, result, env)
                case Return(value=v):
                    return self.eval(v, env)
                case _:
                    raise Stop(OPAQUE)

    def store(self, target: RParam, value: object, env: dict) -> None:
        match target:
            case StackVar(name=n):
                env[n] = value
            case ObjectField(pointer=ptr, field=f, index=idx):
                self.write(self.eval(ptr, env), f, None if idx is None else self.eval(idx, env), value)
            case GlobalVar():
                raise Stop(EFFECT)
            case _:
                raise Stop(OPAQUE)


# ── Emitting a value as constants ────────────────────────────────────────────

class Emitter:
    """Turns a finished value into RParams, each object it built a static.
    `known` names the objects earlier values already made static."""
    def __init__(self, machine: Machine, counter: list[int], known: dict[int, str],
                 prefix: str = _STATIC_PREFIX, known_literals: dict[str, str] | None = None):
        self.m = machine
        self.counter = counter
        self.prefix = prefix
        self.known_literals = known_literals or {}
        self.literals: dict[str, str] = {}
        self.known = known
        self.names: dict[int, str] = {}
        self.globals: dict[str, Global] = {}

    def value(self, v: object, ty: Type, in_static: bool) -> RParam:
        """`v` as an RParam of type `ty`; in a static initialiser, or in code."""
        match v:
            case int():
                if isinstance(ty, Int):
                    return Integer(v, ty.precision)
                if isinstance(ty, IntPtr):
                    return Integer(v, 64) if v else ZeroOf(ty)
                raise Stop(OPAQUE)
            case Atom(rparam=rp, home=home):
                if in_static:
                    return rp
                if home is not None:
                    return GlobalVar(self.m.app.globals[home].type, home)
                if isinstance(rp, String) or (isinstance(rp, Integer) and rp.precision == 0):
                    return self.literal(rp)
                return rp
            case _Null():
                return NullPointer() if isinstance(ty, DataPointer) else ZeroOf(ty)
            case Ref(name=n):
                return StaticObjectRef(n) if in_static else GlobalVar(DataPointer(), n)
            case Obj():
                return self.object(v, in_static)
            case Fun(name=None):
                return ZeroOf(ty)
            case Fun(name=n, env=e):
                if not isinstance(ty, FuncPointer):
                    raise Stop(OPAQUE)
                return GlobalFunction(n, None if e is NULL else self.value(e, DataPointer(), in_static))
            case Struct_(fields=fs):
                if not isinstance(ty, Struct) or {n for n, _ in ty.fields} != set(fs):
                    raise Stop(OPAQUE)
                values = tuple((n, self.value(fs[n], ft, in_static)) for n, ft in ty.fields)
                return NewStruct(values) if in_static else NewStructTyped(ty, values)
        raise Stop(OPAQUE)

    def literal(self, rp: RParam) -> GlobalVar:
        """A global holding bigint or string literal `rp`, for code to read."""
        key = f"i:{rp.value}" if isinstance(rp, Integer) else f"s:{rp.value}"
        name = self.known_literals.get(key) or self.literals.get(key)
        if name is None:
            name = f"{self.prefix}{self.counter[0]}"
            self.counter[0] += 1
            self.literals[key] = name
            self.globals[name] = Global(name=name, type=rp.get_type(), init=rp)
        return GlobalVar(rp.get_type(), name)

    def object(self, o: Obj, in_static: bool) -> RParam:
        n = self.static(o)
        return StaticObjectRef(n) if in_static else GlobalVar(DataPointer(), n)

    def static(self, o: Obj) -> str:
        if id(o) in self.known:
            return self.known[id(o)]
        if id(o) in self.names:
            return self.names[id(o)]
        obj = self.m.app.objects[o.cls]
        fields, items = _shape(obj, o, shared=True)
        name = f"{self.prefix}{self.counter[0]}"
        self.counter[0] += 1
        self.names[id(o)] = name
        values = []
        for fname, ftype in obj.fields.fields[1:]:
            if isinstance(ftype, Array):
                values.append((fname, InitArray(ftype.type, tuple(
                    self.value(x, ftype.type, True) for x in items or ()))))
            elif fname == "$hash":
                values.append((fname, ZeroOf(ftype)))
            else:
                values.append((fname, self.value(fields.get(fname, _zero(ftype)), ftype, True)))
        self.globals[name] = Global(name=name, type=DataPointer(), init=NewStruct(tuple(values)),
                                    object_name=o.cls)
        return name


def _shape(obj: Object, o: Obj, shared: bool) -> tuple[dict, list | None]:
    """An object's fields and items as a literal holds them.

    A [pinnable] object with a capacity is late-written only into the room
    past its length, and the runtime's compaction already trims that room away
    (capacity reset to the length): so a literal has none, and nothing can ever
    write it. Any other [pinnable] object has slots a late write may still
    fill: a fresh one per run is fine, but one SHARED by every run is not."""
    if o.pinned:
        raise Stop(SHARED)                      # a construction still under way
    if not obj.is_pinnable:
        return o.fields, o.items
    cap, ln = obj.capacity_field, obj.length_field
    if cap is None or ln is None or o.items is None:
        if shared:
            raise Stop(SHARED)
        return o.fields, o.items
    n = o.fields.get(ln, 0)
    if not isinstance(n, int) or not 0 <= n <= len(o.items):
        raise Stop(OPAQUE)
    return {**o.fields, cap: n}, o.items[:n]


def _objects_in(v: object) -> list:
    """The objects a value holds directly: itself, or inside a struct or a
    closure's environment."""
    if isinstance(v, Obj):
        return [v]
    if isinstance(v, Struct_):
        return [o for x in v.fields.values() for o in _objects_in(x)]
    if isinstance(v, Fun):
        return _objects_in(v.env)
    return []


def _same(a: object, b: object) -> bool:
    """`object_same`: one object, by identity."""
    if isinstance(a, Obj) or isinstance(b, Obj):
        return a is b
    if isinstance(a, (Ref, _Null)) and isinstance(b, (Ref, _Null)):
        return a == b
    raise Stop(OPAQUE)


# ── A function's constants ───────────────────────────────────────────────────

def _construction_stores(ops: list, once: set[str]) -> dict[str, list[Move]]:
    """The constructions of a function: each object a NewObject makes, born
    unpinned, into a register assigned once, whose every store is a FRESH
    initialisation store — straight-line after the NewObject, before anything
    can see the object. Such an object is its stores: nothing else writes it."""
    news = {op.register.name: op for op in ops
            if isinstance(op, NewObject) and isinstance(op.register, StackVar)
            and op.register.name in once and not op.pinned}
    stores: dict[str, list[Move]] = {n: [] for n in news}
    for op in ops:
        if isinstance(op, Move) and isinstance(op.target, ObjectField) \
                and isinstance(op.target.pointer, StackVar) and op.target.pointer.name in stores:
            name = op.target.pointer.name
            if op.target.fresh and not op.target.fill:
                stores[name].append(op)
            else:
                news.pop(name, None)            # written later: not a literal
    return {n: stores[n] for n in news}


class Constants:
    """A function's constant variables. The IR is SSA: a variable assigned
    once holds its value wherever it is read. One assigned by a Move whose
    source is constant is a constant; one a construction makes, whose stores
    are all constant, is a LITERAL object — the same object every time it is
    asked for. A Move's value is evaluated on demand, in any order; the
    constructions are built once, up front, in op order."""
    def __init__(self, machine: "Machine", ops: list):
        self.machine = machine
        defs: dict[str, int] = {}
        for op in ops:
            for t in op.targets():
                if isinstance(t, StackVar):
                    defs[t.name] = defs.get(t.name, 0) + 1
        self.once = {n for n, k in defs.items() if k == 1}
        self.sources: dict[str, RParam] = {}
        for op in ops:
            if isinstance(op, Move):
                self.define(op.target, op.source)
        self.news = {op.register.name: op for op in ops if isinstance(op, NewObject)}
        self.builds = _construction_stores(ops, self.once)
        self.values: dict[str, object] = {}
        self.registers: dict[int, str] = {}     # id(literal object) -> its register
        self.active: set[str] = set()
        # The constructions, built once, up front, in op order: each from the
        # constants and constructions before it.
        for name in self.builds:
            try:
                o = self.__build(name)
            except Stop:
                continue
            self.values[name] = o
            self.registers[id(o)] = name

    def define(self, target: RParam, source: RParam) -> None:
        if isinstance(target, StackVar) and target.name in self.once:
            self.sources[target.name] = source

    def adopt(self, name: str, o: "Obj") -> None:
        """`name` now holds literal object `o` (a construction just written)."""
        self.values[name] = o
        self.registers[id(o)] = name

    def __getitem__(self, name: str) -> object:
        if name in self.values:
            return self.values[name]
        if name in self.active or name not in self.sources:
            raise Stop(OPAQUE)
        self.active.add(name)
        try:
            value = self.machine.eval(self.sources[name], self)
        finally:
            self.active.discard(name)
        self.values[name] = value
        return value

    def __build(self, name: str) -> "Obj":
        new = self.news[name]
        obj = self.machine.app.objects.get(new.name)
        if obj is None or obj.is_mutable or obj.is_foreign:
            raise Stop(OPAQUE)
        items = None
        if new.size is not None:
            n = self.machine.eval(new.size, self)
            if not isinstance(n, int) or n < 0:
                raise Stop(OPAQUE)
            elem = obj.fields.fields[-1][1]
            items = [_zero(elem.type if isinstance(elem, Array) else elem)] * n
        o = Obj(new.name, items)
        for store in self.builds[name]:
            index = store.target.index
            value = self.machine.eval(store.source, self)
            if index is None:
                o.fields[store.target.field] = value
            else:
                i = self.machine.eval(index, self)
                if not isinstance(i, int) or items is None or not 0 <= i < len(items):
                    raise Stop(OPAQUE)
                items[i] = value
        return o


def _constant_args(machine: Machine, ps: RParam, consts: Constants) -> list | None:
    """The call's arguments, if every one is a compile-time constant."""
    try:
        args = machine.eval(ps, consts)
    except Stop:
        return None
    return list(args.fields.values()) if isinstance(args, Struct_) else None


def _skipped(name: str) -> bool:
    """Machinery whose calls are never candidates."""
    return (name.startswith(_FETCH_PREFIX) or name.startswith("future_run$")
            or name in ("__entrypoint__", lowering.eager_globals.START))


# ── Stage 1: a literal and a call make a new literal ─────────────────────────

class Builder(Emitter):
    """Writes a value back into code: each object a construction — a NewObject
    and its fresh stores, children first — unless it is a literal the function
    already builds — earlier in the same block, so its register holds it here
    — and the run did not write, whose register it reuses."""
    def __init__(self, machine: Machine, counter: list[int], consts: Constants,
                 known_literals: dict[str, str], prefix: str, first: int, available: set[str]):
        super().__init__(machine, counter, {}, known_literals=known_literals)
        self.consts = consts
        self.available = available
        self.var_prefix = prefix
        self.first = first
        self.ops: list = []
        self.vars: list[tuple[str, Type]] = []
        self.built: dict[int, StackVar] = {}
        self.objects: list[tuple[str, Obj]] = []
        self.shaped: list[tuple[Obj, dict, list | None]] = []
        self.stores = 0
        self.unchanged: dict[int, bool] = {}

    def __unchanged(self, o: Obj) -> bool:
        """The run wrote neither `o` nor anything it reaches: the construction
        that built it still builds this value. (A list node the run did not
        write still reaches the one it did — its tail, newly linked.)"""
        if id(o) in self.unchanged:
            return self.unchanged[id(o)]
        self.unchanged[id(o)] = True                # a cycle reaches nothing new
        ok = id(o) not in self.m.written and all(
            self.__unchanged(x) for v in list(o.fields.values()) + list(o.items or ())
            for x in _objects_in(v))
        self.unchanged[id(o)] = ok
        return ok

    def object(self, o: Obj, in_static: bool) -> RParam:
        if id(o) in self.built:
            return self.built[id(o)]
        reg_name = self.consts.registers.get(id(o))
        if reg_name is not None and reg_name in self.available and self.__unchanged(o):
            return StackVar(DataPointer(nonnull=True), reg_name)
        obj = self.m.app.objects[o.cls]
        fields, items = _shape(obj, o, shared=False)
        self.shaped.append((o, fields, items))
        values = [(fname, ftype, self.value(fields.get(fname, _zero(ftype)), ftype, False))
                  for fname, ftype in obj.fields.fields[1:]
                  if not isinstance(ftype, Array) and fname != "$hash"]
        elem = obj.fields.fields[-1]
        item_values = ([self.value(x, elem[1].type, False) for x in items]
                       if items is not None and isinstance(elem[1], Array) else None)
        reg = StackVar(DataPointer(nonnull=True), f"{self.var_prefix}{self.first + len(self.vars)}")
        self.vars.append((reg.name, reg.type))
        self.ops.append(NewObject(o.cls, reg, None if item_values is None else Integer(len(item_values), 32)))
        for fname, ftype, rp in values:
            self.ops.append(Move(ObjectField(ftype, reg, o.cls, fname, None, fresh=True), rp))
        for i, rp in enumerate(item_values or ()):
            self.ops.append(Move(ObjectField(elem[1].type, reg, o.cls, elem[0], Integer(i, 32), fresh=True), rp))
        self.stores += len(values) + len(item_values or ())
        if self.stores * 8 > DATA_LIMIT:
            raise Stop(LARGE)
        self.built[id(o)] = reg
        self.objects.append((reg.name, o))
        return reg


def _drop_dead_constructions(ops: list) -> list:
    """Remove what folding left unread: each construction (a NewObject and its
    initialisation stores) whose object nothing else reads, and each plain
    Move into a variable nothing reads. To a fixpoint — a dead parent was the
    one reader of its children, a dead copy the one reader of its source."""
    def own(op) -> str | None:
        if (isinstance(op, Move) and isinstance(op.target, ObjectField) and op.target.fresh
                and isinstance(op.target.pointer, StackVar)):
            return op.target.pointer.name
        return None

    while True:
        news = {op.register.name for op in ops
                if isinstance(op, NewObject) and isinstance(op.register, StackVar)}
        read: set[str] = set()
        for op in ops:
            if isinstance(op, NewObject):
                if op.size is not None:
                    read.update(p.name for p in op.size.get_live_vars())
                continue
            mine = own(op)
            if mine is not None and mine in news:
                read.update(p.name for p in op.source.get_live_vars())
                if op.target.index is not None:
                    read.update(p.name for p in op.target.index.get_live_vars())
                continue
            live, _ = op.get_live_vars()
            read.update(p.name for p in live)
            read.update(p.name for p in op.saved_vars)
        dead_news = news - read
        kept = []
        for op in ops:
            if isinstance(op, NewObject) and isinstance(op.register, StackVar) and op.register.name in dead_news:
                continue
            if own(op) in dead_news:
                continue
            if (isinstance(op, Move) and isinstance(op.target, StackVar) and not op.keep
                    and op.target.name not in read):
                continue
            kept.append(op)
        if len(kept) == len(ops):
            return ops
        ops = kept


class _Stage1:
    def __init__(self, app: Application):
        self.app = dataclasses.replace(app, functions=dict(app.functions), globals=dict(app.globals))
        self.machine = Machine(self.app)
        self.counter = [0]
        self.literals: dict[str, str] = {}

    def fold_call(self, op: Call, consts: Constants, fn_index: int, available: set[str]) -> list | None:
        """The ops that build the call's value, ending in the Move into its
        register; or None when the call stays."""
        f = op.function
        if not isinstance(f, GlobalFunction) or f.object is not None or f.external or f.c_symbol:
            return None
        callee = self.app.functions.get(f.name)
        if callee is None or _skipped(f.name) or op.register is None or op.musttail or op.impure:
            return None
        args = _constant_args(self.machine, op.parameters, consts)
        if args is None:
            return None
        m = self.machine
        m.steps, m.depth = 0, 0
        m.written = set()
        start = self.counter[0]
        builder = Builder(m, self.counter, consts, self.literals, f"$lit{fn_index}$", len(self.new_vars),
                          available)
        try:
            value = m.call(f.name, NULL, args)
            rp = builder.value(value, callee.result, False)
        except Stop:
            self.counter[0] = start
            return None
        # The literals ARE their shapes from here on: what the code builds is
        # what a later run reads.
        for o, fields, items in builder.shaped:
            o.fields, o.items = fields, items
        self.literals.update(builder.literals)
        self.app.globals.update(builder.globals)
        for reg_name, o in builder.objects:
            consts.adopt(reg_name, o)
            available.add(reg_name)
        consts.define(op.register, rp)
        self.new_vars.extend(builder.vars)
        return builder.ops + [Move(op.register, rp)]

    def fold_function(self, name: str, fn_index: int) -> None:
        fn = self.app.functions[name]
        ops = list(fn.ops)
        consts = Constants(self.machine, ops)
        self.new_vars: list[tuple[str, Type]] = []
        out: list = []
        changed = False
        # The constructions built earlier in the current block: there, and
        # only there, their registers are certain to hold them.
        available: set[str] = set()
        for op in ops:
            if isinstance(op, Label):
                available = set()
            folded = self.fold_call(op, consts, fn_index, available) if isinstance(op, Call) else None
            if folded is None:
                out.append(op)
                if isinstance(op, NewObject) and isinstance(op.register, StackVar):
                    available.add(op.register.name)
            else:
                out.extend(folded)
                changed = True
        if changed:
            stack_vars = dataclasses.replace(fn.stack_vars, fields=fn.stack_vars.fields + tuple(self.new_vars))
            self.app.functions[name] = dataclasses.replace(
                fn, ops=tuple(_drop_dead_constructions(out)), stack_vars=stack_vars)

    def run(self) -> Application:
        for i, name in enumerate(list(self.app.functions)):
            if not _skipped(name):
                self.fold_function(name, i)
        return self.app


def fold_literal_calls(app: Application) -> Application:
    """Stage 1: each call whose arguments are literals is run, and its value
    written back as constructions — a literal for the next call to consume."""
    return _Stage1(app).run()


# ── Stage 2 helper: a global whose initialiser is a literal ──────────────────

def settle_globals(app: Application) -> Application:
    """Each lazy global whose initialiser just returns a constant is that
    constant: every read of it becomes the constant, and its forcing at
    startup goes, so the global and its initialiser fall away."""
    machine = Machine(app)
    settled: dict[str, RParam] = {}
    for name in sorted(app.globals):
        g = app.globals[name]
        if not (g.object_name and g.object_name.startswith(_STUB_PREFIX) and isinstance(g.init, NewStruct)):
            continue
        closure = dict(g.init.values).get("closure")
        fn = app.functions.get(closure.name) if isinstance(closure, GlobalFunction) else None
        if fn is None or not all(isinstance(op, (Move, Return)) for op in fn.ops):
            continue
        ret = fn.ops[-1] if fn.ops else None
        if not isinstance(ret, Return):
            continue
        consts = Constants(machine, list(fn.ops))
        emitter = Emitter(machine, [0], {})
        try:
            value = machine.eval(ret.value, consts)
            rp = emitter.value(value, fn.result, False)
        except Stop:
            continue
        if isinstance(value, Obj) or emitter.globals or not _settles(rp):
            continue
        settled[name] = rp
    if not settled:
        return app

    def read_of(p: RParam) -> RParam | None:
        """The constant an eager global's read stands for (eager_globals made
        each read a Move of the stub's `value`)."""
        if (isinstance(p, ObjectField) and p.field == "value" and p.index is None
                and isinstance(p.pointer, GlobalVar) and p.pointer.name in settled):
            return settled[p.pointer.name]
        return None

    functions = {}
    for name, fn in app.functions.items():
        ops = []
        for op in fn.ops:
            f = op.function if isinstance(op, Call) else None
            if (isinstance(f, GlobalFunction) and f.name.startswith(_FETCH_PREFIX)
                    and isinstance(f.object, GlobalVar) and f.object.name in settled
                    and not op.musttail):
                # A read of the global, or its forcing at startup (which reads
                # nothing): its initialiser has nothing left to do.
                if op.register is not None:
                    ops.append(Move(op.register, settled[f.object.name]))
            elif isinstance(op, Move) and read_of(op.source) is not None:
                ops.append(dataclasses.replace(op, source=read_of(op.source)))
            else:
                ops.append(op)
        functions[name] = dataclasses.replace(fn, ops=tuple(ops)) if ops != list(fn.ops) else fn
    return dataclasses.replace(app, functions=functions)


def _settles(rp: RParam) -> bool:
    """A constant that is the same value read anywhere: a literal, or a
    static object or literal global named in place."""
    return all(isinstance(p, (Integer, String, Float, NullPointer, ZeroOf, GlobalVar, GlobalFunction,
                              NewStructTyped, StaticObjectRef))
               for p in rp.flatten())
