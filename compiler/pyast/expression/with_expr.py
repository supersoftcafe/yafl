"""The `with` expression — copy-with-replacements, identity-preserving.

    with subject(name = value, …)

docs/preserving-rewrites-design.md, all rulings applied. The node exists only
until its types resolve: `compile` EXPANDS it into ordinary AST —

    Block[ let $ws = subject; let $w0 = v0; … ]
      Ternary( yafl_same($w0, $ws.f0) && …,
               $ws,                      # bit-identical: the ORIGINAL object
               match($ws)                # (or a direct constructor call when
                 (x: Leaf) => Leaf(…)    #  the subject type is a class or a
                 … )                     #  single variant)

— so every existing mechanism does the real work: the ternary's codegen, the
match's leaf dispatch (which is what preserves the DYNAMIC leaf under a
root-typed subject), constructors (fresh `$hash` by construction — a copy can
never serve a stale cache), and conversions. `yafl_same` is one C macro
(memcmp of the representations): reference compare for boxed fields, value
compare for scalars, byte compare for value structs — embedded references
compare as pointer words in place. Identity never surfaces to user code: the
two ternary arms are structurally identical, so the choice is unobservable.

Validation failures leave the node UNEXPANDED; `check` then reports — which
is what makes zero replacements an AST/check error, not a parse error, per
the ruling.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Callable

import pyast.resolver as g
import pyast.rewrite as rw
import pyast.typespec as t
from parsing.parselib import Error
from pyast.expression.base import Expression
from pyast.expression.literal import BoolExpression, StringExpression
from pyast.expression.builtin_op import BuiltinOpExpression
from pyast.expression.tuple_expr import TupleExpression, TupleEntryExpression


def _bare(name: str) -> str:
    return name.split("@")[0].rpartition("::")[2]


@dataclass
class WithExpression(Expression):
    subject: Expression
    replacements: TupleExpression

    # ── shape validation (parse stays permissive; check reports) ─────────────

    def __shape_error(self) -> str | None:
        if not self.replacements.expressions:
            return ("a `with` expression needs at least one replacement — "
                    "`with x()` copies nothing and means nothing")
        for en in self.replacements.expressions:
            if en.spread:
                return "a `with` replacement cannot be a spread"
            if not en.name:
                return ("`with` replacements must be named — "
                        "`with x(field = value)`")
        names = [en.name for en in self.replacements.expressions]
        if len(set(names)) != len(names):
            return "a `with` expression replaces each field at most once"
        return None

    # ── the subject's visible fields: (bare name, unique name, type) ─────────

    def __fields(self, resolver: g.Resolver) -> "list[tuple[str, str, t.TypeSpec]] | None":
        import pyast.statement as s
        stype = self.subject.get_type(resolver)
        if isinstance(stype, t.ClassSpec):
            found = resolver.find_type(stype.name)
            if len(found) != 1 or not isinstance(found[0].statement, s.ClassStatement):
                return None
            return [(_bare(let.name), let.name, let.declared_type)
                    for let in found[0].statement.parameters.flatten()]
        if isinstance(stype, t.EnumSpec):
            found = resolver.find_type(stype.root_name)
            if len(found) != 1 or not isinstance(found[0].statement, s.EnumStatement):
                return None
            covering = found[0].statement.covering_fields(stype.valid_leaf_names)
            return [(_bare(n), n, ft) for n, ft in covering]
        return None

    # ── compile: expand once the types allow it ──────────────────────────────

    def compile(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> tuple[Expression, list]:
        subject, stmts = self.subject.compile(resolver, None)
        repl, stmts2 = self.replacements.compile(resolver, None)
        node = dataclasses.replace(self, subject=subject,
                                   replacements=repl if isinstance(repl, TupleExpression) else self.replacements)
        if node.__shape_error() is not None:
            return node, stmts + stmts2
        expanded = node.__expand(resolver)
        if expanded is None:
            return node, stmts + stmts2      # types not resolved yet: wait
        from pyast.expression.conversion import converted
        return converted(expanded, expected_type, resolver), stmts + stmts2

    def __expand(self, resolver: g.Resolver) -> "Expression | None":
        import pyast.statement as s
        import pyast.expression as e
        fields = self.__fields(resolver)
        if fields is None:
            return None
        by_bare = {bare: (unique, ftype) for bare, unique, ftype in fields}
        for en in self.replacements.expressions:
            if en.name not in by_bare:
                return None                  # unknown field: check reports it
        stype = self.subject.get_type(resolver)
        lr = self.line_ref
        tag = lr.hash6()

        def ref(name: str) -> Expression:
            return e.NamedExpression(lr, name)

        subject_let = s.LetStatement(lr, f"$ws@{tag}", None, {}, (), self.subject, None)
        repl_lets: list = []
        repl_ref: dict[str, Expression] = {}
        for i, en in enumerate(self.replacements.expressions):
            repl_lets.append(s.LetStatement(lr, f"$w{i}@{tag}", None, {}, (),
                                            en.value, None))
            repl_ref[en.name] = ref(f"$w{i}")

        # SAME guard: every replacement bit-identical to the current field.
        cond: Expression | None = None
        for en in self.replacements.expressions:
            one = BuiltinOpExpression(lr, t.BuiltinSpec(lr, "bool"),
                StringExpression(lr, "yafl_same"),
                TupleExpression(lr, [
                    TupleEntryExpression(None, repl_ref[en.name]),
                    TupleEntryExpression(None, e.DotExpression(lr, ref("$ws"), en.name))]))
            cond = one if cond is None else e.TernaryExpression(lr, cond, one, BoolExpression(lr, False))

        # The copy: constructor call(s) mixing carried fields with replacements.
        def construct(ctor_name: str, ctor_fields, carrier: Callable[[str], Expression]) -> Expression:
            args = []
            for let in ctor_fields:
                bare = _bare(let.name)
                args.append(TupleEntryExpression(None,
                    repl_ref[bare] if bare in repl_ref else carrier(bare)))
            return e.CallExpression(lr, e.NamedExpression(lr, ctor_name),
                                    TupleExpression(lr, args))

        if isinstance(stype, t.ClassSpec):
            found = resolver.find_type(stype.name)
            cls = found[0].statement
            copy: Expression = construct(
                cls.name, cls.parameters.flatten(),
                lambda bare: e.DotExpression(lr, ref("$ws"), bare))
        else:
            root = resolver.find_type(stype.root_name)[0].statement
            leaves = _leaves(root, [])
            arms = []
            for i, (leaf_name, leaf_fields) in enumerate(leaves):
                if _bare(leaf_name) not in {_bare(v) for v in stype.valid_leaf_names}:
                    continue
                binder = f"$wx{i}"
                arms.append(_arm(lr, f"{binder}@{tag}", leaf_name,
                    construct(leaf_name, leaf_fields,
                              lambda bare, b=binder: e.DotExpression(lr, ref(b), bare))))
            if not arms:
                return None
            if len(arms) == 1:
                # A single valid leaf needs no dispatch — but the CARRIED
                # fields must still read through the binder-free subject.
                leaf_name, leaf_fields = next(
                    (ln, lf) for ln, lf in leaves
                    if _bare(ln) in {_bare(v) for v in stype.valid_leaf_names})
                copy = construct(leaf_name, leaf_fields,
                                 lambda bare: e.DotExpression(lr, ref("$ws"), bare))
            else:
                from pyast.match import MatchExpression
                copy = MatchExpression(lr, ref("$ws"), arms=arms)

        body = e.TernaryExpression(lr, cond, ref("$ws"), copy)
        return e.BlockExpression(lr, [subject_let] + repl_lets, body, tag=None)

    # ── check: only reached when expansion could not happen ──────────────────

    def check(self, resolver: g.Resolver, expected_type: t.TypeSpec | None) -> list[Error]:
        err = self.subject.check(resolver, None) + self.replacements.check(resolver, None)
        if err:
            return err
        shape = self.__shape_error()
        if shape is not None:
            return [Error(self.line_ref, shape)]
        stype = self.subject.get_type(resolver)
        if not isinstance(stype, (t.ClassSpec, t.EnumSpec)):
            return [Error(self.line_ref,
                "the subject of `with` must be a class- or enum-typed "
                "expression")]
        fields = self.__fields(resolver)
        if fields is None:
            return [Error(self.line_ref,
                "the subject type of `with` did not resolve")]
        visible = {bare for bare, _u, _t in fields}
        for en in self.replacements.expressions:
            if en.name not in visible:
                return [Error(self.line_ref,
                    f"`{en.name}` is not a field visible on the subject's "
                    f"type — `with` can only replace fields the static type "
                    f"guarantees")]
        return []

    def get_type(self, resolver: g.Resolver) -> t.TypeSpec | None:
        return self.subject.get_type(resolver)

    def search_and_replace(self, resolver: g.Resolver, replace: Callable[[g.Resolver, Any], Any]) -> Expression:
        return rw.rewrite(self, replace, resolver,
            subject=self.subject.search_and_replace(resolver, replace),
            replacements=self.replacements.search_and_replace(resolver, replace))

    def generate(self, resolver: g.Resolver) -> g.OperationBundle:
        raise ValueError(
            "a `with` expression must expand during compile — codegen "
            "reaching one means its subject type never resolved")


def _leaves(st, inherited: list) -> list:
    """(leaf unique name, fields root-down), declaration order — the same
    accumulation the leaf constructors use."""
    own = inherited + list(st.parameters.flatten())
    if not st.variants:
        return [(st.name, own)] if st.has_param_list else []
    out: list = []
    for v in st.variants:
        out.extend(_leaves(v, own))
    return out


def _arm(lr, binder: str, leaf_name: str, body):
    from pyast.match import MatchArm
    return MatchArm(lr, binder, t.NamedSpec(lr, leaf_name), body)
