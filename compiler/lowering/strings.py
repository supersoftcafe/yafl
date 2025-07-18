from __future__ import annotations

import pyast.statement as s
import pyast.expression as e

import pyast.resolver as g
import pyast.typespec as t

from pyast.statement import ImportGroup
from tokenizer import LineRef


def fix_global_strings(statements: list[s.Statement]) -> list[s.Statement]:
    # Find all string literals
    def find_all_string_literals(statements: list[s.Statement]) -> set[str]:
        all_string_literals: set[str] = set()
        def find_string_literal(resolver: g.Resolver, thing: any) -> any:
            if isinstance(thing, e.StringExpression):
                all_string_literals.add(thing.value)
            return thing
        for x in statements:
            x.search_and_replace(g.ResolverRoot([]), find_string_literal)
        return all_string_literals
    all_string_literals = find_all_string_literals(statements)

    # Create global 'let' declarations for each unique string literal
    def create_string(index: int, value: str) -> s.LetStatement:
        lr = LineRef("$strings", index + 1, 1)
        return s.LetStatement(lr, f"$strings::string@{index}",
                              ImportGroup(()), {},
                              e.StringExpression(lr, value),
                              t.BuiltinSpec(lr, "str"))
    global_statements = {value: create_string(index, value) for index,value in enumerate(all_string_literals)}

    # For each string generate a global reference
    global_references = {value: e.NamedExpression(statement.line_ref, statement.name)  for value, statement in global_statements.items()}

    # Replace all strings with their global reference counterparts
    def replace_string_expression(resolver: g.Resolver, thing: any) -> any:
        if isinstance(thing, e.StringExpression):
            return global_references[thing.value]
        return thing
    statements = [x.search_and_replace(g.ResolverRoot([]), replace_string_expression) for x in statements]

    # Return everything
    return list(global_statements.values()) + statements
