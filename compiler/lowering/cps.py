from __future__ import annotations

# Convert the linear calling convention to continuation passing style
import dataclasses
from dataclasses import dataclass
from collections.abc import Iterator
from itertools import chain
from typing import Iterable

import langtools
from codegen.gen import Application
from codegen.ops import Op, Call, Return, Move, Label, JumpIf, Jump, NewObject
from codegen.things import Function, Object
from codegen.typedecl import FuncPointer, Void, Struct, ImmediateStruct, DataPointer, Int, Type
from codegen.param import ObjectField, StackVar, LParam, GlobalVar, NewStruct, GlobalFunction, Integer, RParam, \
    StructField
from functools import reduce



@dataclass
class BasicBlock:
    name: str # Also the name of a label that comes after the final call
    ops: list[Op] # Last op must be either Jump, Return or Call[musttail=True]...  but blocks don't necessarily split on these
    live: dict[StackVar, LParam] # Set of parameters that must be saved before entering this block
    result: LParam|None


__frame_param_var = StackVar(DataPointer(), "$frame")
__frame_param_decl: tuple[str, Type] = ("$frame", DataPointer())
__continuation_param_var = StackVar(FuncPointer(), "$continuation")
__async_params_type = Struct( ( ("this", DataPointer()), ("index", Int(32)) ) )



# TODO: Heap frame needs storage for each function call's return values
#       Shame we can't use the stack for those
#       Maybe get rid of the common async body, and generate the required code into every continuation function
#       Will still need to figure out which values are kept across function call sites
#
#       Or, for now, keep it simple.


def __discover_tail_calls(fn: Function) -> Function:
    # Anywhere where we can prove that a function-call's return value is returned exactly and without condition
    # we can replace it with a 'musttail=True' variant.
    ops = list(fn.ops)
    for index in reversed(range(0, len(ops)-1)):
        op1, op2 = ops[index], ops[index+1]
        if isinstance(op1, Call) and isinstance(op2, Return) and isinstance(op1.register, StackVar) and op1.register == op2.value:
            ops.pop(index+1) # Remove the return
            ops[index] = dataclasses.replace(op1, musttail=True, register=None)
    return dataclasses.replace(fn, ops=tuple(ops))


def __make_struct(value: RParam) -> RParam:
    xtype = value.get_type()
    if isinstance(xtype, Struct):
        return value
    return NewStruct((("item1", value),))


def __append_to_struct(struct: RParam, name: str, value: RParam) -> RParam:
    if isinstance(struct, NewStruct):
        return NewStruct(values = struct.values + ((name, value),))
    xtype = struct.get_type()
    if not isinstance(xtype, Struct):
        raise ValueError("not of type struct")
    return NewStruct(values = tuple(StructField(struct, nm) for nm, tp in xtype.fields) + ((name, value),))


def __heap_field_ref(var: StackVar, heap_object_name: str) -> LParam:
    return ObjectField(var.get_type(), __frame_param_var, heap_object_name, var.name, None)


def __vars_to_heap_fields(vars: Iterable[StackVar], heap_object_name: str) -> dict[StackVar, LParam]:
    return {var: __heap_field_ref(var, heap_object_name) for var in vars}


def __convert_var_to_field_refs(ops: Iterable[Op], vars_to_fields: dict[StackVar, LParam]) -> tuple[Op, ...]:
    return tuple(op.replace_params(lambda rparam: vars_to_fields.get(rparam) or rparam) for op in ops)


