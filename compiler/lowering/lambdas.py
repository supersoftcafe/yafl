from __future__ import annotations

import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t

from langtools import cast
from pyast.statement import ImportGroup




__empty_imports = ImportGroup(tuple())


def __create_unique_name(lmd: e.LambdaExpression) -> str:
    return f"$lambdas::lambda@{lmd.line_ref.hash6()}"


def __discover_captures(resolver: g.Resolver, lmd: e.LambdaExpression) -> list[tuple[str, t.TypeSpec]]:
    # Find all variable references and then remove the lambda parameters from the set
    references: dict[str, t.TypeSpec] = {}
    def check_if_capture(resolver: g.Resolver, thing):
        if isinstance(thing, e.NamedExpression):
            found = resolver.find_data({thing.name})
            if len(found) == 1:
                references[thing.name] = found[0].statement.get_type()
        return thing
    lmd.search_and_replace(resolver, check_if_capture)
    params = set(p.name for p in lmd.parameters.flatten())
    captures = [(name, xtype) for name, xtype in references.items() if name not in params]
    return captures


def __redirect_references_to_class(xpr: e.Expression, cpt: list[tuple[str, t.TypeSpec]]) -> e.Expression:
    lr = xpr.line_ref
    def redirect_reference(resolver: g.Resolver, thing):
        if isinstance(thing, e.NamedExpression) and any(name for name, type in cpt if thing.name == name):
            return e.DotExpression(lr, e.NamedExpression(lr, "this"), thing.name)
        return thing
    result = xpr.search_and_replace(g.ResolverRoot([]), redirect_reference)
    return result


def __create_function_from_lambda(lmd: e.LambdaExpression, nme: str, xpr: e.Expression, cpt: list[tuple[str, t.TypeSpec]]) -> s.FunctionStatement:
    lr = lmd.line_ref
    statement = s.ReturnStatement(lr, xpr)
    # local_this = s.LetStatement(lr, "this", None, {}, None, t.ClassSpec(lr, nme)) if cpt else None
    return_type = cast(t.CallableSpec, lmd.return_type).result
    function = s.FunctionStatement(lr, nme, __empty_imports, {}, lmd.parameters, [statement], return_type) #, local_this)
    return function


def __create_class_from_lambda(lmd: e.LambdaExpression, nme: str, fnc: s.FunctionStatement, cpt: list[tuple[str, t.TypeSpec]]) -> s.ClassStatement|None:
    lr = lmd.line_ref
    if cpt:
        parameters = [s.LetStatement(lr, name, __empty_imports, {}, None, xtype) for name, xtype in cpt]
        parameter_type = t.TupleSpec(lr, [t.TupleEntrySpec(name, xtype) for name, xtype in cpt])
        parameter = s.DestructureStatement(lr, "_", __empty_imports, {}, None, parameter_type, parameters)
        attributes = {"final": e.IntegerExpression(lr, 1, 32)}
        xclass = s.ClassStatement(lr, nme, __empty_imports, attributes, parameter, [fnc], [], False, set(), [])
        return xclass
    else:
        return None


def __create_new_expression(cls: s.ClassStatement|None, fnc: s.FunctionStatement, cpt: list[tuple[str, t.TypeSpec]]) -> e.Expression:
    lr = fnc.line_ref
    if cpt:
        captures = [e.TupleEntryExpression(name, e.NamedExpression(lr, name)) for name, xtype in cpt]
        parameters = e.TupleExpression(lr, captures)                 # Capture parameters for class constructor
        clstype = t.ClassSpec(lr, cls.name)                          # Reference to class type
        newexpression = e.NewExpression(lr, clstype, parameters)     # Construct class with captured variables
        dotexpression = e.DotExpression(lr, newexpression, fnc.name) # Get function pointer
        return dotexpression
    else:
        return e.NamedExpression(lr, fnc.name)


def __scan_function_and_export_lambdas(statement: s.Statement) -> (s.Statement, list[s.Statement]):
    exported_statements = []

    def export_if_lambda(resolver: g.Resolver, lmd):
        if not isinstance(lmd, e.LambdaExpression):
            return lmd

        nme = __create_unique_name(lmd)
        cpt = __discover_captures(resolver, lmd)
        xpr = __redirect_references_to_class(lmd.expression, cpt)
        fnc = __create_function_from_lambda(lmd, nme, xpr, cpt)
        cls = __create_class_from_lambda(lmd, nme, fnc, cpt)
        result = __create_new_expression(cls, fnc, cpt)

        if cls:
            exported_statements.append(cls)
        exported_statements.append(fnc)
        return result

    statement = statement.search_and_replace(g.ResolverRoot([]), export_if_lambda)
    return statement, exported_statements


def __convert_lambdas_to_functions(statements: list[s.Statement]) -> list[s.Statement]:
    tmp_result = [__scan_function_and_export_lambdas(stm) for stm in statements]
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
