from __future__ import annotations

import dataclasses
from abc import abstractmethod
from enum import Enum
from typing import List
from dataclasses import dataclass
from typing import Optional

import langtools
from parselib import Error
import pyast.resolver as g
import pyast.statement as s
import pyast.expression as e

import codegen.typedecl as cg_t

from tokenizer import LineRef


@dataclass(frozen=True)
class TypeSpec:
    line_ref: LineRef

    def is_concrete(self) -> bool:
        return False

    def _compile(self, resolver: g.Resolver) ->  (TypeSpec, list[s.Statement]):
        raise NotImplementedError()

    def compile(self, resolver: g.Resolver) ->  (TypeSpec, list[s.Statement]):
        type, statements = self._compile(resolver)
        if not isinstance(type, TypeSpec):
            raise ValueError("Urggg..  This is here to catch mistakes in the code that the IDE hasn't caught")
        return type, statements

    def check(self, resolver: g.Resolver) -> list[Error]:
        raise NotImplementedError()

    def generate(self) -> cg_t.Type:
        raise NotImplementedError()

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        raise NotImplementedError()

    def as_unique_id_str(self) -> str|None:
        raise NotImplementedError()


def trivially_assignable_equals(resolver: g.Resolver, left: TypeSpec | None, right: TypeSpec | None) -> bool | None:
    if left is None or right is None:
        return None
    result = left.trivially_assignable_from(resolver, right)
    return result


@dataclass(frozen=True)
class CallableSpec(TypeSpec):
    parameters: TupleSpec
    result: TypeSpec|None

    def is_concrete(self) -> bool:
        return self.parameters.is_concrete() and (self.result is None or self.result.is_concrete())

    def _compile(self, resolver: g.Resolver) ->  (TypeSpec, list[s.Statement]):
        p, pglb = self.parameters.compile(resolver)
        r, rglb = self.result and self.result.compile(resolver)
        xtype = dataclasses.replace(self, parameters=p, result=r)
        return xtype, pglb+rglb

    def check(self, resolver: g.Resolver) -> list[Error]:
        return self.parameters.check(resolver) + (self.result.check(resolver) if self.result else [])

    def generate(self) -> cg_t.Type:
        return cg_t.FuncPointer()

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, NamedSpec):
            return None # Not resolved yet

        # Must be callable.
        if not isinstance(right, CallableSpec):
            return False

        # Simple check for results
        result_result = trivially_assignable_equals(resolver, self.result, right.result)
        # Direction swaps for parameters
        params_result = trivially_assignable_equals(resolver, right.parameters, self.parameters)

        if result_result == False or params_result == False:
            return False

        if result_result and params_result: # None or False
            return True

        return None

    def as_unique_id_str(self) -> str|None:
        p = self.parameters.as_unique_id_str()
        return p and f"f{p}"


@dataclass(frozen=True)
class BuiltinSpec(TypeSpec):
    type_name: str

    def is_concrete(self) -> bool:
        return True

    def __translate(self) -> cg_t.Type|None:
        match self.type_name:
            case "str":
                return cg_t.Str()
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

    def _compile(self, resolver: g.Resolver) ->  (TypeSpec, list[s.Statement]):
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        xtype = self.__translate()
        if xtype is None:
            return [Error(self.line_ref, f"Unresolved reference to '{self.type_name}'")]
        return []

    def generate(self) -> cg_t.Type:
        xtype = self.__translate()
        if xtype is None:
            raise ValueError(f"Unknown type {self.type_name}")
        return xtype

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, NamedSpec):
            return None # Not resolved yet
        return isinstance(right, BuiltinSpec) and self.type_name == right.type_name

    def as_unique_id_str(self) -> str|None:
        return self.type_name


@dataclass(frozen=True)
class ClassSpec(TypeSpec):
    name: str

    def is_concrete(self) -> bool:
        return True

    def _compile(self, resolver: g.Resolver) ->  (TypeSpec, list[s.Statement]):
        types = resolver.find_type({self.name})
        if len(types) == 1:
            return dataclasses.replace(self, name=types[0].unique_name), []
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        types = resolver.find_type({self.name})
        if not types:
            return [Error(f"Failed to resolve class {self.name}")]
        if len(types) > 1:
            return [Error(f"Found too many classes named {self.name}")]
        return []

    def generate(self) -> cg_t.Type:
        return cg_t.DataPointer()

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        def find_class(xtype: TypeSpec) -> s.ClassStatement:
            clstype = langtools.cast(ClassSpec, xtype)
            xstmt = resolver.find_type({clstype.name})[0].statement
            return langtools.cast(s.ClassStatement, xstmt)

        if not '@' in self.name:
            return None # Left is not resolved yet
        if isinstance(right, NamedSpec):
            return None # Right is not resolved yet so Unknown
        if not isinstance(right, ClassSpec):
            return False # Right is resolved to something not a class so definitely False
        if self.name == right.name:
            return True # Exact match
        lcls = find_class(self)
        rcls = find_class(right)
        if rcls._all_parents is None:
            return None # Right parents aren't resolved yet so Unknown
        result = any(x for x in rcls._all_parents if find_class(x).name == self.name)
        return result

    def as_unique_id_str(self) -> str|None:
        return self.name