def __create_simple_continuation_function(fn: Function) -> Function:
    # Add a continuation function pointer parameter
    # Change return type to void
    param_fields = fn.params.fields + ((__continuation_param_var.name, __continuation_param_var.type),)
    def process_op(op: Op) -> Op:
        if isinstance(op, Return):
            # Replace ops.Return with a tail call to the continuation function, reuse the expression from the return statement
            return Call(__continuation_param_var, __make_struct(op.value), None, musttail=True)
        elif isinstance(op, Call) and op.musttail:
            # This is already a tail call, so we can make it a CPS tail call without worrying about saved state
            # Replace ops.Call[musttail=True] with a tail call to the continuation function
            return dataclasses.replace(op, parameters=__append_to_struct(op.parameters, __continuation_param_var.name, __continuation_param_var))
        else:
            return op
    ops = tuple(process_op(op) for op in fn.ops)
    return dataclasses.replace(fn, params=Struct(param_fields), result=Void(), ops=ops)


def __calculate_saved_vars(fn: Function) -> Function:
    # Input is the simple continuation function
    # Output is the same function with Call.saved_vars properly populated

    labels = {op.name: index for index, op in enumerate(fn.ops) if isinstance(op, Label)}
    def do_a_pass(ops: tuple[Op, ...]) -> tuple[Op, ...]:
        def saved_set_at(index: int) -> frozenset[StackVar]:
            op = ops[index]
            next_live, next_dead = op.get_live_vars()
            return next_live | op.saved_vars
        def calc(index: int) -> Op:
            op = fn.ops[index]
            ss1 = frozenset() if isinstance(op, Jump) or index >= len(fn.ops)-1 else saved_set_at(index+1)
            ss2 = frozenset() if not isinstance(op, JumpIf) else saved_set_at(labels[op.label])
            this_live, this_dead = op.get_live_vars()
            saved_vars = (ss1 | ss2) - this_dead
            return dataclasses.replace(op, saved_vars=saved_vars)
        return tuple(calc(index) for index in range(len(ops)))

    def iterate(ops: tuple[Op, ...]) -> tuple[Op, ...]:
        new_ops = do_a_pass(ops)
        return new_ops if ops == new_ops else iterate(new_ops)

    ops = iterate(fn.ops)
    return dataclasses.replace(fn, ops=ops)


def __create_basic_blocks(fn: Function, heap_object_name: str) -> list[BasicBlock]:
    # Each block (save the last) terminates on a Call that is a candidate to be converted
    # to a continuing tail call. The following block is the re-entry point.
    lifetime = __calculate_saved_vars(fn)
    partitions = langtools.partition(lifetime.ops, lambda op: isinstance(op, Call) and not op.musttail)
    def create_basic_block(index: int, ops: list[Op]) -> BasicBlock:
        name = f"cont${index}"
        def convert_to_tailcall(op: Op) -> Op:
            if not isinstance(op, Call) or op.musttail: return op
            parameters = __append_to_struct(op.parameters, __continuation_param_var.name,
                                            GlobalFunction(f"{fn.name}${name}", StackVar(DataPointer(), __frame_param_var.name)))
            return dataclasses.replace(op, parameters=parameters, register=None)
        last_op = ops[-1]
        result = last_op.register if isinstance(last_op, Call) else None
        ops = [convert_to_tailcall(op) for op in ops] + ([Label(name)] if isinstance(last_op, Call) and not last_op.musttail else [])
        live_vars = __vars_to_heap_fields(last_op.saved_vars, heap_object_name)
        return BasicBlock(name, ops, live_vars, result)
    top_and_tail = [create_basic_block(index, ops) for index, ops in enumerate(partitions)]
    return top_and_tail


def __create_heap_frame_object(fn: Function, heap_object_name: str, basic_blocks: list[BasicBlock]) -> Object:
    # Create heap object from the list of variables discovered to traverse function calls
    saved_fields: dict[StackVar, LParam] = {var: lparam for bb in basic_blocks for var, lparam in bb.live.items()}
    heap_fields = (("type",DataPointer()),) + tuple((var.name, lparam.get_type()) for var, lparam in saved_fields.items())
    return Object(heap_object_name, (), (), ImmediateStruct(heap_fields), comment=fn.comment) if heap_fields else None


