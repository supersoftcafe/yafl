from __future__ import annotations

from typing import Callable, Any
import dataclasses
import pyast.rewrite as rw
from dataclasses import dataclass, field
from functools import reduce

from langtools import checked_cast
from parsing.tokenizer import LineRef
from parsing.parselib import Error

import codegen.ops as cg_o
import codegen.param as cg_p
import codegen.typedecl as cg_t

import pyast.resolver as g
import pyast.statement as s
import pyast.typespec as t
import pyast.hints as h
import pyast.utils as u
from pyast.expression.base import Expression
from pyast.expression.literal import BoolExpression, IntegerExpression
from pyast.expression.tuple_expr import TupleExpression


@dataclass
class BuiltinOpExpression(Expression):
    type: t.BuiltinSpec
    op: StringExpression
    params: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            type=self.type.search_and_replace(resolver, replace),
            params=self.params.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.type

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement], h.Hints]:
        new_params, new_statements, hints = self.params.compile(resolver, None)
        # The declared type may be a full TypeSpec (array_builder_alloc's
        # Array<T>): compile it so the name resolves like any declared type.
        # BuiltinSpecs compile to themselves, so the historical ops are
        # untouched.
        new_type, type_stmts = self.type.compile(resolver)
        expr = dataclasses.replace(self, params=new_params, type=new_type)
        new_statements = list(new_statements) + list(type_stmts)
        # A primitive op owns its conversion to the receiver — its result
        # boxing into a union slot (`str_parse_int`'s bigint into `Int|None`).
        from pyast.expression.conversion import converted
        folded = expr._fold_const_compare()
        return (folded if folded is not None else converted(expr, expected_type, resolver)), list(new_statements), hints

    # An integer comparison of two bigint literals (the body of Int's `==`/`<`/
    # `>`) folds to a Bool literal. The language has no true/false token, so
    # this fold is what makes a constant Bool fold to a literal and inline.
    _INT_COMPARE = {
        "integer_test_eq": lambda a, b: a == b,
        "integer_test_lt": lambda a, b: a < b,
        "integer_test_gt": lambda a, b: a > b,
    }

    def _fold_const_compare(self) -> "BoolExpression | None":
        # The declared type may be a full TypeSpec (array_builder_alloc's
        # Array<T>) — only builtin-typed comparison ops fold.
        if not isinstance(self.type, t.BuiltinSpec) or self.type.type_name != "bool":
            return None
        predicate = BuiltinOpExpression._INT_COMPARE.get(self.op.value)
        if predicate is None or not isinstance(self.params, TupleExpression):
            return None
        operands = [entry.value for entry in self.params.expressions]
        if len(operands) != 2 or not all(
                isinstance(o, IntegerExpression) and o.precision == 0 for o in operands):
            return None
        return BoolExpression(self.line_ref, predicate(operands[0].value, operands[1].value))

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        return self.params.check(resolver, None)

    # The hash/identity internals are REPRESENTATION-AWARE: on a boxed enum
    # they are the real runtime calls; on a value representation there is no
    # object, so peek is the constant 0 (never cached), ref_eq is the constant
    # false (no identity to compare), and store just normalises the computed
    # hash (the 0-is-reserved contract holds either way). This is what lets
    # derived/wrapped code contain the shortcut UNCONDITIONALLY while the
    # boxing decision stays the compiler's.
    _REPR_AWARE = frozenset({"yafl_hash_peek", "yafl_hash_store", "yafl_ref_eq"})

    def __repr_aware(self, resolver: g.Resolver) -> "g.OperationBundle | None":
        if self.op.value not in BuiltinOpExpression._REPR_AWARE:
            return None
        if not isinstance(self.params, TupleExpression) or not self.params.expressions:
            return None
        subject_type = self.params.expressions[0].value.get_type(resolver)
        if (isinstance(subject_type, t.EnumSpec)
                and resolver.is_complex_root(subject_type.root_name)):
            return None    # boxed: the generic path emits the runtime call
        if self.op.value == "yafl_hash_peek":
            return g.OperationBundle((), (), cg_p.Integer(0, 32))
        if self.op.value == "yafl_ref_eq":
            return g.OperationBundle((), (), cg_p.Integer(0, 8))
        # store: the subject has no slot — evaluate ONLY the hash operand and
        # normalise it. The subject is a plain reference in all emitted code,
        # so skipping it drops no effects.
        h = self.params.expressions[1].value.generate(resolver)
        inv = cg_p.RuntimeInvoke("yafl_hash_norm",
                                 cg_p.NewStruct((("h", h.result_var),)),
                                 cg_t.Int(32))
        return h + g.OperationBundle((), (), inv)

    def __array_class_parts(self, resolver: g.Resolver, arr_type):
        """(cname, elem_ctype) for an Array-class type — the pieces an inline
        element store or sized allocation needs. The trailing storage member
        is contractually named "array" in the Object IR (classdef.py's
        global_codegen), regardless of the YAFL-level field name."""
        from pyast.statement.classdef import ClassStatement
        found = [rs.statement for rs in resolver.find_type(arr_type.name)]
        cls = found[0]
        assert isinstance(cls, ClassStatement), f"array builtin on non-class {arr_type.name}"
        params = cls.parameters.flatten()
        ap = next(p for p in params if isinstance(p.declared_type, t.ArrayFieldSpec))
        elem_ctype = ap.declared_type.element.generate(resolver)
        return arr_type.name, elem_ctype

    def __array_builder_alloc(self, resolver: g.Resolver) -> "g.OperationBundle":
        """Sized, unfilled allocation for a builder, born PINNED (held until
        array_builder_seal): array_create zero-fills pointer-bearing payloads
        and stamps length = CAPACITY, so the scanner traces every slot from
        birth. The element type rides the builtin's declared RESULT type; no
        init function runs."""
        cname, _ = self.__array_class_parts(resolver, self.type)
        cap_b = self.params.expressions[0].value.generate(resolver).with_prefix("abcap")
        rv = cg_p.StackVar(cg_t.DataPointer(), "abarr")
        alloc = g.OperationBundle((rv,), (cg_o.NewObject(cname, rv, size=cap_b.result_var, pinned=True),), rv)
        return cap_b + alloc

    def __array_builder_store(self, resolver: g.Resolver) -> "g.OperationBundle":
        """Inline pinned-array element store: a Move into the indexed
        trailing array field. A runtime call cannot express this — the
        element's C type varies per instantiation — and the builder holds
        the pin from allocation to seal, so the address is stable. NOT fresh:
        a builder crosses safe points (even suspensions, resuming on another
        worker), so a cycle may open between the allocation and the store.
        The barrier covers that, as it does for every other heap store."""
        arr_e = self.params.expressions[0].value
        idx_e = self.params.expressions[1].value
        val_e = self.params.expressions[2].value
        cname, elem_ctype = self.__array_class_parts(resolver, arr_e.get_type(resolver))
        arr_b = arr_e.generate(resolver).with_prefix("absarr")
        idx_b = idx_e.generate(resolver).with_prefix("absidx")
        val_b = val_e.generate(resolver).with_prefix("absval")
        store = cg_o.Move(
            cg_p.ObjectField(elem_ctype, arr_b.result_var, cname, "array",
                             idx_b.result_var, fill=True),
            val_b.result_var)
        done = g.OperationBundle((), (store,), cg_p.Integer(1, 8))
        return arr_b + idx_b + val_b + done

    def __new_pinned(self, resolver: g.Resolver) -> "g.OperationBundle":
        """`__builtin_op__<T>("new_pinned", C(...))`: the construction C, its
        heap object born PINNED — for an object written after allocation,
        across safe points (a list-builder cell's `next`). The owner releases
        it with object_unpin."""
        arg = self.params.expressions[0].value
        gen = getattr(arg, "generate_pinned", None)
        if gen is None:
            raise AssertionError(f"new_pinned takes a construction, not {type(arg).__name__}")
        return gen(resolver)

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        special = self.__repr_aware(resolver)
        if special is not None:
            return special
        if self.op.value == "new_pinned":
            return self.__new_pinned(resolver)
        if self.op.value == "array_builder_alloc":
            return self.__array_builder_alloc(resolver)
        if self.op.value == "array_builder_store":
            return self.__array_builder_store(resolver)
        params_bundle = self.params.generate(resolver)
        if params_bundle.result_var is None:
            raise ValueError("BuiltinOpExpression has no parameters")
        ptype = params_bundle.result_var.get_type()
        if not isinstance(ptype, cg_t.Struct):
            raise ValueError("BuiltinOpExpression parameters must be tuple")

        xtype = self.type.generate(resolver)
        xexpr = cg_p.RuntimeInvoke(self.op.value, params_bundle.result_var, xtype)
        final_bundle = g.OperationBundle( (), (), xexpr )

        return params_bundle + final_bundle



