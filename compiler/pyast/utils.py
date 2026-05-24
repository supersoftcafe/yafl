
from typing import Iterable
import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t


def __to_entry(let: s.LetStatement) -> e.TupleEntryExpression:
    return e.TupleEntryExpression(let.name, e.NamedExpression(let.line_ref, let.name))


def create_constructor(cls: s.ClassStatement) -> s.FunctionStatement:
    # Carry the class's generic type params through to the synthesized
    # constructor. Without this, `class Box<T>(value: T)` produces a
    # constructor with zero type params, and `Box<Int>(42)` is rejected
    # as "Excess type parameters" at the call site (and the class itself
    # fails its self-consistency check with "Not enough").
    type_params = tuple(tp.type for tp in cls.type_params)
    class_type = t.ClassSpec(cls.line_ref, cls.name, type_params=type_params)

    parameters = [__to_entry(let) for let in cls.parameters.flatten()]
    expression = e.TupleExpression(cls.line_ref, parameters)

    body = e.BlockExpression(cls.line_ref, [], e.NewExpression(cls.line_ref, class_type, expression))
    constructor = s.FunctionStatement(cls.line_ref, cls.name, cls.imports, {}, cls.type_params, cls.parameters, body, class_type)

    return constructor


def flatten_lists[_X,_Y](lists: Iterable[tuple[_X, list[_Y]]]) -> tuple[list[_X], list[_Y]]:
    xs: list[_X] = []
    ys: list[_Y] = []

    for x, ylist in lists:
        xs.append(x)
        ys.extend(ylist)

    return xs, ys

