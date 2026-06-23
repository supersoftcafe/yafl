from __future__ import annotations

import dataclasses

import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t

from langtools import cast
from parsing.tokenizer import LineRef
from pyast.statement import ImportGroup




__empty_imports = ImportGroup(tuple())


def __create_unique_name(lmd: e.LambdaExpression, path: tuple[str, ...] = ()) -> str:
    # Path-based naming disambiguates lambdas that share a `line_ref` across
    # different monomorphisations.  `generics.py` substitutes type params into
    # a generic function's body without rewriting `line_ref`s, so the same
    # nested-fn declaration ends up in every specialisation at the same
    # source location.  Without the enclosing-statement names mixed in, two
    # specialisations of `fold<T,U>` called with different `U` types collide
    # on `lambda@<hash6>` and the second class overwrites the first.
    prefix = "$".join(path) + "$" if path else ""
    return f"$lambdas::lambda@{prefix}{lmd.line_ref.hash6()}"


def __collect_lambda_paths(stmt: s.Statement) -> dict[LineRef, tuple[str, ...]]:
    """Pre-order walk: record the path (sequence of enclosing
    NamedStatement names) for every LambdaExpression reachable from
    `stmt`.  Used by `__scan_function_and_export_lambdas` to assign a
    monomorphisation-unique class name to every lifted lambda.

    Generic recursion: walk every dataclass field that holds a Statement
    or Expression (or a list/tuple of them).  Only NamedStatement nodes
    extend the path; everything else passes through with the current
    path."""
    paths: dict[LineRef, tuple[str, ...]] = {}

    def walk(node, path: tuple[str, ...]) -> None:
        if isinstance(node, e.LambdaExpression):
            # Only the first occurrence wins.  After monomorphisation a
            # generic statement's lambdas may show up via multiple
            # search_and_replace paths; the first wins as a deterministic
            # tie-break.
            paths.setdefault(node.line_ref, path)
        new_path = path
        if isinstance(node, s.NamedStatement) and node.name:
            new_path = path + (node.name,)
        if not dataclasses.is_dataclass(node):
            return
        for f in dataclasses.fields(node):
            child = getattr(node, f.name, None)
            if isinstance(child, (s.Statement, e.Expression)):
                walk(child, new_path)
            elif isinstance(child, (list, tuple)):
                for item in child:
                    if isinstance(item, (s.Statement, e.Expression)):
                        walk(item, new_path)

    walk(stmt, ())
    return paths


def __discover_captures(resolver: g.Resolver, lmd: e.LambdaExpression) -> list[tuple[str, t.TypeSpec]]:
    # Find all variable references and then remove the lambda parameters from the set.
    # Use the outer resolver (not the inner one updated by search_and_replace) so that
    # locally-defined names inside BlockExpression bodies are not mistakenly treated as
    # free variables that need to be captured.
    #
    # GLOBAL-scoped references (top-level functions, top-level lets, lifted
    # lambdas) are accessible by name from any function the lambda is
    # lifted into, so threading them through a closure object is pure
    # overhead.  TRAIT scope still needs capture because trait instances
    # are bound through the enclosing function's `where` clause and that
    # context is lost on lift.
    #
    # LazyExpression nodes are treated as captures of the stub pointer.
    # `lower_lazy_lets` already rewrote every NamedExpression that resolves
    # to a `[lazy]` let into LazyExpression — so by the time we walk a
    # lifted lambda's body, the LazyExpression is the only handle on its
    # stub.  Capture as LazyStubSpec (always generates to DataPointer).
    references: dict[str, t.TypeSpec] = {}
    def check_if_capture(_inner_resolver: g.Resolver, thing):
        if isinstance(thing, e.NamedExpression):
            found = resolver.find_data(thing.name)
            if len(found) == 1 and found[0].scope != g.ResolvedScope.GLOBAL:
                references[thing.name] = found[0].statement.get_type()
        elif isinstance(thing, e.LazyExpression):
            found = resolver.find_data(thing.stub_name)
            if found and len(found) == 1 and found[0].scope != g.ResolvedScope.GLOBAL:
                references[thing.stub_name] = t.LazyStubSpec(thing.line_ref, thing.target_type)
        return thing
    lmd.search_and_replace(resolver, check_if_capture)
    params = set(p.name for p in lmd.parameters.flatten())
    captures = [(name, xtype) for name, xtype in references.items() if name not in params]
    return captures


def __redirect_references_to_class(xpr: e.Expression, cpt: list[tuple[str, t.TypeSpec]], self_ref_names: frozenset[str] = frozenset(), method_nme: str = "", cls_name: str = "") -> e.Expression:
    lr = xpr.line_ref
    capture_names = {name for name, _ in cpt}
    def redirect_reference(resolver: g.Resolver, thing):
        if isinstance(thing, e.NamedExpression):
            if thing.name in capture_names:
                return e.DotExpression(lr, e.NamedExpression(lr, "this"), thing.name)
            elif thing.name in self_ref_names:
                # Self-referential capture: reconstruct the fun_t from `this` rather
                # than reading a captured field (which would be null at creation time).
                return e.DotExpression(lr, e.NamedExpression(lr, "this"), method_nme)
        elif isinstance(thing, e.LazyExpression) and thing.stub_name in capture_names:
            # Captured stub: route stub access through `this.<stub_name>`
            # on the closure class.  LazyExpression's `captured_class`
            # field flips its generate path from StackVar/GlobalVar to
            # ObjectField on `this`.
            return dataclasses.replace(thing, captured_class=cls_name)
        return thing
    result = xpr.search_and_replace(g.ResolverRoot([]), redirect_reference)
    return result


