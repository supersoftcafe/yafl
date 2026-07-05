"""AST statement nodes, one (group of) statement kind(s) per submodule —
the same convention as pyast/expression/. `import pyast.statement as s`
exposes the same flat surface as the former single module.

Submodule import order below is the dependency order (base ← lets ← function
← types/classdef/control); the two base→classdef runtime references are
deferred local imports inside their methods.
"""
from __future__ import annotations

from pyast.statement.base import (
    ImportGroup, Statement, NamedStatement, TypeStatement, DataStatement,
    ImportStatement, NamespaceStatement)
from pyast.statement.lets import LetStatement, DestructureStatement
from pyast.statement.function import FunctionStatement
from pyast.statement.types import TypeAliasStatement, EnumStatement
from pyast.statement.classdef import ClassFunctionSlot, ClassStatement
from pyast.statement.control import (
    ReturnStatement, ActionStatement, IfStatement, ElseIfStatement,
    ElseStatement, collapse_else_if)
