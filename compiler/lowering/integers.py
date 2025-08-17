from __future__ import annotations

import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t

from pyast.statement import ImportGroup
from tokenizer import LineRef


def fix_global_integers(statements: list[s.Statement]) -> list[s.Statement]:
    # Find all integer literals
    def find_all_integer_literals(statements: list[s.Statement]) -> set[int]:
        all_integer_literals: set[int] = set()
        def find_integer_literal(resolver: g.Resolver, thing: Any) -> Any:
            if isinstance(thing, e.IntegerExpression) and thing.precision == 0:
                all_integer_literals.add(thing.value)
            return thing
        for x in statements:
            x.search_and_replace(g.ResolverRoot([]), find_integer_literal)
        return all_integer_literals
    all_integer_literals = find_all_integer_literals(statements)

    # Create global 'let' declarations for each unique string literal
    def create_integer(index: int, value: int) -> s.LetStatement:
        lr = LineRef("$integers", index + 1, 1)
        return s.LetStatement(lr, f"$integers::integer@{'n'if value<0 else'p'}{(0-value)if value<0 else value}",
                              ImportGroup(()), {},
                              e.IntegerExpression(lr, value, 0),
                              t.BuiltinSpec(lr, "bigint"))
    global_statements = {value: create_integer(index, value) for index,value in enumerate(all_integer_literals)}

    # For each string generate a global reference
    global_references = {value: e.NamedExpression(statement.line_ref, statement.name) for value, statement in global_statements.items()}

    # Replace all strings with their global reference counterparts
    def replace_integer_expression(resolver: g.Resolver, thing: any) -> any:
        if isinstance(thing, e.IntegerExpression) and thing.precision == 0:
            return global_references[thing.value]
        return thing
    statements = [x.search_and_replace(g.ResolverRoot([]), replace_integer_expression) for x in statements]

    # Return everything
    return list(global_statements.values()) + statements
