"""Lower "simple" classes to flat structs + free functions.

A class qualifies as simple if it:
  - is not an interface
  - has no inheritance (implements list is empty)
  - has at most 4 fields
  - is not used as a base class by any other class
  - has no method references used standalone (i.e. every DotExpression referring to
    one of its methods is immediately called as a CallExpression)

Qualifying classes are replaced throughout the AST:
  - ClassSpec(name)  →  TupleSpec(fields)
  - NewExpression(TupleSpec, params)  →  params   (constructor becomes bare tuple)
  - CallExpression(NamedExpression(cls_name), args)  →  args  (constructor call → flat tuple)
  - b.method(args)   →  ClassName__method(b, args)  (method dispatch becomes a free-function call)

Each method is lifted to a top-level FunctionStatement whose first explicit parameter is
"$this: TupleSpec(fields)".  The ClassStatement itself is dropped.
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict

import pyast.statement as s
import pyast.expression as e
import pyast.typespec as t
import pyast.resolver as g

from langtools import cast
from pyast.statement import ImportGroup

__empty_imports = ImportGroup(tuple())

# Maximum number of fields a class may have to qualify for flat-struct lowering.
# Arbitrary but reasonable cut-off: a complex number (2 fields) and even a
# quaternion (4 fields) are optimised, but a matrix is not.
_MAX_FLAT_STRUCT_FIELDS = 4


def __is_simple_class(
        cls: s.ClassStatement,
        base_class_names: set[str]) -> bool:
    if cls.is_interface:
        return False
    if cls.implements:
        return False
    if cls.name in base_class_names:
        return False
    if len(cls.parameters.flatten()) > _MAX_FLAT_STRUCT_FIELDS:
        return False
    return True


def __lift_method(
        cls_name: str,
        tuple_spec: t.TupleSpec,
        method: s.FunctionStatement) -> s.FunctionStatement:
    """Create a free function equivalent for one class method.

    The lifted function is identical to the original except:
      - its name is  cls_name + "__" + method.name
      - a "$this: tuple_spec" LetStatement is prepended to the parameter list
      - every "this" NamedExpression in the body is renamed to "$this"
    """
    lr = method.line_ref

    def rename_this(_, thing):
        if isinstance(thing, e.NamedExpression) and thing.name == "this":
            return dataclasses.replace(thing, name="$this")
        return thing

    new_statements = [
        stmt.search_and_replace(g.ResolverRoot([]), rename_this)
        for stmt in method.statements
    ]

    this_let = s.LetStatement(lr, "$this", __empty_imports, {}, (), None, tuple_spec)
    new_targets = [this_let] + list(method.parameters.targets)
    new_params = dataclasses.replace(method.parameters, targets=new_targets)

    return dataclasses.replace(
        method,
        name=f"{cls_name}__{method.name}",
        parameters=new_params,
        statements=new_statements,
    )


def __find_simple_classes(
        statements: list[s.Statement]) -> tuple[dict[str, s.ClassStatement], set[str]]:
    """Return (simple_classes, base_class_names) from the statement list.

    simple_classes maps class name → ClassStatement for all initially qualifying classes
    (field-count, interface, and inheritance checks only; DotExpression scan is separate).
    base_class_names is the set of class names that appear as a parent of another class.
    """
    all_classes: dict[str, s.ClassStatement] = {
        stmt.name: stmt
        for stmt in statements
        if isinstance(stmt, s.ClassStatement)
    }

    base_class_names: set[str] = set()
    for cls in all_classes.values():
        for parent in (cls._all_parents or set()):
            if isinstance(parent, t.ClassSpec):
                base_class_names.add(parent.name)

    simple_classes = {
        name: cls
        for name, cls in all_classes.items()
        if __is_simple_class(cls, base_class_names)
    }
    return simple_classes, base_class_names


def __build_tuple_specs(
        simple_classes: dict[str, s.ClassStatement]) -> dict[str, t.TupleSpec]:
    """Build the initial TupleSpec for each simple class from its field list."""
    result: dict[str, t.TupleSpec] = {}
    for name, cls in simple_classes.items():
        fields = cls.parameters.flatten()
        entries = [t.TupleEntrySpec(f.name, f.declared_type, None) for f in fields]
        result[name] = t.TupleSpec(cls.line_ref, entries)
    return result


def __lower_nested_field_types(
        simple_classes: dict[str, s.ClassStatement],
        simple_tuple_specs: dict[str, t.TupleSpec],
        resolver: g.Resolver) -> dict[str, t.TupleSpec]:
    """Fixpoint: replace ClassSpec(A) → TupleSpec(A) inside each TupleSpec's field types.

    Ensures nested simple classes are represented as flat structs rather than
    heap-pointer DataPointer fields.  Returns an updated simple_tuple_specs dict.
    """
    def _replace(_, thing):
        if isinstance(thing, t.ClassSpec) and thing.name in simple_classes:
            return simple_tuple_specs[thing.name]
        return thing

    specs = dict(simple_tuple_specs)
    changed = True
    while changed:
        changed = False
        for name in list(specs.keys()):
            new_spec = specs[name].search_and_replace(resolver, _replace)
            if new_spec != specs[name]:
                specs[name] = new_spec
                changed = True
    return specs


def __exclude_standalone_method_refs(
        simple_classes: dict[str, s.ClassStatement],
        simple_tuple_specs: dict[str, t.TupleSpec],
        statements: list[s.Statement],
        resolver: g.Resolver,
) -> tuple[dict[str, s.ClassStatement], dict[str, t.TupleSpec]]:
    """Remove classes that have any standalone (uncalled) method DotExpression.

    Counts all method DotExpression occurrences (all_dot) vs those immediately used
    as CallExpression.function (called_dot).  If all_dot > called_dot for a class,
    a method reference escapes as a function pointer and the class cannot be lowered.
    """
    all_dot: defaultdict[str, int] = defaultdict(int)
    called_dot: defaultdict[str, int] = defaultdict(int)

    def _dot_scan(resolver_: g.Resolver, thing):
        if isinstance(thing, e.DotExpression):
            base_type = thing.base.get_type(resolver_)
            if isinstance(base_type, t.ClassSpec) and base_type.name in simple_classes:
                cls = simple_classes[base_type.name]
                method_names = {m.name for m in cls.statements if isinstance(m, s.FunctionStatement)}
                if thing.name in method_names:
                    all_dot[base_type.name] += 1
        elif isinstance(thing, e.CallExpression) and isinstance(thing.function, e.DotExpression):
            dot = thing.function
            base_type = dot.base.get_type(resolver_)
            if isinstance(base_type, t.ClassSpec) and base_type.name in simple_classes:
                cls = simple_classes[base_type.name]
                method_names = {m.name for m in cls.statements if isinstance(m, s.FunctionStatement)}
                if dot.name in method_names:
                    called_dot[base_type.name] += 1
        return thing

    for stmt in statements:
        stmt.search_and_replace(resolver, _dot_scan)

    kept_classes = {n: c for n, c in simple_classes.items()
                    if all_dot.get(n, 0) <= called_dot.get(n, 0)}
    kept_specs = {n: ts for n, ts in simple_tuple_specs.items()
                  if n in kept_classes}
    return kept_classes, kept_specs


def __build_replace_fn(
        simple_classes: dict[str, s.ClassStatement],
        simple_tuple_specs: dict[str, t.TupleSpec],
        tuple_id_to_class: dict[str, str],
):
    """Return the AST replace function that rewrites all simple-class references."""
    def replace_fn(resolver_: g.Resolver, thing):
        # ClassSpec → TupleSpec
        if isinstance(thing, t.ClassSpec) and thing.name in simple_classes:
            return simple_tuple_specs[thing.name]

        # NewExpression whose type was already converted to TupleSpec → just the params
        if isinstance(thing, e.NewExpression) and isinstance(thing.type, t.TupleSpec):
            return thing.parameter

        # Constructor calls: CallExpression(NamedExpression(cls_name), args) → flat tuple
        if isinstance(thing, e.CallExpression) and isinstance(thing.function, e.NamedExpression):
            if thing.function.name in simple_classes:
                return thing.parameter

        # Method calls: CallExpression(DotExpression(base, method), args)
        if isinstance(thing, e.CallExpression) and isinstance(thing.function, e.DotExpression):
            dot = thing.function
            base_type = dot.base.get_type(resolver_)
            cls_name = None
            if isinstance(base_type, t.ClassSpec) and base_type.name in simple_classes:
                cls_name = base_type.name
            elif isinstance(base_type, t.TupleSpec):
                uid = base_type.as_unique_id_str()
                cls_name = tuple_id_to_class.get(uid) if uid else None

            if cls_name is not None:
                cls = simple_classes[cls_name]
                method_names = {
                    m.name
                    for m in cls.statements
                    if isinstance(m, s.FunctionStatement)
                }
                if dot.name in method_names:
                    func_name = f"{cls_name}__{dot.name}"
                    lr = thing.line_ref
                    args = cast(e.TupleExpression, thing.parameter).expressions
                    new_args = e.TupleExpression(
                        lr,
                        [e.TupleEntryExpression(None, dot.base)] + list(args),
                    )
                    return e.CallExpression(lr, e.NamedExpression(lr, func_name), new_args)

        return thing

    return replace_fn


def lower_simple_classes(statements: list[s.Statement]) -> list[s.Statement]:
    resolver = g.ResolverRoot(statements)

    simple_classes, _ = __find_simple_classes(statements)
    if not simple_classes:
        return statements

    simple_tuple_specs = __build_tuple_specs(simple_classes)
    simple_tuple_specs = __lower_nested_field_types(simple_classes, simple_tuple_specs, resolver)

    simple_classes, simple_tuple_specs = __exclude_standalone_method_refs(
        simple_classes, simple_tuple_specs, statements, resolver)
    if not simple_classes:
        return statements

    tuple_id_to_class: dict[str, str] = {
        v.as_unique_id_str(): k
        for k, v in simple_tuple_specs.items()
        if v.as_unique_id_str() is not None
    }

    replace_fn = __build_replace_fn(simple_classes, simple_tuple_specs, tuple_id_to_class)

    # Lift each method to a top-level free function
    lifted_pre: list[s.FunctionStatement] = [
        __lift_method(cls_name, simple_tuple_specs[cls_name], method)
        for cls_name, cls in simple_classes.items()
        for method in cls.statements
        if isinstance(method, s.FunctionStatement)
    ]

    # Rewrite all non-simple-class statements, then the lifted methods
    new_statements = [
        stmt.search_and_replace(resolver, replace_fn)
        for stmt in statements
        if not (isinstance(stmt, s.ClassStatement) and stmt.name in simple_classes)
    ]
    lifted_final = [
        lifted.search_and_replace(resolver, replace_fn) for lifted in lifted_pre
    ]

    return new_statements + lifted_final
