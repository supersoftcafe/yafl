from __future__ import annotations

import dataclasses
from typing import Callable, Any
from dataclasses import dataclass, field
from codegen.tools import mangle_name, to_pointer_mask

from codegen.ops import Op, Move, Call, NewObject, Jump, JumpIf, IfTask, SwitchJump, Return, ReturnVoid, Label

import codegen.typedecl as t
import codegen.param as p

def _fold_struct_field(rparam: p.RParam) -> p.RParam:
    """Fold StructField(NewStruct/NewStructTyped, name) → the named value directly.
    Eliminates construct-then-immediately-access patterns."""
    if isinstance(rparam, p.StructField):
        struct = rparam.struct
        if isinstance(struct, (p.NewStruct, p.NewStructTyped)):
            for name, value in struct.values:
                if name == rparam.field:
                    return value
    return rparam


def _is_cse_eligible(rparam: p.RParam) -> bool:
    """Pure computed expression whose value depends only on its inputs.
    Simple references (StackVar, GlobalVar, GlobalFunction) are excluded —
    they're not worth caching; copy propagation handles those."""
    return not isinstance(rparam, (p.StackVar, p.GlobalVar, p.GlobalFunction))


@dataclass(frozen=True)
class Function:
    name: str
    params: t.Struct            # First parameter must be DataPointer and must be named 'this'
    result: t.Type
    stack_vars: t.Struct
    ops: tuple[Op, ...]
    comment: str = ""
    foreign_symbol: str | None = None
    sync: bool = False

    def __post_init__(self):
        if len(self.params.fields) == 0:
            raise ValueError("Functions require a first parameter")
        name, field_type = self.params.fields[0]
        if not isinstance(field_type, t.DataPointer):
            raise ValueError("First parameter to a function must be a DataPointer")

    def __declare_vars(self, type_cache: dict[t.Type, tuple[str, str]], sep: str, p: t.Struct, end: str) -> str:
        return sep.join(f'{ptype.declare(type_cache)} {mangle_name(pname)}{end}' for pname, ptype in p.fields)

    def __prototype(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return (f"static NOINLINE\n"
                f"{self.result.declare(type_cache)} {mangle_name(self.name)}("
                f"{self.__declare_vars(type_cache, ', ', self.params, '')}"
                f")")

    @property
    def comment_line(self):
        return f"// {self.comment}\n" if self.comment else ""

    def to_c_extern(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        """Emit an extern declaration for the underlying C symbol, using the YAFL calling convention."""
        return (f"extern {self.result.declare(type_cache)} "
                f"{self.foreign_symbol}({self.__declare_vars(type_cache, ', ', self.params, '')});\n")

    def to_c_prototype(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return f"{self.comment_line}{self.__prototype(type_cache)};\n"

    def to_c_implement(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        vars_decl = self.__declare_vars(type_cache, '    ', self.stack_vars, ';\n')
        vars_section = f"    {vars_decl}\n" if vars_decl else ""
        return (f"{self.comment_line}{self.__prototype(type_cache)}\n"
                f"{{\n"
                f"{vars_section}"
                f"{''.join(op.to_c(type_cache) for op in self.ops)}"
                f"}}\n")

    def replace_params(self, replacer: Callable[[p.RParam], p.RParam]) -> Function:
        return dataclasses.replace(self, ops=tuple(op.replace_params(replacer) for op in self.ops))

    def simplify_control_flow(self) -> Function:
        ops = list(self.ops)
        changed = True
        while changed:
            changed = False
            new_ops: list[Op] = []
            i = 0
            while i < len(ops):
                op = ops[i]
                next_op  = ops[i + 1] if i + 1 < len(ops) else None
                next2_op = ops[i + 2] if i + 2 < len(ops) else None

                # goto L; L: → drop the goto
                if isinstance(op, Jump) and isinstance(next_op, Label) and op.name == next_op.name:
                    changed = True
                    i += 1
                    continue

                # if (c) goto L; L: → drop the conditional jump
                if isinstance(op, JumpIf) and isinstance(next_op, Label) and op.label == next_op.name:
                    changed = True
                    i += 1
                    continue

                # if (c) goto L1; goto L2; L1: → if (!c) goto L2; L1:
                if (isinstance(op, JumpIf) and not op.invert
                        and isinstance(next_op, Jump)
                        and isinstance(next2_op, Label)
                        and op.label == next2_op.name):
                    new_ops.append(dataclasses.replace(op, label=next_op.name, invert=True))
                    changed = True
                    i += 2  # consume JumpIf + Jump; Label stays
                    continue

                new_ops.append(op)
                i += 1
            ops = new_ops

        # Remove labels that no jump targets any more
        referenced: set[str] = set()
        for op in ops:
            if isinstance(op, Jump):
                referenced.add(op.name)
            elif isinstance(op, JumpIf):
                referenced.add(op.label)
            elif isinstance(op, IfTask):
                referenced.add(op.target)
            elif isinstance(op, SwitchJump):
                for _, lbl in op.cases:
                    referenced.add(lbl)
        ops = [op for op in ops if not (isinstance(op, Label) and op.name not in referenced)]

        return dataclasses.replace(self, ops=tuple(ops))

    def strip_unused_operations(self) -> Function:
        labels: dict[str, int] = {op.name: index for index, op in enumerate(self.ops) if isinstance(op, Label)}
        seen_indexes: set[int] = set()
        to_see_indexes: set[int] = {0}
        while to_see_indexes:
            seen_indexes.update(to_see_indexes)
            to_see = to_see_indexes
            to_see_indexes = set()
            for index in to_see:
                op = self.ops[index]
                if isinstance(op, Jump):
                    to_see_indexes.add(labels[op.name])
                elif isinstance(op, JumpIf):
                    to_see_indexes.add(labels[op.label])
                    if index+1 < len(self.ops):
                        to_see_indexes.add(index+1)
                elif isinstance(op, IfTask):
                    to_see_indexes.add(labels[op.target])
                    if index+1 < len(self.ops):
                        to_see_indexes.add(index+1)
                elif isinstance(op, SwitchJump):
                    for _, lbl in op.cases:
                        to_see_indexes.add(labels[lbl])
                    if index+1 < len(self.ops):
                        to_see_indexes.add(index+1)
                elif isinstance(op, (Return, ReturnVoid)):
                    pass
                else:
                    if index+1 < len(self.ops):
                        to_see_indexes.add(index+1)
        ops = tuple(op for index, op in enumerate(self.ops) if index in seen_indexes)
        return dataclasses.replace(self, ops=ops)

    def fold_struct_fields(self) -> Function:
        """Fold StructField(NewStruct/NewStructTyped, name) → the value directly,
        bottom-up across all ops.  Eliminates redundant struct construct/access pairs."""
        return self.replace_params(_fold_struct_field)

    def copy_propagate(self) -> Function:
        """Eliminate variable-to-variable copy assignments.

        Two cases:
        1. Simple aliases (single write, no null-init): a = b  →  replace all
           reads of a with b and drop the op.
        2. Phi-chain copies (ZeroOf null-init + one real write): a = b  →  same,
           provided b is GC-safe at the function entry (also null-inited or a
           parameter) and not reassigned after the copy.

        In both cases b must be written at most once (real writes only) so that
        substituting a → b can never observe a later version of b.
        """
        param_names: set[str] = {name for name, _ in self.params.fields}

        # Separate ZeroOf inits from real writes.
        real_writes: dict[str, int] = {}
        zero_init_vars: set[str] = set()
        for op in self.ops:
            if isinstance(op, Move) and isinstance(op.target, p.StackVar):
                name = op.target.name
                if isinstance(op.source, p.ZeroOf):
                    zero_init_vars.add(name)
                else:
                    real_writes[name] = real_writes.get(name, 0) + 1
            elif isinstance(op, (Call, NewObject)):
                reg = op.register
                if isinstance(reg, p.StackVar):
                    real_writes[reg.name] = real_writes.get(reg.name, 0) + 1

        # GC-safe vars: always hold a valid (possibly null) pointer at function entry.
        gc_safe: set[str] = param_names | zero_init_vars

        # Build alias map: eliminated_var → source StackVar (unresolved).
        aliases: dict[str, p.StackVar] = {}
        for op in self.ops:
            if not (isinstance(op, Move)
                    and isinstance(op.target, p.StackVar)
                    and isinstance(op.source, p.StackVar)):
                continue
            a, b = op.target.name, op.source.name
            if real_writes.get(a, 0) != 1:
                continue
            if real_writes.get(b, 0) > 1:
                # b may be overwritten after a = b; unsafe to alias.
                continue
            if a in zero_init_vars:
                # Null-init case: only safe when b is also GC-safe from the start.
                if b not in gc_safe and b not in param_names:
                    continue
            aliases[a] = op.source

        if not aliases:
            return self

        # Resolve chains (a → b → c becomes a → c).
        def resolve(sv: p.StackVar) -> p.StackVar:
            seen: set[str] = set()
            while sv.name in aliases and sv.name not in seen:
                seen.add(sv.name)
                sv = aliases[sv.name]
            return sv

        resolved: dict[str, p.StackVar] = {a: resolve(sv) for a, sv in aliases.items()}
        eliminated: set[str] = set(resolved)
        renames: dict[str, str] = {a: sv.name for a, sv in resolved.items()}

        new_ops: list[Op] = []
        for op in self.ops:
            # Check original target BEFORE renaming: if we're writing to an
            # eliminated var (null-init or the real copy), drop the op entirely.
            if (isinstance(op, Move)
                    and isinstance(op.target, p.StackVar)
                    and op.target.name in eliminated):
                continue
            new_ops.append(op.rename_vars(renames))

        new_stack_vars = t.Struct(
            tuple((name, typ) for name, typ in self.stack_vars.fields
                  if name not in eliminated)
        )
        return dataclasses.replace(self, ops=tuple(new_ops), stack_vars=new_stack_vars)

    def eliminate_common_subexpressions(self) -> Function:
        # Pre-pass: find StackVars written more than once.  These are not SSA-stable:
        # aliasing another var to a multi-write var would break correctness when the
        # var is overwritten.  Expressions that depend on multi-write vars are also
        # excluded from caching.
        write_counts: dict[str, int] = {}
        for op in self.ops:
            if isinstance(op, Move) and isinstance(op.target, p.StackVar):
                n = op.target.name
                write_counts[n] = write_counts.get(n, 0) + 1
            elif isinstance(op, (Call, NewObject)):
                reg = op.register
                if isinstance(reg, p.StackVar):
                    write_counts[reg.name] = write_counts.get(reg.name, 0) + 1
        multi_write: set[str] = {n for n, c in write_counts.items() if c > 1}

        def is_eligible(rparam: p.RParam) -> bool:
            if isinstance(rparam, (p.StackVar, p.GlobalVar, p.GlobalFunction)):
                return False
            return not rparam.test(
                lambda x: isinstance(x, p.StackVar) and x.name in multi_write)

        # available: pure RParam expression -> StackVar that already holds its value
        available: dict[p.RParam, p.StackVar] = {}
        # renames: eliminated var name -> canonical var name (applied to all later ops)
        renames: dict[str, str] = {}
        eliminated: set[str] = set()
        new_ops: list[Op] = []

        for op in self.ops:
            if renames:
                op = op.rename_vars(renames)

            if isinstance(op, Label):
                # Basic-block boundary: expressions valid above may not hold on all
                # paths leading here.  Renames remain valid (each eliminated var is
                # single-write, so the alias holds for the rest of the function).
                available.clear()
                new_ops.append(op)

            elif isinstance(op, Move) and isinstance(op.target, p.StackVar):
                source = op.source
                target_name = op.target.name
                if (is_eligible(source) and source in available
                        and target_name not in multi_write):
                    # Duplicate computation — alias this single-write var to the
                    # existing single-write var that holds the same value.
                    renames[target_name] = available[source].name
                    eliminated.add(target_name)
                    # Don't emit: the target var is gone.
                else:
                    if is_eligible(source) and target_name not in multi_write:
                        available[source] = op.target
                    new_ops.append(op)

            elif isinstance(op, (Call, NewObject)) or (
                    isinstance(op, Move) and isinstance(op.target, p.ObjectField)):
                # A call, heap allocation, or heap field write may mutate object
                # state. Invalidate all cached StructField reads — they may now
                # be stale. Other pure computations that don't involve StructField
                # reads remain valid.
                available = {k: v for k, v in available.items()
                             if not k.test(lambda x: isinstance(x, p.StructField))}
                new_ops.append(op)

            else:
                new_ops.append(op)

        if not eliminated:
            return self

        new_stack_vars = t.Struct(
            tuple((name, typ) for name, typ in self.stack_vars.fields
                  if name not in eliminated)
        )
        return dataclasses.replace(self, ops=tuple(new_ops), stack_vars=new_stack_vars)


@dataclass(frozen=True)
class Object:
    name: str
    extends: tuple[str, ...]                # Full list of everything from which this inherits, all the way up to root
    functions: tuple[tuple[str, str], ...]  # Virtual name to global name lookup including inherited members
    fields: t.ImmediateStruct               # All fields of this and parent objects in the correct order
    length_field: str|None = None           # Name of field that is the Int(32) length
    comment: str = ""
    is_foreign: bool = False

    def __post_init__(self):
        if not isinstance(self.fields, t.ImmediateStruct):
            raise ValueError("Fields parameter must be ImmediateStruct")
        if len(self.fields.fields) == 0:
            raise ValueError("Object cannot have empty fields array")
        else:
            name, field_type = self.fields.fields[0]
            if isinstance(field_type, t.Foreign):
                # Foreign nested object whose first byte is the vtable (e.g.
                # `task_t parent`). The C layout still places the vtable at
                # offset 0, but the field name doesn't have to be "type".
                pass
            elif name != "type":
                raise ValueError("The first field of an object must be named 'type'")
            elif not isinstance(field_type, t.DataPointer):
                raise ValueError("The first field of an object must be DataPointer")
            if any(1 for name, field_type in self.fields.fields[:-1] if isinstance(field_type, t.Array)):
                raise ValueError("An object may only have one array field and it must come last")
            name, field_type = self.fields.fields[-1]
            if isinstance(field_type, t.Array):
                if field_type.length > 0:
                    raise ValueError("The final array field must have length 0")
                if name != "array":
                    raise ValueError("The final array field must be named 'array'")
        if self.length_field is not None:
            if self.array_type is None:
                raise ValueError("Length field requires that there is an array field")
            if not any(1 for name, field_type in self.fields.fields if name == self.length_field):
                raise ValueError("Length field does not exist")
        if self.array_type is not None:
            if self.length_field is None:
                raise ValueError("Array field requires that there is a length field")

    @property
    def array_type(self) -> t.Type|None:
        f = self.fields.fields
        if len(f) > 0:
            f = f[-1][1]
            if isinstance(f, t.Array):
                return f.type
        return None

    @property
    def comment_line(self):
        return f"// {self.comment}\n" if self.comment else ""

    def get_pointer_mask(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        # Trim the explicit "type" vtable field (if any) and the trailing array
        # field (if any).  When the first field is a Foreign nested object
        # (e.g. `task_t parent`), it owns its vtable internally and is responsible
        # for excluding that pointer from its own pointer_paths — so we keep it
        # in the iteration.
        fields = self.fields.fields
        if fields and fields[0][0] == "type":
            fields = fields[1:]
        if self.array_type:
            fields = fields[:-1]
        return to_pointer_mask(t.Struct(fields), f"{mangle_name(self.name)}_t")

    def get_array_pointer_mask(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        array_type = self.array_type
        if not array_type: return "0"
        return to_pointer_mask(array_type, array_type.declare(type_cache))

    def get_object_size(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        type_str = f"{mangle_name(self.name)}_t"
        return f"offsetof({type_str}, {self.fields.fields[-1][0]})" if self.array_type else f"sizeof({type_str})"

    def get_array_el_size(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        a = self.array_type
        return f"sizeof({a.declare(type_cache)})" if a else "0"

    def get_array_length_offset(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        l = self.length_field
        if l is not None:
            return f"offsetof({mangle_name(self.name)}_t, {l})"
        return "0"


@dataclass(frozen=True)
class Global:
    name: str
    type: t.Type
    init: p.RParam|None = None    # How to initialise it. If DataPointer, this is NewStruct
    object_name: str|None = None  # Which object type
    lazy_init_function: str|None = None # If initialisation is more complex, the function that will do it
    lazy_init_flag: str|None = None

    def to_c_name(self) -> str:
        return mangle_name(self.name)

    def __prototype(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        if self.object_name and self.init:
            if not isinstance(self.init, p.NewStruct):
                raise ValueError("init must be NewStruct")
            if self.init.values and isinstance(self.init.values[-1], p.InitArray):
                return (f"static struct {{\n"
                        + "".join(f"    {value.get_type().declare(type_cache)} {name};\n" for name, value in self.init.values) +
                        f"}}[1] {self.to_c_name()}")
            # Static object globals are declared as object_t* pointing to a named struct
            return f"static object_t* {self.to_c_name()}"
        return f"static {self.type.declare(type_cache)} {self.to_c_name()}"

    def to_c_prototype(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        return f"{self.__prototype(type_cache)};\n"

    def to_c_implement(self, type_cache: dict[t.Type, tuple[str, str]]) -> str:
        if not self.init:
            return ""
        if self.object_name:
            if not isinstance(self.init, p.NewStruct):
                raise ValueError("init must be NewStruct")
            if self.init.values and isinstance(self.init.values[-1], p.InitArray):
                return (f"{self.__prototype(type_cache)} = {{\n"
                 f"    (const vtable_t const *)&obj_{mangle_name(self.object_name)}\n"
                 + "".join(f"  , {value.to_c(type_cache)}\n" for name, value in self.init.values) +
                 f"}};\n")
            # Generate a named struct for the data, then a pointer to it
            data_name = f"{self.to_c_name()}_data"
            struct_body = ("    (const vtable_t const *)&obj_{}\n".format(mangle_name(self.object_name))
                           + "".join(f"  , {value.to_c(type_cache)}\n" for _, value in self.init.values))
            return (f"static {mangle_name(self.object_name)}_t {data_name} = {{\n"
                    f"{struct_body}"
                    f"}};\n"
                    f"static object_t* {self.to_c_name()} = (object_t*)&{data_name};\n")
        else:
            return f"{self.__prototype(type_cache)} = {self.init.to_c(type_cache)};"

