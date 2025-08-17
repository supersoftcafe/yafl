from __future__ import annotations

# Convert the linear calling convention to continuation passing style
import dataclasses
from dataclasses import dataclass
from collections.abc import Iterator
from itertools import chain
from typing import Iterable

import langtools
from codegen.gen import Application
from codegen.ops import Op, Call, Return, Move, Label, JumpIf, Jump, NewObject
from codegen.things import Function, Object, Global
from codegen.typedecl import FuncPointer, Void, Struct, ImmediateStruct, DataPointer, Int, Type
from codegen.param import ObjectField, StackVar, LParam, GlobalVar, NewStruct, GlobalFunction, Integer, RParam, \
    StructField, InitArray, Invoke, String, VirtualFunction, PointerTo
from functools import reduce


@dataclass
class _scan_sets:
    g: frozenset[str] = frozenset()
    o: frozenset[str] = frozenset()
    f: frozenset[str] = frozenset()

    def __or__(self, other):
        return _scan_sets(self.g | other.g, self.o | other.o, self.f | other.f)

    def __sub__(self, other):
        return _scan_sets(self.g - other.g, self.o - other.o, self.f - other.f)

    def __bool__(self):
        return bool(self.g or self.o or self.f)


def __reduce_scan_sets(iter: Iterable[_scan_sets]) -> _scan_sets:
    return reduce(lambda a, b: a | b, iter, _scan_sets())


def __scan_rparam(p: RParam) -> _scan_sets:
    match p:
        case InitArray():
            return __reduce_scan_sets(__scan_rparam(x) for x in p.values)
        case NewStruct():
            return __reduce_scan_sets(__scan_rparam(x) for _, x in p.values)
        case Invoke():
            return __scan_rparam(p.parameters)
        case PointerTo():
            return __scan_rparam(p.value)
        case StructField():
            return __scan_rparam(p.struct)
        case String():
            return _scan_sets()
        case Integer():
            return _scan_sets()
        case VirtualFunction():
            return __scan_rparam(p.object)
        case StackVar():
            return _scan_sets()
        case ObjectField():
            x = __scan_rparam(p.pointer)
            return (x | __scan_rparam(p.index)) if p.index else x

        case GlobalFunction():
            if p.external:
                return _scan_sets()
            x = _scan_sets(f=frozenset([p.name]))
            return (x | __scan_rparam(p.object)) if p.object else x
        case GlobalVar():
            return _scan_sets(g=frozenset([p.name]))

        case _:
            raise NotImplementedError(f"Unknown type of RParam {type(p)}")

def __scan_op(op: Op) -> _scan_sets:
    match op:
        case Label():
            return _scan_sets()
        case Move():
            return __scan_rparam(op.target) | __scan_rparam(op.source)
        case Jump():
            return _scan_sets()
        case JumpIf():
            return __scan_rparam(op.condition)
        case Call():
            return __scan_rparam(op.function) | __scan_rparam(op.parameters) | (__scan_rparam(op.register) if op.register else _scan_sets())
        case Return():
            return __scan_rparam(op.value)

        case NewObject():
            x = _scan_sets(o=frozenset([op.name]))
            return __scan_rparam(op.register) | ((x | __scan_rparam(op.size)) if op.size else x)

        case _:
            raise NotImplementedError(f"Unknown type of Op {type(op)}")

def __scan_global(g: Global) -> _scan_sets:
    rp = __scan_rparam(g.init) if g.init else _scan_sets()
    lf = _scan_sets(f=frozenset({g.lazy_init_function})) if g.lazy_init_function else _scan_sets()
    lv = _scan_sets(g=frozenset({g.lazy_init_flag})) if g.lazy_init_flag else _scan_sets()
    return rp | lf | lv

def __scan_object(o: Object) -> _scan_sets:
    return _scan_sets(f=frozenset(rn for vn, rn in o.functions), o=frozenset(o.extends))

def __scan_function(f: Function) -> _scan_sets:
    return __reduce_scan_sets(__scan_op(op) for op in f.ops)


def __removed_unused_stuff(from_app: Application, scan_sets: _scan_sets, to_app: _scan_sets) -> Application:
    from_globals   = [__scan_global(from_app.globals[    name]) for name in scan_sets.g]
    from_objects   = [__scan_object(from_app.objects[    name]) for name in scan_sets.o]
    from_functions = [__scan_function(from_app.functions[name]) for name in scan_sets.f]
    seen_sets = scan_sets | __reduce_scan_sets(from_globals + from_objects + from_functions)
    new_scan_sets = seen_sets - to_app
    if not new_scan_sets:
        app = Application()
        app.globals   = {name: from_app.globals[  name] for name in to_app.g}
        app.objects   = {name: from_app.objects[  name] for name in to_app.o}
        app.functions = {name: from_app.functions[name] for name in to_app.f}
        return app
    return __removed_unused_stuff(from_app, new_scan_sets, seen_sets | to_app)


def removed_unused_stuff(app: Application) -> Application:
    return __removed_unused_stuff(app, _scan_sets(f=frozenset(["__entrypoint__"])), _scan_sets())
