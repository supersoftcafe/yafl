from __future__ import annotations

import dataclasses
from abc import abstractmethod
from enum import Enum
from typing import List
from dataclasses import dataclass
from typing import Optional

from parselib import Error
import pyast.globalcontext as g
import pyast.statement as s
import pyast.expression as e

import codegen.typedecl as cg_t

from tokenizer import LineRef


@dataclass
class TypeSpec:
    line_ref: LineRef

    def validate(self, glb: g.Global) -> list[Error]:
        return []

    def compile(self, glb: g.Global) ->  (TypeSpec, list[s.Statement], list[Error]):
        return self, [], []

    def to_codegen(self) -> cg_t.Type:
        raise RuntimeError("Unsupported type")

    @abstractmethod
    def fuzzy_assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        pass

    @abstractmethod
    def assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        pass

    @abstractmethod
    def as_unique_id_str(self) -> str|None:
        pass


def fuzzy_assignable_equals(glb: g.Global, left: TypeSpec | None, right: TypeSpec | None, reversed: bool = False) -> bool:
    result = left is None or right is None or left.fuzzy_assignable_from(glb, right, reversed)
    return result


def assignable_equals(glb: g.Global, left: TypeSpec | None, right: TypeSpec | None, reversed: bool = False) -> bool:
    result = left is not None and right is not None and left.assignable_from(glb, right, reversed)
    return result


@dataclass
class CallableSpec(TypeSpec):
    parameters: TupleSpec
    result: TypeSpec|None

    def compile(self, glb: g.Global) ->  (TypeSpec, list[s.Statement], list[Error]):
        p, pglb, perr = self.parameters.compile(glb)
        r, rglb, rerr = self.result.compile(glb)
        xtype = dataclasses.replace(self, parameters=p, result=r)
        return xtype, pglb+rglb, perr+rerr

    def to_codegen(self) -> cg_t.Type:
        return cg_t.FuncPointer()

    def fuzzy_assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        # TODO: Conversion assignment compatibility applies to function pointers too
        #       This could result in extra heap allocations for a thunk to reference the original function.

        # Must be callable.
        if not isinstance(right, CallableSpec):
            return False

        # Direction swaps for parameters. Must be assignment convertable.
        if not fuzzy_assignable_equals(glb, right.parameters, self.parameters, not reversed):
            return False

        return True

    def assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        # Must be callable.
        if not isinstance(right, CallableSpec):
            return False

        # Direction swaps for parameters. Must be assignment convertable.
        if not assignable_equals(glb, right.parameters, self.parameters, not reversed):
            return False

        return True

    def as_unique_id_str(self) -> str|None:
        p = self.parameters.as_unique_id_str()
        r = self.result and self.result.as_unique_id_str()
        return p and r and f"{p}:{r}"


@dataclass
class BuiltinSpec(TypeSpec):
    type_name: str

    def __translate(self) -> cg_t.Type|None:
        match self.type_name:
            case "int8":
                return cg_t.Int(8)
            case "int16":
                return cg_t.Int(16)
            case "int32":
                return cg_t.Int(32)
            case "int64":
                return cg_t.Int(64)
            case "bigint":
                return cg_t.Int()
            case _:
                return None

    def validate(self, glb: g.Global) -> list[Error]:
        xtype = self.__translate()
        if xtype is None:
            return [Error(self.line_ref, f"Unresolved reference to '{self.type_name}'")]
        return []

    def to_codegen(self) -> cg_t.Type:
        xtype = self.__translate()
        if xtype is None:
            raise ValueError(f"Unknown type {self.type_name}")
        return xtype

    def fuzzy_assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        # TODO: Conversation compatible types..  need to look for a global converter
        return isinstance(right, BuiltinSpec) and self.type_name == right.type_name

    def assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        return isinstance(right, BuiltinSpec) and self.type_name == right.type_name

    def as_unique_id_str(self) -> str|None:
        return self.type_name