_PIN_SET = "'__builtin_pin_set__'"


@dataclass
class PinSetExpression(Expression):
    """`__builtin_pin_set__(obj, obj.field, value)`: the write-once publication
    in one step. Pins `obj`; if the field is empty, stores `value`; releases.
    Answers None when it stored, else what the field already held, left as it
    is: it only ever fills None, never replaces a value.

    For library use: the field must hold a heap object or None (`C|None`, C a
    class no lowering can flatten to a value), so an empty field is one NULL
    word the runtime can test and fill, and the class must admit a late write
    ([pinnable] or [mutable]). `obj` is a plain name and `obj.field` a field of
    it, so the field is named in YAFL and found in whichever copy the pin
    takes (yafl.h object_pin_set) — but only the store follows a move: a
    caller still holding the stale copy afterwards holds the stale copy.
    """
    subject: Expression    # a NamedExpression
    target: Expression     # a DotExpression on the same name
    value: Expression

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver,Any],Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            subject=self.subject.search_and_replace(resolver, replace),
            target=self.target.search_and_replace(resolver, replace),
            value=self.value.search_and_replace(resolver, replace))

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.target.get_type(resolver)

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list[s.Statement], h.Hints]:
        new_subject, subject_stmts, subject_hints = self.subject.compile(resolver, None)
        new_target, target_stmts, target_hints = self.target.compile(resolver, None)
        # Received by the FIELD's type, as `:=` receives it: a Node into a
        # `Node|None`.
        new_value, value_stmts, value_hints = self.value.compile(resolver, new_target.get_type(resolver))
        expr = dataclasses.replace(self, subject=new_subject, target=new_target, value=new_value)
        from pyast.expression.conversion import converted
        return (converted(expr, expected_type, resolver),
                list(subject_stmts) + list(target_stmts) + list(value_stmts),
                h.merge(subject_hints, target_hints, value_hints))

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        from pyast.expression.access import DotExpression, NamedExpression
        from pyast.statement.control import written_field, late_write_errors
        from pyast.statement.classdef import ClassStatement
        errors = (self.subject.check(resolver, None) + self.target.check(resolver, None)
                  + self.value.check(resolver, None))
        if not (isinstance(self.subject, NamedExpression) and isinstance(self.target, DotExpression)
                and isinstance(self.target.base, NamedExpression)
                and self.target.base.name == self.subject.name):
            return errors + [Error(self.line_ref,
                f"{_PIN_SET} takes (obj, obj.field, value): a name, then a field of it")]
        found = written_field(resolver, self.target, _PIN_SET)
        if isinstance(found, str):
            return errors + [Error(self.line_ref, found)]
        cdecl, _ = found
        errors.extend(late_write_errors(self.line_ref, cdecl, _PIN_SET))
        field_type = self.target.get_type(resolver)
        if field_type is not None and not self.__heap_or_none(resolver, field_type):
            errors.append(Error(self.line_ref,
                f"{_PIN_SET} fills a field holding a heap object or None: "
                f"'{self.target.name}' must be 'C|None', C a class always kept on the heap "
                f"(an interface, or a class that is [pinnable], [mutable] or [foreign], "
                f"implements an interface, or has more than "
                f"{ClassStatement.MAX_FLAT_STRUCT_FIELDS} fields)"))
        vtype = self.value.get_type(resolver)
        if (field_type is not None and vtype is not None
                and t.trivially_assignable_equals(resolver, field_type, vtype) is False):
            errors.append(Error(self.line_ref, "Incorrect type assigned to the field"))
        return errors

    @staticmethod
    def __heap_or_none(resolver: g.Resolver, field_type: t.TypeSpec) -> bool:
        """`C|None`, C a class that stays a heap object whatever the rest of the
        program does (ClassStatement.never_flattens): its None is NULL."""
        from pyast.statement.classdef import ClassStatement
        if not isinstance(field_type, t.CombinationSpec):
            return False
        members = field_type.repr_members()
        units = [m for m in members if isinstance(m, t.TupleSpec) and not m.entries]
        classes = [m for m in members if isinstance(m, t.ClassSpec)]
        if len(members) != 2 or len(units) != 1 or len(classes) != 1:
            return False
        found = resolver.find_type(classes[0].name)
        return (len(found) == 1 and isinstance(found[0].statement, ClassStatement)
                and found[0].statement.never_flattens())

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        from pyast.statement.control import written_field
        cdecl, data = written_field(resolver, self.target, _PIN_SET)
        field_type = self.target.get_type(resolver)
        obj_b = self.subject.generate(resolver).with_prefix("psobj")
        val_b = self.value.generate_to(resolver, field_type).with_prefix("psval")
        old = cg_p.StackVar(field_type.generate(resolver), "psold")
        # Kept when the answer goes unread: the call is the store.
        call = cg_o.Move(old, cg_p.RuntimeInvoke("object_pin_set", cg_p.NewStruct((
            ("o", obj_b.result_var),
            ("offset", cg_p.FieldOffset(cdecl.name, data.name)),
            ("v", val_b.result_var))), cg_t.DataPointer()), keep=True)
        return obj_b + val_b + g.OperationBundle((old,), (call,), old)