@dataclass(frozen=True)
class NamedSpec(TypeSpec):
    name: str

    def is_concrete(self) -> bool:
        return False

    def _compile(self, resolver: g.Resolver) ->  (TypeSpec, list[s.Statement]):
        types = resolver.find_type({self.name})
        if len(types) == 1:
            xtype = types[0].statement
            if isinstance(xtype, s.TypeAliasStatement):
                if xtype.type.is_concrete():
                    return xtype.type, []
                return self, [] # No change because target isn't a concrete type yet
            elif isinstance(xtype, s.ClassStatement):
                return ClassSpec(self.line_ref, xtype.name), []
        return self, []

    def check(self, resolver: g.Resolver) -> list[Error]:
        types = resolver.find_type({self.name})
        if len(types) > 1:
            return [Error(self.line_ref, f"Ambiguous reference to '{self.name}'")]
        return [Error(self.line_ref, f"Unresolved reference to '{self.name}'")]

    def generate(self) -> cg_t.Type:
        raise RuntimeError("NamedSpec should be replaced with a concrete type")

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        return None # Not resolved yet

    def as_unique_id_str(self) -> str|None:
        return None # This is 'alias', not a concrete type.


@dataclass(frozen=True)
class CombinationSpec(TypeSpec):
    types: list[TypeSpec]

    def is_concrete(self) -> bool:
        return all(x.is_concrete() for x in self.types)

    def _compile(self, resolver: g.Resolver) ->  (TupleSpec, list[s.Statement]):
        new_types, new_errors = zip(*[x.compile(resolver) for x in self.types])
        return dataclasses.replace(self, types = new_types), [x for stm in new_errors for x in stm]

    def check(self, resolver: g.Resolver) -> list[Error]:
        return [y for x in self.types for y in x.check(resolver)]

    def generate(self) -> cg_t.Type:
        raise NotImplementedError("Can't generate tagged unions, yet!")

    def as_unique_id_str(self) -> str|None:
        raise NotImplementedError("Can't generate tagged unions, yet!")

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        raise NotImplementedError("Can't generate tagged unions, yet!")


@dataclass(frozen=True)
class TupleEntrySpec:
    name: str|None
    type: TypeSpec|None
    default: e.Expression|None = None

    def compile(self, resolver: g.Resolver) ->  (TupleEntrySpec, list[s.Statement]):
        new_type, new_statements1 = self.type.compile(resolver) if self.type else (None, [])
        new_default, new_statements2 = self.default.compile(resolver, new_type) if self.default else None, []
        return dataclasses.replace(self, type=new_type, default=new_default), new_statements1 + new_statements2

    def check(self, resolver: g.Resolver) -> list[Error]:
        err1 = self.type.check(resolver) if self.type else []
        err2 = self.default.check(resolver, self.type) if self.default else []
        return err1 + err2

    def generate(self) -> cg_t.Type:
        return self.type.generate()


@dataclass(frozen=True)
class TupleSpec(TypeSpec):
    entries: list[TupleEntrySpec]

    def is_concrete(self) -> bool:
        return all(x.type and x.type.is_concrete() for x in self.entries)

    def _compile(self, resolver: g.Resolver) ->  (TupleSpec, list[s.Statement]):
        new_entries, new_errors = zip(*[x.compile(resolver) for x in self.entries])
        return dataclasses.replace(self, entries = new_entries), [x for stm in new_errors for x in stm]

    def check(self, resolver: g.Resolver) -> list[Error]:
        # All named parameters must come after all positional parameters
        max_unnamed_index = max((i for i, entry in enumerate(self.entries) if entry.name is None), default=0)
        min_named_index = min((i for i, entry in enumerate(self.entries) if entry.name is not None), default=0)
        if max_unnamed_index > min_named_index:
            return [Error(self.line_ref, "Named parameters are not allowed before positional parameters")]
        return [y for x in self.entries for y in x.check(resolver)]

    def generate(self) -> cg_t.Type:
        return cg_t.Struct(tuple((f"_{idx}", ent.type.generate()) for idx, ent in enumerate(self.entries)))

    def as_unique_id_str(self) -> str|None:
        ids = [x.type and x.type.as_unique_id_str() for x in self.entries]
        if not all(ids):
            return None
        else:
            return f"({','.join(ids)})"

    def trivially_assignable_from(self, resolver: g.Resolver, right: TypeSpec) -> bool | None:
        if isinstance(right, NamedSpec):
            return None # Not resolved yet
        if not isinstance(right, TupleSpec):
            return False
        if not len(self.entries) == len(right.entries):
            return False
        results = {trivially_assignable_equals(resolver, l.type, r.type) for (l, r) in zip(self.entries, right.entries)}
        if False in results:
            return False # Definitely not assignable, even if there are some unknowns
        if None in results:
            return None # Might be assignable, but still some doubt
        return True # Is assignable