@dataclass
class NamedSpec(TypeSpec):
    name: str

    def validate(self, glb: g.Global) -> list[Error]:
        return [Error(self.line_ref, f"Unresolved reference to '{self.name}'")]

    def compile(self, glb: g.Global) ->  (TypeSpec, list[s.Statement], list[Error]):
        types = glb.find_global_type({self.name})
        if len(types) == 0:
            return self, [], [Error(self.line_ref, f"Unresolved reference to '{self.name}'")]
        if len(types) > 1:
            return self, [], [Error(self.line_ref, f"Ambiguous reference to '{self.name}'")]
        return types[0], [], []

    def to_codegen(self) -> cg_t.Type:
        raise RuntimeError("NamedSpec should be replaced with a concrete type")

    def fuzzy_assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        return False # Must be replaced with a concrete type, builtin, class etc

    def assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        return False

    def as_unique_id_str(self) -> str|None:
        return None # This is 'alias', not a concrete type.


@dataclass
class TupleEntrySpec:
    name: str|None
    type: TypeSpec|None
    default: e.Expression|None = None


@dataclass
class TupleSpec(TypeSpec):
    entries: list[TupleEntrySpec]
    tagged: bool = False

    def compile(self, glb: g.Global) ->  (TypeSpec, list[s.Statement], list[Error]):
        # All named parameters must come after all positional parameters
        max_unnamed_index = max(i for i, entry in enumerate(self.entries) if entry.name is None)
        min_named_index = min(i for i, entry in enumerate(self.entries) if entry.name is not None)
        if max_unnamed_index > min_named_index:
            return self, [], [Error(self.line_ref, "Named parameters are not allowed before positional parameters")]

        all_names = [entry.name for entry in self.entries]
        if len(all_names) != len(set(all_names)):
            return self, [], [Error(self.line_ref, "Duplicate named parameters are not allowed")]

        return self, [], []

    def to_codegen(self) -> cg_t.Type:
        if self.tagged:
            raise ValueError("TupleSpec does not support tagged containers (enums) yet")
        for ent in self.entries:
            if ent.type is None:
                raise ValueError("TupleEntrySpec must have a known type at codegen")
        return cg_t.Struct(tuple((f"_{idx}", ent.type.to_codegen()) for idx, ent in enumerate(self.entries)))

    def fuzzy_assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        if len(self.entries) == 1 and fuzzy_assignable_equals(glb, self.entries[0].type, right):
            return True # Rule: tuple of <type> is equivalent to <type>

        if not isinstance(right, TupleSpec):
            return False

        unnamed_entries = [entry for entry in right.entries if entry.name is None]
        if len(unnamed_entries) > len(self.entries):
            return False

        if not all(fuzzy_assignable_equals(glb, l.type, r.type, reversed) for l, r in zip(self.entries[:len(unnamed_entries)], unnamed_entries)):
            return False

        # TODO: Named parameter matching
        # TODO: Named parameters that match positionally matched args are errors
        # TODO: Default values aren't required

        # For now we'll just say mis-match if there are named parameters
        return len(self.entries[len(unnamed_entries):0]) == 0 and len(unnamed_entries) == len(right.entries)

    def assignable_from(self, glb: g.Global, right: TypeSpec, reversed: bool = False) -> bool:
        if len(self.entries) == 1 and assignable_equals(glb, self.entries[0].type, right):
            return True # Rule: tuple of <type> is equivalent to <type>

        if not isinstance(right, TupleSpec):
            return False

        unnamed_entries = [entry for entry in right.entries if entry.name is None]
        if len(unnamed_entries) > len(self.entries):
            return False

        if not all(assignable_equals(glb, l.type, r.type, reversed) for l, r in zip(self.entries[:len(unnamed_entries)], unnamed_entries)):
            return False

        # TODO: Named parameter matching
        # TODO: Named parameters that match positionally matched args are errors
        # TODO: Default values aren't required

        # For now we'll just say mis-match if there are named parameters
        return len(self.entries[len(unnamed_entries):0]) == 0 and len(unnamed_entries) == len(right.entries)

    def as_unique_id_str(self) -> str|None:
        ids = [x.type and x.type.as_unique_id_str() for x in self.entries]
        if not all(ids):
            return None
        elif self.tagged:
            return f"[{'|'.join(sorted(set(ids)))}]"
        else:
            return f"({','.join(ids)})"


