from __future__ import annotations

import sys

import lowering.integers
import lowering.strings
import lowering.globalfuncs
import lowering.globalinit
import lowering.lambdas
import lowering.inlining
import lowering.cps
import lowering.trim

import pyast.statement as s
import pyast.expression as e

from codegen.typedecl import DataPointer, Struct, Int
from codegen.things import Function
import codegen.param as cg_p
import codegen.ops as cg_o

from codegen.gen import Application
import pyast.resolver as g
import pyast.typespec as t
from dataclasses import dataclass, fields

from tokenizer import tokenize, LineRef
from parselib import Error
from parser import parse
from pathlib import Path




@dataclass
class Input:
    content: str
    filename: str


if getattr(sys, 'frozen', False):
    # Running inside PyInstaller bundle
    __base_path = Path(sys._MEIPASS)
else:
    # Running normally
    __base_path = Path(__file__).parent
_stdlib_code_path = __base_path / "stdlib"



def _read_source(path: Path) -> Input:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    return Input(''.join(lines), path.name)

def _read_stdlib_code(use_stdlib: bool) -> list[Input]:
    if not use_stdlib: return []
    libs = [_read_source(x) for x in _stdlib_code_path.glob(f"*.yafl")]
    return libs


def __create_entry_point(main: s.FunctionStatement) -> Function:
    sv = cg_p.StackVar(Int(0), "result")
    return Function(
        name="__entrypoint__",
        params=Struct(fields=(("this", DataPointer()),)),
        result=Int(0),
        stack_vars=Struct(fields=(("result", Int(0)),)),
        ops=(
            cg_o.Call(
                function=cg_p.GlobalFunction(main.name),
                parameters=cg_p.NewStruct(()),
                register=sv
            ),
            cg_o.Return(sv)
        )
    )



def __create_c_code(statements: list[s.Statement], main: s.FunctionStatement, just_testing = False) -> str:
    a = Application()
    resolver = g.ResolverRoot(statements)
    for stmt in statements:
        match stmt:
            case s.FunctionStatement() as f:
                resolver2 = g.AddScopeResolution(resolver, f.imports)
                a.functions[f.name] = f.global_codegen(resolver2)
            case s.LetStatement() as l:
                resolver2 = g.AddScopeResolution(resolver, l.imports)
                global_vars, init_funcs = l.global_codegen(resolver2)
                # if not global_var.init:
                #     raise ValueError("Only literal global variables are supported so far. Dynamic initialisation is tbd.")
                for gv in global_vars:
                    a.globals[gv.name] = gv
                for fn in init_funcs:
                    a.functions[fn.name] = fn
            case s.ClassStatement() as c:
                resolver2 = g.AddScopeResolution(resolver, c.imports)
                xclass, functions = c.global_codegen(resolver2)
                a.objects[c.name] = xclass
                for function in functions:
                    a.functions[function.name] = function
            case s.TypeAliasStatement() as t:
                pass
            case _:
                raise ValueError(f"Unexpected type {type(stmt)}")

    a.functions["__entrypoint__"] = __create_entry_point(main)

    a = lowering.trim.removed_unused_stuff(a)
    a = lowering.globalfuncs.discover_global_function_calls(a)

    # Inlining with trimming is done iteratively
    a = lowering.trim.removed_unused_stuff(lowering.inlining.inline_small_functions(a))
    a = lowering.trim.removed_unused_stuff(lowering.inlining.inline_small_functions(a))
    a = lowering.trim.removed_unused_stuff(lowering.inlining.inline_small_functions(a))
    a = lowering.trim.removed_unused_stuff(lowering.inlining.inline_small_functions(a))

    # Lazy initialisation must be after inlining, and before CPS conversion.
    a = lowering.trim.removed_unused_stuff(lowering.globalinit.add_ops_to_support_global_lazy_init(a))

    a = lowering.trim.removed_unused_stuff(lowering.cps.convert_application_to_cps(a))
    return a.gen(just_testing=just_testing)


def __compile(stmt: s.Statement, glb: g.Resolver, expected_type: t.TypeSpec | None) -> list[s.Statement]:
    if isinstance(stmt, s.NamedStatement):
        glb = g.AddScopeResolution(glb, stmt.imports)
    result, extras = stmt.compile(glb, expected_type)
    result = [result] + extras
    if not isinstance(result, list):
        raise ValueError()
    if any(1 for x in result if isinstance(x, list)):
        raise ValueError()
    for x in result:
        if isinstance(x, list):
            raise ValueError()
    return result


def __is_main_function(stmt: s.FunctionStatement) -> bool:
    if ("::main@" not in stmt.name or
        not isinstance(stmt.return_type, t.BuiltinSpec) or
        not stmt.return_type.type_name == "bigint"):
        return False
    params_type = stmt.parameters.get_type()
    if not isinstance(params_type, t.TupleSpec):
        return False
    return len(params_type.entries) == 0


def __iterate_and_compile(statements: list[s.Statement], iteration_count: int = 1, just_testing = False) -> str|list[Error]:
    resolver = g.ResolverRoot(statements)

    new_statements = [x for stmt in statements for x in __compile(stmt, resolver, None)]
    new_errors = [x for stmt in new_statements for x in stmt.check(resolver, None)]
    mains = [stmt for stmt in new_statements if isinstance(stmt, s.FunctionStatement) and __is_main_function(stmt)]

    if not mains:
        new_errors += [Error(LineRef("none", 0, 0), "No main function found")]
    elif len(mains) > 1:
        new_errors += [Error(LineRef("none", 0, 0), "Too many main functions defined")]

    if new_statements != statements:
        # More work to do
        return __iterate_and_compile(new_statements, iteration_count + 1)
    elif new_errors:
        # Nothing more to do, just errors
        return new_errors
    else:
        # All ok so let's create some C code
        new_statements = lowering.strings.fix_global_strings(new_statements)
        new_statements = lowering.integers.fix_global_integers(new_statements)
        new_statements = lowering.lambdas.convert_lambdas_to_functions(new_statements)
        return __create_c_code(new_statements, mains[0], just_testing=just_testing)


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


def compile(source: list[Input], use_stdlib = False, just_testing = False) -> str:
    # Tokenize input
    statements, errors = __tokenize_and_parse(_read_stdlib_code(use_stdlib) + source)
    if errors:
        return __print_errors(errors)

    # Compile and find errors
    compiled_result = __iterate_and_compile(statements, just_testing=just_testing)
    if isinstance(compiled_result, list):
        return __print_errors(compiled_result)

    return compiled_result