def __create_launchpad_func(fn: Function, heap_object_name: str, basic_blocks: list[BasicBlock]) -> Function:
    # Starts with the simple continuation function and converts it to be a launchpad, that
    # is, it is the first function called to create the heap frame and continuations. Each
    # call site hit must create a heap object, saving exactly those fields dictated by the
    # call site. C compiler will eliminate dead code, so we don't worry about that.

    def transform_block(basic_block: BasicBlock) -> list[Op]:
        def transform_op(op: Op) -> list[Op]:
            if not isinstance(op, Call) or op.musttail:
                return [op]
            constructor = NewObject(heap_object_name, __frame_param_var)
            save_vars = [Move(field, var) for var, field in basic_block.live.items()]
            # TODO: Might want to default init other members
            parameters = __append_to_struct(op.parameters, __continuation_param_var.name, GlobalFunction(f"{fn.name}${basic_block.name}"))
            tailcall = dataclasses.replace(op, musttail=True, parameters=parameters)
            return [constructor] + save_vars + [tailcall]
        return [op2 for op1 in basic_block.ops for op2 in transform_op(op1)]

    ops = tuple(op for bb in basic_blocks for op in transform_block(bb))
    stack_vars = fn.stack_vars + Struct((("$frame", DataPointer()),))
    return dataclasses.replace(fn, ops=ops, stack_vars=stack_vars)


def __create_continuation_funcs(fn: Function, basic_blocks: list[BasicBlock]) -> list[Function]:
    vars_to_fields = {var: field for bb in basic_blocks for var, field in bb.live.items()}
    all_ops = [(op if not isinstance(op, Call) or op.musttail else dataclasses.replace(op, musttail=True)) for bb in basic_blocks for op in bb.ops]
    # Convert all function calls to continuation tail calls
    # Append all operations together into a complete list

    def create_cont_func(basic_block: BasicBlock) -> Function:
        # Create function with first param named after heap frame, and second param named something like "$value"
        #    IFF the call does not return Void...  AND, assign "$value" to the original call target
        # Add Jump to label
        # Append rest of ops list
        # Convert all var refs to field refs
        # Give function name using the label name as well
        name = f"{fn.name}${basic_block.name}"
        params, assignment =\
            (Struct((__frame_param_decl, ("$value", basic_block.result.get_type()))), [Move(basic_block.result, StackVar(basic_block.result.get_type(), "$value"))])\
            if basic_block.result else (Struct((__frame_param_decl,)), [])
        ops = __convert_var_to_field_refs(assignment + [Jump(basic_block.name)] + all_ops, vars_to_fields)
        return dataclasses.replace(fn, ops=ops, name=name, params=params)

    return [create_cont_func(bb) for bb in basic_blocks[0:-1]]


def __convert_function_to_cps(fn: Function) -> tuple[dict[str, Function], dict[str, Object]]:
    heap_object_name = f"{fn.name}$frame"

    tail_calls_func = __discover_tail_calls(fn)
    simple_cont_func = __create_simple_continuation_function(tail_calls_func)
    basic_blocks = __create_basic_blocks(simple_cont_func, heap_object_name)

    if len(basic_blocks) < 2:
        return {simple_cont_func.name: simple_cont_func}, dict()

    heap_frame_object = __create_heap_frame_object(simple_cont_func, heap_object_name, basic_blocks)
    launchpad_func = __create_launchpad_func(simple_cont_func, heap_object_name, basic_blocks)
    continue_funcs = __create_continuation_funcs(simple_cont_func, basic_blocks)

    functions = {x.name: x for x in [launchpad_func] + continue_funcs}
    objects = {heap_frame_object.name: heap_frame_object}
    return functions, objects


def convert_application_to_cps(app: Application) -> Application:
    cps_result = [__convert_function_to_cps(fn) for _, fn in app.functions.items()]
    result = Application()
    result.functions = reduce(lambda acc, v: acc | v[0], cps_result, dict())
    result.objects   = reduce(lambda acc, v: acc | v[1], cps_result, dict()) | app.objects
    result.globals   = app.globals
    return result