def __create_function_from_lambda(lmd: e.LambdaExpression, nme: str, xpr: e.Expression, cpt: list[tuple[str, t.TypeSpec]]) -> s.FunctionStatement:
    lr = lmd.line_ref
    return_type = cast(t.CallableSpec, lmd.return_type).result
    body = e.BlockExpression(lr, [], xpr)
    function = s.FunctionStatement(lr, nme, __empty_imports, {}, (), lmd.parameters, body, return_type)
    return function


def __create_class_from_lambda(lmd: e.LambdaExpression, nme: str, fnc: s.FunctionStatement, cpt: list[tuple[str, t.TypeSpec]]) -> s.ClassStatement|None:
    lr = lmd.line_ref
    if cpt:
        parameters = [s.LetStatement(lr, name, __empty_imports, {}, (), None, xtype) for name, xtype in cpt]
        parameter_type = t.TupleSpec(lr, [t.TupleEntrySpec(name, xtype) for name, xtype in cpt])
        parameter = s.DestructureStatement(lr, "_", __empty_imports, {}, (), None, parameter_type, parameters)
        attributes = {"final": e.IntegerExpression(lr, 1, 32)}
        xclass = s.ClassStatement(lr, nme, __empty_imports, attributes, (), parameter, [fnc], [], False, set(), [])
        return xclass
    else:
        return None


def __create_new_expression(cls: s.ClassStatement|None, fnc: s.FunctionStatement, cpt: list[tuple[str, t.TypeSpec]]) -> e.Expression:
    lr = fnc.line_ref

    def _capture_read(name: str, xtype: t.TypeSpec) -> e.Expression:
        # A captured `[lazy]` stub must be read as the raw stub pointer, not
        # forced and not read as its (possibly struct-shaped) value type — the
        # slot holds a DataPointer stub regardless of the let's declared type.
        if isinstance(xtype, t.LazyStubSpec):
            return e.LazyExpression(lr, stub_name=name, target_type=xtype.target_type,
                                    stub_only=True)
        return e.NamedExpression(lr, name)

    if cpt:
        captures = [e.TupleEntryExpression(name, _capture_read(name, xtype)) for name, xtype in cpt]
        parameters = e.TupleExpression(lr, captures)                 # Capture parameters for class constructor
        clstype = t.ClassSpec(lr, cls.name)                          # Reference to class type
        newexpression = e.NewExpression(lr, clstype, parameters)     # Construct class with captured variables
        dotexpression = e.DotExpression(lr, newexpression, fnc.name) # Get function pointer
        return dotexpression
    else:
        return e.NamedExpression(lr, fnc.name)


def __scan_function_and_export_lambdas(statement: s.Statement, all_statements: list[s.Statement]) -> tuple[s.Statement, list[s.Statement]]:
    exported_statements = []
    # Build the path map BEFORE search_and_replace.  search_and_replace
    # clones nodes via `dataclasses.replace`, but `line_ref` is preserved
    # across the clone, so the dict keyed by line_ref still resolves
    # correctly when we receive the clone in `export_if_lambda`.
    lambda_paths = __collect_lambda_paths(statement)

    def export_if_lambda(resolver: g.Resolver, lmd):
        if not isinstance(lmd, e.LambdaExpression):
            return lmd

        nme = __create_unique_name(lmd, lambda_paths.get(lmd.line_ref, ()))
        cpt = __discover_captures(resolver, lmd)

        # Remove self-referential captures: a capture whose declared type is
        # the same object as lmd.return_type is the LetStatement that binds
        # this very lambda (letrec). Capturing it stores null (fun_t{0}) at
        # closure creation time. Instead, redirect self-calls to
        # `this.method` which reconstructs {.f=fn, .o=this} on the fly.
        self_ref_names = frozenset(name for name, xtype in cpt if xtype == lmd.return_type)
        cpt = [(name, xtype) for name, xtype in cpt if name not in self_ref_names]

        xpr = __redirect_references_to_class(lmd.expression, cpt, self_ref_names, nme, cls_name=nme)
        fnc = __create_function_from_lambda(lmd, nme, xpr, cpt)
        cls = __create_class_from_lambda(lmd, nme, fnc, cpt)
        result = __create_new_expression(cls, fnc, cpt)

        if cls:
            exported_statements.append(cls)
        else:
            exported_statements.append(fnc)
        return result

    # Pass the full statement list as the resolver root so that captured
    # references resolved via `_find_trait_data` can find specialized
    # (post-monomorphisation) trait classes — e.g. `Show$generic$str`.
    # An empty root here was fine pre-monomorphisation when traits stayed
    # generic, but after monomorphisation each `where Show<T>` constraint
    # rewrites to a concrete `Show$generic$<concrete>` and the lookup
    # needs the full statement list to find that class.
    statement = statement.search_and_replace(g.ResolverRoot(all_statements), export_if_lambda)
    return statement, exported_statements


def __convert_lambdas_to_functions(statements: list[s.Statement]) -> list[s.Statement]:
    tmp_result = [__scan_function_and_export_lambdas(stm, statements) for stm in statements]
    statements, new_statements = zip(*tmp_result) if tmp_result else ([], [])
    statements = [x for x in statements if x is not None]
    new_statements = [x for lst in new_statements for x in lst]
    if new_statements:
        statements = statements + __convert_lambdas_to_functions(new_statements)
    return statements


def convert_lambdas_to_functions(statements: list[s.Statement]) -> list[s.Statement]:
    statements = __convert_lambdas_to_functions(statements)
    return statements


# TODO
#  1. Add 'this' to ClassStatement resolver
#     a. How to cope with nested classes?
#        Maybe this@sdfu9s using the LineRef of the class declaration?
#        Will have some tricky moments trying to figure out which 'this' to resolve to in nested cases.
#  2. Fix function to discover captures
