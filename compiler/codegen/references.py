"""What an IR node names directly: the functions, globals and objects it
references. The one reference model shared by every pass that reasons about
reachability (lowering/trim.py, lowering/eager_globals.py); the passes know the
model, not each other."""
from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from typing import Iterable

from codegen.ops import Op, Call, Return, ReturnVoid, Move, Label, JumpIf, IfTask, AssertNotTask, Jump, NewObject, SwitchJump, Abort, Phi
from codegen.ir import Function, Object, Global
from codegen.param import ObjectField, StackVar, GlobalVar, NewStruct, GlobalFunction, Integer, Float, RParam, \
    StructField, InitArray, RuntimeInvoke, String, VirtualFunction, PointerTo, NullPointer, NewStructTyped, IntEqConst, NullPattern, TagTask, ZeroOf, SyncWrap, ObjVtableEq, ArrayElement, VtableDiscriminator, StaticObjectRef, FunField, NarrowInt, MakeFun, FieldOffset


@dataclass
class References:
    globals: frozenset[str] = frozenset()
    objects: frozenset[str] = frozenset()
    functions: frozenset[str] = frozenset()

    def __or__(self, other):
        return References(self.globals | other.globals, self.objects | other.objects, self.functions | other.functions)

    def __sub__(self, other):
        return References(self.globals - other.globals, self.objects - other.objects, self.functions - other.functions)

    def __bool__(self):
        return bool(self.globals or self.objects or self.functions)


def union_references(iter: Iterable[References]) -> References:
    return reduce(lambda a, b: a | b, iter, References())


def rparam_references(p: RParam) -> References:
    match p:
        case InitArray():
            return union_references(rparam_references(x) for x in p.values)
        case NewStruct():
            return union_references(rparam_references(x) for _, x in p.values)
        case RuntimeInvoke():
            return rparam_references(p.parameters)
        case PointerTo():
            return rparam_references(p.value)
        case StructField():
            return rparam_references(p.struct)
        case String():
            return References()
        case Integer():
            return References()
        case Float():
            return References()
        case VirtualFunction():
            return rparam_references(p.object)
        case StackVar():
            return References()
        case ObjectField():
            x = rparam_references(p.pointer) | References(objects=frozenset([p.object_name]))
            return (x | rparam_references(p.index)) if p.index else x
        case ArrayElement():
            return (rparam_references(p.pointer) | rparam_references(p.index)
                    | References(objects=frozenset([p.object_name])))
        case FieldOffset():
            return References(objects=frozenset([p.object_name]))

        case GlobalFunction():
            if p.external:
                return References()
            x = References(functions=frozenset([p.name]))
            return (x | rparam_references(p.object)) if p.object else x
        case GlobalVar():
            return References(globals=frozenset([p.name]))

        case NullPointer():
            return References()
        case StaticObjectRef():
            # Keeps the referenced static instance alive.
            return References(globals=frozenset([p.name]))
        case IntEqConst():
            return rparam_references(p.value)
        case NullPattern():
            return union_references(rparam_references(word) for word, _ in p.tests)
        case VtableDiscriminator():
            return rparam_references(p.value)
        case ObjVtableEq():
            # Keep the referenced class's vtable alive when dispatching on it.
            on = References(objects=frozenset([p.class_name])) if p.class_name else References()
            return rparam_references(p.value) | on
        case NewStructTyped():
            return union_references(rparam_references(x) for _, x in p.values)
        case TagTask():
            return rparam_references(p.task)
        case ZeroOf():
            return References()
        case SyncWrap():
            return rparam_references(p.value)
        case FunField():
            return rparam_references(p.fun)
        case NarrowInt():
            return rparam_references(p.value)
        case MakeFun():
            return rparam_references(p.code) | rparam_references(p.env)

        case _:
            raise NotImplementedError(f"Unknown type of RParam {type(p)}")

def op_references(op: Op) -> References:
    match op:
        case Label():
            return References()
        case Move():
            return rparam_references(op.target) | rparam_references(op.source)
        case Jump():
            return References()
        case JumpIf():
            return rparam_references(op.condition)
        case Call():
            return rparam_references(op.function) | rparam_references(op.parameters) | (rparam_references(op.register) if op.register else References())
        case Return():
            return rparam_references(op.value)
        case ReturnVoid():
            return References()

        case NewObject():
            x = References(objects=frozenset([op.name]))
            return rparam_references(op.register) | ((x | rparam_references(op.size)) if op.size else x)

        case IfTask():
            return rparam_references(op.condition) | rparam_references(op.task_source)

        case AssertNotTask():
            return rparam_references(op.condition)

        case SwitchJump():
            return rparam_references(op.condition)

        case Abort():
            return References()

        case Phi():
            return reduce(lambda a, b: a | b, (rparam_references(v) for _, v in op.sources), rparam_references(op.target))

        case _:
            raise NotImplementedError(f"Unknown type of Op {type(op)}")

def global_references(g: Global) -> References:
    rp = rparam_references(g.init) if g.init else References()
    lf = References(functions=frozenset({g.lazy_init_function})) if g.lazy_init_function else References()
    lv = References(globals=frozenset({g.lazy_init_flag})) if g.lazy_init_flag else References()
    on = References(objects=frozenset({g.object_name})) if g.object_name else References()
    return rp | lf | lv | on

def object_references(o: Object) -> References:
    return References(functions=frozenset(rn for vn, rn in o.functions), objects=frozenset(o.extends))

def function_references(f: Function) -> References:
    return union_references(op_references(op) for op in f.ops)
