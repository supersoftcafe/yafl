
import dataclasses
from typing import Iterable
import pyast.expression as e
import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t


def __to_entry(let: s.LetStatement) -> e.TupleEntryExpression:
    return e.TupleEntryExpression(let.name, e.NamedExpression(let.line_ref, let.name))


def __constructor_param(let: s.LetStatement) -> s.LetStatement:
    # The array field's *constructor* parameter is the initialiser function
    # `(Int32): Elem` — its results are tabulated into the trailing storage at
    # construction — not the storage type itself. Every other field is passed by
    # value as usual.
    if isinstance(let.declared_type, t.ArrayFieldSpec):
        lr = let.line_ref
        init_fn = t.CallableSpec(lr,
            t.TupleSpec(lr, [t.TupleEntrySpec(None, t.BuiltinSpec(lr, "int32"))]),
            let.declared_type.element)
        return dataclasses.replace(let, declared_type=init_fn)
    return let


def create_constructor(cls: s.ClassStatement) -> s.FunctionStatement:
    # Carry the class's generic type params through to the synthesized
    # constructor. Without this, `class Box<T>(value: T)` produces a
    # constructor with zero type params, and `Box<Int>(42)` is rejected
    # as "Excess type parameters" at the call site (and the class itself
    # fails its self-consistency check with "Not enough").
    type_params = tuple(tp.type for tp in cls.type_params)
    class_type = t.ClassSpec(cls.line_ref, cls.name, type_params=type_params)

    ctor_params = dataclasses.replace(cls.parameters,
        targets=[__constructor_param(let) for let in cls.parameters.targets])

    parameters = [__to_entry(let) for let in ctor_params.flatten()]
    expression = e.TupleExpression(cls.line_ref, parameters)

    body = e.BlockExpression(cls.line_ref, [], e.NewExpression(cls.line_ref, class_type, expression))
    constructor = s.FunctionStatement(cls.line_ref, cls.name, cls.imports, {}, cls.type_params, ctor_params, body, class_type)

    return constructor


def create_array_accessor(cls: s.ClassStatement) -> s.ClassStatement:
    """If `cls` declares a trailing array field, add an accessor *method* named
    after that field: a `(Int32): Elem` member whose body reads the element via
    `ArrayReadExpression(this, index)`. Just as the constructor is an ordinary
    function, so is the field — `obj.field` is a first-class function value that
    can be passed anywhere, and `obj.field(i)` is an ordinary call to it.

    The storage field keeps its own name (used by construction and codegen) but
    is hidden from member resolution by `ClassStatement.find_data`, so the name
    resolves to this accessor. The accessor shares the field's *simple* name yet
    carries a distinct hash, so the two never clash in slot/thunk creation."""
    af = next((f for f in cls.parameters.flatten()
               if isinstance(f.declared_type, t.ArrayFieldSpec)), None)
    if af is None:
        return cls

    lr = af.line_ref
    idx_name = f"index@{lr.hash6()}"
    idx_let = s.LetStatement(lr, idx_name, None, {}, (), None, t.BuiltinSpec(lr, "int32"))
    params = s.DestructureStatement(lr, '_', None, {}, (), None, None, [idx_let])
    body = e.BlockExpression(lr, [], e.ArrayReadExpression(
        lr, e.NamedExpression(lr, "this"), e.NamedExpression(lr, idx_name)))
    accessor = s.FunctionStatement(
        lr, f"{g.simple_name(af.name)}@{lr.hash6()}r", None, {}, (),
        params, body, af.declared_type.element)
    return dataclasses.replace(cls, statements=list(cls.statements) + [accessor])


def flatten_lists[_X,_Y](lists: Iterable[tuple[_X, list[_Y]]]) -> tuple[list[_X], list[_Y]]:
    xs: list[_X] = []
    ys: list[_Y] = []

    for x, ylist in lists:
        xs.append(x)
        ys.extend(ylist)

    return xs, ys

