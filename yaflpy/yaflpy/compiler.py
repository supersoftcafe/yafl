from __future__ import annotations

import pyast.statement as s

from collections import defaultdict

from codegen.typedecl import DataPointer, Struct, Int
from codegen.things import Function
import codegen.param as e
import codegen.ops as o

from codegen.gen import Application
import pyast.globalcontext as g
import pyast.typespec as t
from dataclasses import dataclass, fields

from pyast.statement import ImportGroup
from tokenizer import tokenize
from parselib import Error
from parser import parse


@dataclass
class Input:
    content: str
    filename: str


def __create_entry_point() -> Function:
    return Function(
        name="__entrypoint__",
        params=Struct(fields=(("this", DataPointer()),)),
        result=Int(32),
        stack_vars=Struct(fields=(("result", Int(32)),)),
        ops=(
            o.Call(
                function=e.GlobalFunction("Main::main"),
                parameters=(),
                register="result"
            ),
            o.Return(e.StackVar("result"))
        )
    )



def __create_c_code(statements: list[s.Statement], just_testing = False) -> str:
    a = Application()
    glb = g.GlobalRoot(statements)
    for stmt in statements:
        glb2 = g.AddScopeResolution(glb, stmt.imports)
        match stmt:
            case s.FunctionStatement() as f:
                a.functions[f.name] = f.global_codegen(glb2)
            case s.LetStatement() as l:
                a.globals[l.name] = l.global_codegen(glb)
            case s.TypeAliasStatement() as t:
                pass
            case _:
                raise ValueError(f"Unexpected type {type(stmt)}")
    a.functions["__entrypoint__"] = __create_entry_point()
    return a.gen(just_testing=just_testing)


def __compile(stmt: s.Statement, glb: g.Global, expected_type: t.TypeSpec|None) -> list:
    if isinstance(stmt, s.NamedStatement):
        glb = g.AddScopeResolution(glb, stmt.imports)
    result, extras, errors = stmt.compile(glb, expected_type)
    return [result] + extras + errors


def __iterate_and_compile(statements: list[s.Statement], iteration_count: int = 1, just_testing = False) -> str|list[Error]:
    glb = g.GlobalRoot(statements)

    statements_and_errors = [o for stmt in statements for o in __compile(stmt, glb, None)]
    new_statements = [o for o in statements_and_errors if isinstance(o, s.Statement)]
    new_errors = [o for o in statements_and_errors if isinstance(o, Error)]

    if not new_errors:
        # All ok so let's create some C code
        return __create_c_code(new_statements, just_testing=just_testing)
    elif new_statements != statements:
        # More work to do
        return __iterate_and_compile(new_statements, iteration_count + 1)
    else:
        # Nothing more to do, just errors
        return new_errors


def __tokenize_and_parse(source: list[Input]) -> (list[s.Statement], list[Error]):
    errors = []
    statements = []

    # Tokenize and parse input files
    for input in source:
        tokens = tokenize(input.content, input.filename)
        result = parse(tokens)

        if result.errors:
            errors += result.errors
        if result.value:
            statements += result.value

    return statements, errors


def __print_errors(errors: list[Error]) -> str:
    for error in sorted(set(errors)):
        print(error)
    return ""


def compile(source: list[Input], just_testing = False) -> str:
    statements, errors = __tokenize_and_parse(source)
    if errors:
        return __print_errors(errors)

    compiled_result = __iterate_and_compile(statements, just_testing=just_testing)
    if isinstance(compiled_result, list):
        return __print_errors(compiled_result)

    return compiled_result



