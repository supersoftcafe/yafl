from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any, Tuple, Union
from codegen.param import RParam, LParam, StackVar, NewStruct, GlobalFunction
import codegen.typedecl as t
from codegen.tools import mangle_name


@dataclass(frozen=True)
class Op:
    saved_vars: frozenset[StackVar] = field(default=frozenset(), kw_only=True) # Which locals need to persist across this call

    def test_params(self, predicate: Callable[[RParam], bool]) -> bool:
        return False

    def rename_vars(self, renames: dict[str, str]) -> Op:
        return self

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> Op:
        return self

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        raise NotImplementedError()

    def get_live_vars(self) -> tuple[frozenset[StackVar], frozenset[StackVar]]:
        return frozenset(), frozenset()


@dataclass(frozen=True)
class Label(Op):
    name: str

    def rename_vars(self, renames: dict[str, str]) -> Label:
        return dataclasses.replace(self, name=renames.get(self.name, self.name))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"{self.name}:\n"


@dataclass(frozen=True)
class Move(Op):
    target: LParam
    source: RParam

    def test_params(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self.target) or predicate(self.source)

    def rename_vars(self, renames: dict[str, str]) -> Move:
        return dataclasses.replace(self, target=self.target.rename_vars(renames), source=self.source.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> Move:
        return dataclasses.replace(self, target=self.target.replace_params(replacer), source=self.source.replace_params(replacer))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return self.target.to_c_store(type_cache, self.source.to_c(type_cache))

    def get_live_vars(self) -> tuple[frozenset[StackVar], frozenset[StackVar]]:
        live = self.source.get_live_vars()
        return (live, frozenset({self.target})) if isinstance(self.target, StackVar) else (live | self.target.get_live_vars(), frozenset())


@dataclass(frozen=True)
class Jump(Op):
    name: str

    def rename_vars(self, renames: dict[str, str]) -> Jump:
        return dataclasses.replace(self, name=renames.get(self.name, self.name))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"    goto {self.name};\n"


@dataclass(frozen=True)
class JumpIf(Op):
    label: str
    condition: RParam

    def test_params(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self.condition)

    def rename_vars(self, renames: dict[str, str]) -> JumpIf:
        return dataclasses.replace(self, condition=self.condition.rename_vars(renames), label=renames.get(self.label, self.label))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> JumpIf:
        return dataclasses.replace(self, condition=self.condition.replace_params(replacer))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"    if ({self.condition.to_c(type_cache)}) goto {self.label};\n"

    def get_live_vars(self) -> tuple[frozenset[StackVar], frozenset[StackVar]]:
        return self.condition.get_live_vars(), frozenset()


@dataclass(frozen=True)
class NewObject(Op): # Create a new blank instance of the named object
    name: str
    register: LParam
    size: RParam|None = None

    def get_type(self) -> t.DataPointer:
        return t.DataPointer()

    def rename_vars(self, renames: dict[str, str]) -> NewObject:
        return dataclasses.replace(self,
                register=self.register.rename_vars(renames),
                size=self.size and self.size.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> NewObject:
        return dataclasses.replace(self,
                register=self.register.replace_params(replacer),
                size=self.size and self.size.replace_params(replacer))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        if self.size is not None:
            return f"    {self.register.to_c(type_cache)} = array_create(obj_{mangle_name(self.name)}, {self.size});\n"
        else:
            return f"    {self.register.to_c(type_cache)} = object_create(obj_{mangle_name(self.name)});\n"

    def get_live_vars(self) -> tuple[frozenset[StackVar], frozenset[StackVar]]:
        live = self.size.get_live_vars() if self.size else frozenset()
        return (live, frozenset({self.register})) if isinstance(self.register, StackVar) else (live | self.register.get_live_vars(), frozenset())


@dataclass(frozen=True)
class Call(Op):
    function: RParam # Must evaluate to a function
    parameters: RParam # Must evaluate to a struct
    register: LParam|None = None # Target of operation result, unless musttail == True
    musttail: bool = False # Current function will end here and the return value is the return of this call

    def test_params(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self.function) or predicate(self.parameters) or (self.register and predicate(self.register))

    def is_direct_call(self) -> bool:
        return isinstance(self.function, GlobalFunction)

    def rename_vars(self, renames: dict[str, str]) -> Call:
        return dataclasses.replace(self,
            function = self.function.rename_vars(renames),
            parameters = self.parameters.rename_vars(renames),
            register = self.register and self.register.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> Call:
        return dataclasses.replace(self,
            function = self.function.replace_params(replacer),
            parameters = self.parameters.replace_params(replacer),
            register = self.register and self.register.replace_params(replacer))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        rg = self.register
        output, return_type = (lambda x: rg.to_c_store(type_cache, x), rg.get_type().declare(type_cache)) if rg else (lambda x: x, "void")
        tailreturn = "return " if self.musttail else ""

        prms = self.parameters
        ptype = prms.get_type()
        if not isinstance(ptype, t.Struct):
            raise ValueError("parameters must be a struct type")

        get_parameters_code = ""
        if isinstance(prms, NewStruct):
            types = tuple(prm.get_type().declare(type_cache) for name, prm in prms.values)
            params = tuple(prm.to_c(type_cache) for name, prm in prms.values)
        else:
            if len(ptype.fields) > 0:
                get_parameters_code = f"        {ptype.declare(type_cache)} prm = {prms.to_c(type_cache)};\n"
            types = tuple(type.declare(type_cache) for _, type in ptype.fields)
            params = tuple(f"prm.{name}" for name, _ in ptype.fields)

        get_function_code = f"        fun_t fun = {self.function.to_c(type_cache)};\n"

        types  = "".join(f", {typ}" for typ in types )
        params = "".join(f", {prm}" for prm in params)

        return (f"    {{\n{get_function_code}{get_parameters_code}"
                f"        {tailreturn}{output(f"(({return_type}(*)(void*{types}))fun.f)(fun.o{params})")};\n"
                f"    }}\n")

    def get_live_vars(self) -> tuple[frozenset[StackVar], frozenset[StackVar]]:
        live = self.function.get_live_vars() | self.parameters.get_live_vars()
        dead = self.register.get_live_vars() if self.register else set()
        return (live, dead) if isinstance(self.register, StackVar) else (live | dead, frozenset())


@dataclass(frozen=True)
class Return(Op):
    value: RParam

    def __post_init__(self):
        if self.value is None:
            raise ValueError()

    def test_params(self, predicate: Callable[[RParam], bool]) -> bool:
        return predicate(self.value)

    def rename_vars(self, renames: dict[str, str]) -> Return:
        return dataclasses.replace(self, value=self.value.rename_vars(renames))

    def replace_params(self, replacer: Callable[[RParam], RParam]) -> Return:
        return dataclasses.replace(self, value=self.value.replace_params(replacer))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"    return {self.value.to_c(type_cache)};\n"

    def get_live_vars(self) -> tuple[frozenset[StackVar], frozenset[StackVar]]:
        return self.value.get_live_vars(), frozenset()

