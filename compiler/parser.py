from __future__ import annotations

import dataclasses
from functools import reduce

from typing import Generic, TypeVar

import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t
import parselib as p
import pyast.utils


def __integer() -> p.Parser[e.Expression]:
    def _p(tokens: list[p.Token]) -> p.Result[e.IntegerExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.NUMBER:
                # Assume that head.value is an integer, check for format errors
                # We can assume this, because 'parse_float' comes first, and so only integers remain
                value = head.value
                starts = lambda x: value.startswith(x)
                ends = lambda x: value.endswith(x)
                radix, triml = (2, 2) if starts("0b") else (8, 2) if starts("0o") else (16, 2) if starts("0x") else (10, 0)
                size, trimr = (8, 2) if ends("i8") else (16, 3) if ends("i16") else (32, 3) if ends("i32") else (64, 3) if ends("i64") else (0, 0)
                value = value[ triml : len(value)-triml-trimr ].replace("_", "")
                try:
                    return p.Result.ok(e.IntegerExpression(head.line_ref, int(value, radix), size), tail, head.line_ref)
                except ValueError as err:
                    return p.Result.error(str(err), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)


def __float() -> p.Parser[e.Expression]:
    def _p(tokens: list[p.Token]) -> p.Result[e.FloatExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.NUMBER and "." in head.value:
                try:
                    return p.Result.ok(e.FloatExpression(head.line_ref, float(head.value)), tail, head.line_ref)
                except ValueError as err:
                    return p.Result.error(str(e), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)

def __string() -> p.Parser[e.Expression]:
    def _p(tokens: list[p.Token]) -> p.Result[e.StringExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.STRING:
                value = head.value
                if not value.endswith('"'):
                    return p.Result.error("string missing quote", tail, head.line_ref)
                # TODO: Process quotes
                return p.Result.ok(e.StringExpression(head.line_ref, value[1:len(value)-1]), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)


def __named() -> p.Parser[e.Expression]:
    def _p(tokens: list[p.Token]) -> p.Result[e.NamedExpression]:
        match tokens:
            case[head, *tail] if head.kind == p.TokenKind.IDENTIFIER:
                return p.Result.ok(e.NamedExpression(head.line_ref, head.value), tail, head.line_ref)
        return p.Result.none(tokens, tokens[0].line_ref)
    return p.Parser(_p)


def __to_dot_path(result: p.Result[tuple[e.Expression, list[tuple[str, e.Expression]]]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    def accumulate(left: e.Expression, entry: tuple[str, e.NamedExpression]):
        op, right = entry
        return e.DotExpression(right.line_ref, left, right.name)
    left_expr, right_list = result.value
    for op, expr in right_list:
        if not isinstance(expr, e.NamedExpression):
            return p.Result(None, result.tokens, result.line_ref, result.errors + [e.Error(expr.line_ref, "Must be an identifier")])
    expr = reduce(accumulate, right_list, left_expr)
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_named_fully_qualified(result: p.Result[e.NamedExpression, list[e.NamedExpression]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    first, path = result.value
    expr = e.NamedExpression(first.line_ref, "::".join(ne.name for ne in ([first] + path)))
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_builtin_op(result: p.Result[tuple[str, e.TupleExpression]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    typename, params_tuple = result.value
    op, *_ = params_tuple.expressions
    if not isinstance(op.value, e.StringExpression):
        return p.Result.error("__builtin_op__ first parameter must be a string", tokens, result.line_ref)
    expr = e.BuiltinOpExpression(result.line_ref, t.BuiltinSpec(result.line_ref, typename), op.value, params_tuple.trim_left(1))
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_invokes(result: p.Result[tuple[e.Expression, list[e.Expression]]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    def accumulate(left: e.Expression, entry: e.Expression):
        return e.CallExpression(tokens[0].line_ref, left, entry)
    left_expr, right_list = result.value
    expr = reduce(accumulate, right_list, left_expr)
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_pipeline(result: p.Result[tuple[e.Expression, list[e.Expression]]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    def accumulate(last_result: e.Expression, function: e.Expression) -> e.Expression:
        # Wrap last result in a tuple, just-in-case it isn't a tuple already.
        parameter = last_result if isinstance(last_result, e.TupleExpression)\
            else e.TupleExpression(last_result.line_ref, [e.TupleEntryExpression(None, last_result)])
        call = e.CallExpression(function.line_ref, function, parameter)
        return call
    left_expr, right_list = result.value
    expr = reduce(accumulate, right_list, left_expr)
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_call_operators(result: p.Result[tuple[e.Expression, list[tuple[str, e.Expression]]]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    def accumulate(left: e.Expression, entry: tuple[str, e.Expression]):
        op, right = entry
        line = tokens[0].line_ref
        return e.CallExpression(line,
            e.NamedExpression(line, f"`{op}`"),
            e.TupleExpression(line, [
                    e.TupleEntryExpression(None, left),
                    e.TupleEntryExpression(None, right)
                ]))
    left_expr, right_list = result.value
    expr = reduce(accumulate, right_list, left_expr)
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_ternery(result: p.Result[tuple[e.Expression, list[tuple[e.Expression, e.Expression]]]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    def get_right_expr(condition: e.Expression, expressions: list[tuple[e.Expression, e.Expression]]) -> e.Expression:
        if not expressions:
            return condition
        true_expr, false_expr = expressions[0]
        if len(expressions) == 1:
            return e.TerneryExpression(condition.line_ref, condition, true_expr, false_expr)
        else:
            false_expr = get_right_expr(false_expr, expressions[1:])
            return e.TerneryExpression(condition.line_ref, condition, true_expr, false_expr)
    left_expr, right_list = result.value
    expr = get_right_expr(left_expr, right_list)
    return p.Result(expr, result.tokens, result.line_ref, result.errors)


def __to_expr_tuple_entry(result: p.Result[tuple[list[str], e.Expression]], tokens: list[p.Token]) -> p.Result[e.TupleEntryExpression]:
    name, value = result.value
    return p.Result(e.TupleEntryExpression(p.first_or_none(name), value), result.tokens, result.line_ref, result.errors)


def __to_expr_tuple(result: p.Result[list[e.TupleEntryExpression]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    items = result.value
    return p.Result(e.TupleExpression(result.line_ref, items), result.tokens, result.line_ref, result.errors)


def __to_expr_lambda(result: p.Result[tuple[list[s.LetStatement], e.Expression]], tokens: list[p.Token]) -> p.Result[e.Expression]:
    params, expression = result.value
    params2 = s.DestructureStatement(result.line_ref, '_', None, {}, None, None, params)
    return p.Result(e.LambdaExpression(tokens[0].line_ref, params2, expression, None), result.tokens, result.line_ref, result.errors)


def __to_ret_statement(result: p.Result[e.Expression], tokens: list[p.Token]) -> p.Result[s.ReturnStatement]:
    return p.Result(s.ReturnStatement(result.line_ref, result.value), result.tokens, result.line_ref, result.errors)


def __to_action_statement(result: p.Result[e.Expression], tokens: list[p.Token]) -> p.Result[s.ReturnStatement]:
    return p.Result(s.ActionStatement(result.line_ref, result.value), result.tokens, result.line_ref, result.errors)


def __to_let_statement(result: p.Result[tuple[str|list[s.LetStatement], list[t.TypeSpec], list[e.Expression]]], tokens: list[p.Token]) -> p.Result[s.LetStatement]:
    target, dtype, value = result.value
    if isinstance(target, str):
        statement = s.LetStatement(tokens[0].line_ref, f"{target}@{result.line_ref.hash6()}", None, {}, p.first_or_none(value), p.first_or_none(dtype))
    elif isinstance(target, list):
        statement = s.DestructureStatement(tokens[0].line_ref, '_', None, {}, p.first_or_none(value), p.first_or_none(dtype), target)
    else:
        raise ValueError("invalid target type")
    return p.Result(statement, result.tokens, result.line_ref, result.errors)


def __to_import_statement(result: p.Result[list[str]], tokens: list[p.Token]) -> p.Result[s.ImportStatement]:
    return p.Result(s.ImportStatement(result.line_ref, '::'.join(result.value)),
                  result.tokens, result.line_ref, result.errors)


def __to_namespace_statement(result: p.Result[list[str]], tokens: list[p.Token]) -> p.Result[s.NamespaceStatement]:
    return p.Result(s.NamespaceStatement(result.line_ref, '::'.join(result.value)),
                  result.tokens, result.line_ref, result.errors)


def __to_named_spec(result: p.Result[tuple[list[str], str]], tokens: list[p.Token]) -> p.Result[t.NamedSpec]:
    path, name = result.value
    return p.Result(t.NamedSpec(result.line_ref, '::'.join(path + [name])),
                  result.tokens, result.line_ref, result.errors)


def __to_builtin_spec(result: p.Result[str], tokens: list[p.Token]) -> p.Result[t.NamedSpec]:
    name = result.value
    return p.Result(t.BuiltinSpec(result.line_ref, name),
                  result.tokens, result.line_ref, result.errors)


def __to_tuple_entry(result: p.Result[tuple[list[str], list[t.TypeSpec], list[e.Expression]]], tokens: list[p.Token]) -> p.Result[t.TupleEntrySpec]:
    name, e_type, default_expr = result.value
    if len(default_expr) > 0 and len(name) == 0:
        return p.Result.error("missing name on left of assignment", tokens, result.line_ref)
    if len(name) == 0 and len(e_type) == 0 and len(default_expr) == 0:
        return p.Result.none(tokens, result.line_ref)
    return p.Result(t.TupleEntrySpec(p.first_or_none(name), p.first_or_none(e_type), p.first_or_none(default_expr)),
                  result.tokens, result.line_ref, result.errors)


def __to_tuple_or_callable_spec(result: p.Result[tuple[list[t.TupleEntrySpec],list[t.TypeSpec]]], tokens: list[p.Token]) -> p.Result[t.TypeSpec]:
    entries, callable_result = result.value
    result_type = t.TupleSpec(result.line_ref, entries)
    if callable_result:
        result_type = t.CallableSpec(result.line_ref, result_type, callable_result[0])
    return p.Result(result_type, result.tokens, result.line_ref, result.errors)


def __to_tagged_spec_or_simple_type(result: p.Result[list[t.TypeSpec]], tokens: list[p.Token]) -> p.Result[t.TypeSpec]:
    entries: list[t.TypeSpec] = result.value
    if len(entries) == 1:
        return p.Result(entries[0], result.tokens, result.line_ref, result.errors)
    return p.Result(t.CombinationSpec(result.line_ref, entries), result.tokens, result.line_ref, result.errors)


def __to_function(result: p.Result[tuple[str, list[s.LetStatement], list[t.TypeSpec], list[s.Statement]]], tokens: list[p.Token]) -> p.Result[s.FunctionStatement]:
    name, params, dtype, body = result.value
    statement = s.FunctionStatement(result.line_ref, f"{name}@{result.line_ref.hash6()}", None, {}, s.DestructureStatement(result.line_ref, '_', None, {}, None, None, params), body,  p.first_or_none(dtype))
    return p.Result(statement, result.tokens, result.line_ref, result.errors)


def __to_class(result: p.Result[tuple[dict[str, e.Expression|None], str, list[s.LetStatement], list[t.TypeSpec], list[s.Statement]]], tokens: list[p.Token]) -> p.Result[s.ClassStatement]:
    attributes, name, params, implements, body = result.value
    statement = s.ClassStatement(result.line_ref, f"{name}@{result.line_ref.hash6()}", None, attributes or {}, s.DestructureStatement(result.line_ref, '_', None, {}, None, None, params), body, implements, False)
    return p.Result(statement, result.tokens, result.line_ref, result.errors)


def __to_interface(result: p.Result[tuple[dict[str, e.Expression|None], str, list[t.TypeSpec], list[s.Statement]]], tokens: list[p.Token]) -> p.Result[s.ClassStatement]:
    attributes, name, implements, body = result.value
    statement = s.ClassStatement(result.line_ref, f"{name}@{result.line_ref.hash6()}", None, attributes or {}, s.DestructureStatement(result.line_ref, '_', None, {}, None, None, []), body, implements, True)
    return p.Result(statement, result.tokens, result.line_ref, result.errors)


def __to_type_alias(result: p.Result[tuple[str, t.TypeSpec]], tokens: list[p.Token]) -> p.Result[s.TypeAliasStatement]:
    name, typespec = result.value
    statement = s.TypeAliasStatement(result.line_ref, f"{name}@{result.line_ref.hash6()}", None, {}, typespec)
    return p.Result(statement, result.tokens, result.line_ref, result.errors)

def __to_attributes(result: p.Result[list[tuple[str, list[e.Expression]]]], tokens: list[p.Token]) -> p.Result[dict[str, e.Expression]]:
    d = {key: (value[0] if value else None) for key, value in result.value[0]} if result.value else {}
    return p.Result(d, result.tokens, result.line_ref, result.errors)


def parse_type(tokens: list[p.Token]) -> p.Result[t.TypeSpec]:
    return __parse_type_any(tokens)
__parse_type = p.Parser(parse_type)


def parse_expression(tokens: list[p.Token]) -> p.Result[e.Expression]:
    return __parse_ternery(tokens) # Real function allows recursion
__parse_expression = p.Parser(parse_expression)


def parse_statement(tokens: list[p.Token]) -> p.Result[s.Statement]:
    return __parse_statement_any(tokens) # Real function allows recursion
__parse_statement = p.Parser(parse_statement)


############
## TypeSpecs

__parse_maybe_colon_type = p.maybe(p.requires(p.sym(":"), __parse_type, "missing type"))
__parse_maybe_equal_expr = p.maybe(p.requires(p.sym("="), __parse_expression, "missing default value"))

__parse_type_builtin = (p.discard_sym("__builtin_type__") & p.discard_sym("<") & p.ident() & p.discard_sym(">")) >> __to_builtin_spec
__parse_type_named = (p.many(p.ident() & p.discard_sym("::")) & p.ident()) >> __to_named_spec
__parse_type_tuple_entry = (p.maybe(p.ident()) & __parse_maybe_colon_type & __parse_maybe_equal_expr) >> __to_tuple_entry
__parse_type_tuple_or_callable = p.requires(
    p.discard_sym("("),
      ((p.delimited_list(__parse_type_tuple_entry, ",") & p.discard_sym(")") & __parse_maybe_colon_type) >> __to_tuple_or_callable_spec),
    "incomplete structured type")
__parse_type_any2 = __parse_type_tuple_or_callable | __parse_type_builtin | __parse_type_named
__parse_type_any = p.delimited_list(__parse_type_any2, "|") >> __to_tagged_spec_or_simple_type


##############
## Expressions

def parse_target_type_expr(tokens: list[p.Token]) -> p.Result[t.TypeSpec]:
    return __parse_target_type_expr_any(tokens)
__parse_target_type_expr = p.Parser(parse_target_type_expr)

__parse_destructure_parts = p.discard_sym('(') & p.delimited_list(__parse_target_type_expr, ',') & p.discard_sym(')')
__parse_target_type_expr_any = ((p.ident()|__parse_destructure_parts) & __parse_maybe_colon_type & __parse_maybe_equal_expr) >> __to_let_statement

__parse_expr_tuple_entry = (p.maybe(p.ident() & p.discard_sym("=")) & __parse_expression) >> __to_expr_tuple_entry
__parse_expr_tuple = p.requires(p.sym("("), p.delimited_list(__parse_expr_tuple_entry, ",") & p.discard_sym(")"), "invalid tuple") >> __to_expr_tuple
__parse_lambda = (__parse_destructure_parts & p.discard_sym("=>") & __parse_expression) >> __to_expr_lambda
__parse_builtin_op = p.requires(p.sym("__builtin_op__"), p.discard_sym("<") & p.ident() & p.discard_sym(">") & __parse_expr_tuple, "invalid use of __builtin_op__") >> __to_builtin_op
__parse_named_fully_qualified = (__named() & p.many(p.discard_sym("::") & __named())) >> __to_named_fully_qualified

__parse_terminal = __float() | __integer() | __string() | __parse_builtin_op | __parse_named_fully_qualified | __parse_lambda | __parse_expr_tuple

__parse_dot_path= (__parse_terminal & p.many(p.sym(".")             & __parse_terminal  )) >> __to_dot_path
__parse_invoke  = (__parse_dot_path & p.many(                         __parse_expr_tuple)) >> __to_invokes
__parse_pipeline= (__parse_invoke   & p.many(p.discard_sym("|>")    & __parse_invoke    )) >> __to_pipeline
__parse_divmul  = (__parse_pipeline & p.many(p.sym(["%", "/", "*"]) & __parse_pipeline  )) >> __to_call_operators
__parse_addsub  = (__parse_divmul   & p.many(p.sym(["+", "-"])      & __parse_divmul    )) >> __to_call_operators
__parse_compare = (__parse_addsub   & p.many(p.sym(["<", "=", ">"]) & __parse_addsub    )) >> __to_call_operators
__parse_ternery = (__parse_compare  & p.many(p.discard_sym("?") & __parse_compare & p.discard_sym(":") & __parse_compare )) >> __to_ternery


#############
## Statements

__parse_attributes = p.maybe(p.discard_sym("[") & p.delimited_list(
    p.ident() & p.maybe(p.discard_sym("=") & (__string() | __integer()))
    , ",") & p.discard_sym("]")) >> __to_attributes

__parse_action = p.block(
    __parse_expression >> __to_action_statement)

__parse_ret = p.block(p.requires(
    p.discard_sym("ret"),
    __parse_expression >> __to_ret_statement,
    "missing return value"))

__parse_fun = p.block(p.requires(
    p.discard_sym("fun"),
    (p.ident() & __parse_destructure_parts & __parse_maybe_colon_type & p.many(__parse_statement)) >> __to_function,
    "invalid function statement"))

__parse_class = p.block(p.requires(
    p.discard_sym("class"),
    (__parse_attributes & p.ident() & __parse_destructure_parts & __parse_maybe_colon_type & p.many(__parse_statement)) >> __to_class,
    "invalid class statement"))

__parse_interface = p.block(p.requires(
    p.discard_sym("interface"),
    (__parse_attributes & p.ident() & __parse_maybe_colon_type & p.many(__parse_statement)) >> __to_interface,
    "invalid interface statement"))

__parse_let = p.block(p.requires(
    p.discard_sym("let"),
    __parse_target_type_expr,
    "invalid let statement"))

__parse_type_alias = p.block(p.requires(
    p.discard_sym("typealias"),
    (p.ident() & p.discard_sym(":") & __parse_type) >> __to_type_alias,
    "invalid typealias statement"))

__parse_import = p.block(p.requires(
    p.discard_sym("import"),
    p.delimited_list(p.ident(), "::") >> __to_import_statement,
    "invalid import statement"))

__parse_namespace = p.block(p.requires(
    p.discard_sym("namespace"),
    p.delimited_list(p.ident(), "::") >> __to_namespace_statement,
    "invalid namespace statement"))

__parse_statement_any = p.block(__parse_class | __parse_interface | __parse_fun | __parse_let | __parse_type_alias | __parse_import | __parse_namespace | __parse_ret | __parse_action)



__parse = p.many(p.block(__parse_statement), skip=p.block(p.imm(None)))
def parse(tokens: list[p.Token]) -> p.Result[list[s.Statement]]:
    result = __parse(tokens)

    # Fix up namespace and import elements
    statements = result.value
    if not statements:
        return result

    imports = []
    for statement in statements:
        if isinstance(statement, s.ImportStatement):
            imports.append(statement)
        elif isinstance(statement, s.NamespaceStatement):
            imports.append(s.ImportStatement(statement.line_ref, statement.path))

    errors = result.errors
    import_group = s.ImportGroup(imports = tuple(imports))
    new_statements = []
    current_namespace = "Main::"

    for statement in result.value:
        match statement:
            case s.ImportStatement(): # Discard as it was processed earlier
                pass
            case s.NamespaceStatement(line_ref, path): # Note value and discard
                current_namespace = f"{path}::"
            case s.FunctionStatement() | s.LetStatement() | s.TypeAliasStatement() | s.ClassStatement(): # Rename and add to list
                statement = statement.add_namespace(current_namespace)
                statement = dataclasses.replace(statement, imports=import_group)
                new_statements.append(statement)
                if isinstance(statement, s.ClassStatement) and not statement.is_interface:
                    new_statements.append(pyast.utils.create_constructor(statement))

            case _: # Discard and report an error
                errors.append(p.Error(statement.line_ref, f"unexpected statement {type(statement)}"))

    return p.Result(new_statements, result.tokens, result.line_ref, errors)






def test():
    src = lambda content: p.tokenize(content, "filename.txt")
    # rlt = Result
    # err = Error
    # ok = Result.ok
    # err = Result.error
    lr = lambda line, offset: p.LineRef("filename.txt", line, offset)

    x = p.ident("fred")(src("fred bill"))
    assert x.value == "fred" and x.tokens[0].line_ref == lr(1, 6) and not x.errors

    prs = p.ident("bill") | p.ident("fred")
    v = src("fred bill")
    x = prs(v)
    assert x.value == "fred" and x.tokens[0].line_ref == lr(1, 6) and not x.errors

    x = p.ident(["bill", "fred"])(src("fred bill"))
    assert x.value == "fred" and x.tokens[0].line_ref == lr(1, 6) and not x.errors

    x = p.ident(["bill", "jeff"])(src("fred bill"))
    assert not x and x.tokens[0].line_ref == lr(1, 1)

    prs = p.ident(["bill", "fred"])
    x = prs(src("fred bill"))
    assert x.value == "fred" and x.tokens[0].line_ref == lr(1, 6) and not x.errors
    x = prs(x.tokens)
    assert x.value == "bill" and x.tokens[0].line_ref == lr(1, 10) and not x.errors

    prs = p.block(p.ident("fred"))
    x = prs(src("fred\n bill\n"))
    assert x.value == "fred"
    assert x.errors == [p.Error(lr(2, 2), "extra unexpected characters")]
    assert x.tokens[0].line_ref == lr(2, 6)

    prs = p.block(p.ident("fred") & p.ident("bill"))
    x = prs(src("fred\n bill\n"))
    assert x.value == ("fred", "bill")
    assert not x.errors
    assert x.tokens[0].line_ref == lr(2, 6)

    x = __parse_expression(src("1 + 2"))
    assert isinstance(x.value, e.BuiltinOpExpression) and x.value.op == "+"

    x = __parse_type_named(src("a"))
    assert isinstance(x.value, t.NamedSpec)

    x = __parse_type_tuple_entry(src("a"))
    assert isinstance(x.value, t.TupleEntrySpec)

    x = __parse_type_tuple_or_callable(src("(a)"))
    assert isinstance(x.value, t.TupleSpec)

    x = __parse_type_tuple_or_callable(src("(a,b)"))
    assert isinstance(x.value, t.TupleSpec)

    x = __parse_type_tuple_or_callable(src("(a:int)"))
    assert isinstance(x.value, t.TupleSpec)

    x = __parse_type_tuple_or_callable(src("(a:int=0)"))
    assert isinstance(x.value, t.TupleSpec)

    x = __parse_type_tuple_or_callable(src("(a:int):int"))
    assert isinstance(x.value, t.CallableSpec)

    x = __parse_expr_tuple_entry(src("a=1"))
    assert isinstance(x.value, e.TupleEntryExpression)

    x = __parse_expr_tuple(src("(a=1,2)"))
    assert isinstance(x.value, e.TupleExpression)


# test()
