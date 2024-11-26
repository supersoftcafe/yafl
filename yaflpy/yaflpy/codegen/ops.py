from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any, Tuple, Union
from codegen.param import RParam, LParam
import codegen.typedecl as t


@dataclass(frozen=True)
class Op:
    def rename_vars(self, renames: dict[str, str]) -> Op:
        return self

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        pass


@dataclass(frozen=True)
class Move(Op):
    target: LParam
    source: RParam

    def rename_vars(self, renames: dict[str, str]) -> Move:
        return dataclasses.replace(self, target=self.target.rename_vars(renames), source=self.source.rename_vars(renames))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"    {self.target.to_c(type_cache)} = {self.source.to_c(type_cache)};\n"


@dataclass(frozen=True)
class Label(Op):
    name: str

    def rename_vars(self, renames: dict[str, str]) -> Label:
        return dataclasses.replace(self, name=renames.get(self.name, self.name))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"{self.name}:\n"


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

    def rename_vars(self, renames: dict[str, str]) -> JumpIf:
        return dataclasses.replace(self, condition=self.condition.rename_vars(renames), label=renames.get(self.label, self.label))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"    if ({self.condition.to_c(type_cache)}) goto {self.label};\n"


@dataclass(frozen=True)
class Call(Op):
    function: RParam
    parameters: tuple[RParam, ...]
    register: str|None

    def rename_vars(self, renames: dict[str, str]) -> Call:
        return dataclasses.replace(
            self,
            function=self.function.rename_vars(renames),
            parameters=tuple(p.rename_vars(renames) for p in self.parameters),
            register=self.register and renames.get(self.register, self.register))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        output = f"{self.register} = " if self.register is not None else ""
        return_type = f"typeof({self.register})" if self.register is not None else "void"
        params = "".join(f", {prm.to_c(type_cache)}" for prm in self.parameters)
        param_types = "".join(f", typeof({prm.to_c(type_cache)})" for prm in self.parameters)
        return (f"    {{\n"
                f"        fun_t fun = {self.function.to_c(type_cache)};\n"
                f"        {output}(({return_type}(*)(void*{param_types}))fun.f)(fun.o{params});\n"
                f"    }}\n")


@dataclass(frozen=True)
class Return(Op):
    value: RParam

    def rename_vars(self, renames: dict[str, str]) -> Return:
        return dataclasses.replace(self, value=self.value.rename_vars(renames))

    def to_c(self, type_cache: Dict[t.Type, (str, str)]) -> str:
        return f"    return {self.value.to_c(type_cache)};\n"

