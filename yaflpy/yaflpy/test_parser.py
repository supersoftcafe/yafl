
from unittest import TestCase
from pathlib import Path

from parser import parse, parse_expression, parse_statement, parse_type, parse_target_type_expr
from tokenizer import tokenize, TokenKind

import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t


class Test(TestCase):
    def test_parse_simple_named_type(self):
        result = parse_type(tokenize("something", "file"))
        self.assertIsInstance(result.value, t.NamedSpec)
        self.assertEqual("something", result.value.name)

    def test_parse_qualified_named_type(self):
        result = parse_type(tokenize("somewhere ::   something", "file"))
        self.assertIsInstance(result.value, t.NamedSpec)
        self.assertEqual("somewhere::something", result.value.name)

    def test_parse_type_empty_tuple(self):
        result = parse_type(tokenize("()", "file"))
        self.assertIsInstance(result.value, t.TupleSpec)
        self.assertEqual(0, len(result.value.entries))

    def test_parse_expression_empty_tuple(self):
        result = parse_expression(tokenize("()", "file"))
        self.assertIsInstance(result.value, e.TupleExpression)
        self.assertEqual(0, len(result.value.expressions))

    def test_parse_statement_return(self):
        result = parse_statement(tokenize("ret 0", "file"))
        self.assertIsInstance(result.value, s.ReturnStatement)
        self.assertIsInstance(result.value.value, e.IntegerExpression)

    def test_parse_builtin_type(self):
        tokens = tokenize("__builtin_type__<int32>", "file")
        result = parse_type(tokens)
        self.assertIsInstance(result.value, t.BuiltinSpec)
        self.assertEqual(result.value.type_name, "int32")

    def test_destructure1(self):
        tokens = tokenize("a", "file")
        result = parse_target_type_expr(tokens)
        self.assertIsInstance(result.value, s.LetStatement)
        self.assertIsNone(result.value.default_value)
        self.assertIsNone(result.value.declared_type)

    def test_destructure2(self):
        tokens = tokenize("(a, b, c)", "file")
        result = parse_target_type_expr(tokens)
        self.assertIsInstance(result.value, s.DestructureStatement)
        self.assertIsNone(result.value.default_value)
        self.assertIsNone(result.value.declared_type)

    def test_destructure3(self):
        tokens = tokenize("(a, b, c) = somefunc()", "file")
        result = parse_target_type_expr(tokens)
        self.assertIsInstance(result.value, s.DestructureStatement)
        self.assertIsInstance(result.value.default_value, e.CallExpression)
        self.assertIsNone(result.value.declared_type)

    def test_int32(self):
        tokens = tokenize("1i32", "file")
        result = parse_expression(tokens)
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(1, result.value.value)
        self.assertEqual(32, result.value.size)

    def test_string(self):
        tokens = tokenize("\"fred\"", "file")
        result = parse_expression(tokens)
        self.assertIsInstance(result.value, e.StringExpression)

    def test_binop(self):
        tokens = tokenize("__builtin_op__<int32>(\"add\", 1i32, 2i32)", "file")
        result = parse_expression(tokens)
        self.assertIsInstance(result.value, e.BuiltinOpExpression)

    def test_module_statement(self):
        tokens = tokenize("namespace Fred\n", "file")
        result = parse_statement(tokens)
        self.assertIsInstance(result.value, s.NamespaceStatement)
        self.assertEqual("Fred", result.value.path)

    def test_type_statement(self):
        tokens = tokenize("typealias Int32 : __builtin_type__<int32>\n", "file")
        result = parse_statement(tokens)
        self.assertIsInstance(result.value, s.TypeAliasStatement)
        self.assertIsInstance(result.value.type, t.BuiltinSpec)

    def test_fully_qualified_name_expression(self):
        tokens = tokenize("System::Int32::add", "file")
        result = parse_expression(tokens)
        self.assertIsInstance(result.value, e.NamedExpression)
        self.assertEqual("System::Int32::add", result.value.name)
