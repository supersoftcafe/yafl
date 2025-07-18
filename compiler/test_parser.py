
from unittest import TestCase
from pathlib import Path

from tokenizer import tokenize

import parser as p
import pyast.expression as e
import pyast.statement as s
import pyast.typespec as t


class Test(TestCase):
    def test_parse_simple_named_type(self):
        result = p.parse_type(tokenize("something", "file"))
        self.assertIsInstance(result.value, t.NamedSpec)
        self.assertEqual("something", result.value.name)

    def test_parse_qualified_named_type(self):
        result = p.parse_type(tokenize("somewhere ::   something", "file"))
        self.assertIsInstance(result.value, t.NamedSpec)
        self.assertEqual("somewhere::something", result.value.name)

    def test_parse_type_empty_tuple(self):
        result = p.parse_type(tokenize("()", "file"))
        self.assertIsInstance(result.value, t.TupleSpec)
        self.assertEqual(0, len(result.value.entries))

    def test_parse_type_two_part_tuple(self):
        result = p.parse_type(tokenize("(int,int)", "file"))
        self.assertIsInstance(result.value, t.TupleSpec)
        self.assertEqual(2, len(result.value.entries))

    def test_parse_type_two_part_combination(self):
        result = p.parse_type(tokenize("int|int", "file"))
        self.assertIsInstance(result.value, t.CombinationSpec)
        self.assertEqual(2, len(result.value.types))

    def test_parse_callable(self):
        result = p.parse_type(tokenize("(int,int):int", "file"))
        self.assertIsInstance(result.value, t.CallableSpec)

    def test_parse_fun_with_callable_param(self):
        ## Parse with something simple as the tuple parameter, it works
        result = p.parse_statement(tokenize(
            "fun do10(f: (:int):__builtin_type__<int32>):__builtin_type__<int32>\n"
            "    ret f(10)\n"
            , "file"))
        self.assertIsInstance(result.value, s.FunctionStatement)
        self.assertIsInstance(result.value.parameters.targets[0].declared_type, t.CallableSpec)

        ## Parse with something more complex as the tuple parameter, it fails
        result = p.parse_statement(tokenize(
            "fun do10(f: (:__builtin_type__<int32>):__builtin_type__<int32>):__builtin_type__<int32>\n"
            "    ret f(10)\n"
            , "file"))
        self.assertIsInstance(result.value, s.FunctionStatement)
        self.assertIsInstance(result.value.parameters.targets[0].declared_type, t.CallableSpec)
        ## Look at the callable parser

    def test_parse_expression_empty_tuple(self):
        result = p.parse_expression(tokenize("()", "file"))
        self.assertIsInstance(result.value, e.TupleExpression)
        self.assertEqual(0, len(result.value.expressions))

    def test_parse_statement_return(self):
        result = p.parse_statement(tokenize("ret 0", "file"))
        self.assertIsInstance(result.value, s.ReturnStatement)
        self.assertIsInstance(result.value.value, e.IntegerExpression)

    def test_parse_builtin_type(self):
        tokens = tokenize("__builtin_type__<int32>", "file")
        result = p.parse_type(tokens)
        self.assertIsInstance(result.value, t.BuiltinSpec)
        self.assertEqual(result.value.type_name, "int32")

    def test_destructure1(self):
        tokens = tokenize("a", "file")
        result = p.parse_target_type_expr(tokens)
        self.assertIsInstance(result.value, s.LetStatement)
        self.assertIsNone(result.value.default_value)
        self.assertIsNone(result.value.declared_type)

    def test_destructure2(self):
        tokens = tokenize("(a, b, c)", "file")
        result = p.parse_target_type_expr(tokens)
        self.assertIsInstance(result.value, s.DestructureStatement)
        self.assertIsNone(result.value.default_value)
        self.assertIsNone(result.value.declared_type)

    def test_destructure3(self):
        tokens = tokenize("(a, b, c) = somefunc()", "file")
        result = p.parse_target_type_expr(tokens)
        self.assertIsInstance(result.value, s.DestructureStatement)
        self.assertIsInstance(result.value.default_value, e.CallExpression)
        self.assertIsNone(result.value.declared_type)

    def test_int32(self):
        tokens = tokenize("1i32", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(1, result.value.value)
        self.assertEqual(32, result.value.precision)

    def test_string(self):
        tokens = tokenize("\"fred\"", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.StringExpression)

    def test_binop(self):
        tokens = tokenize("__builtin_op__<int32>(\"add\", 1i32, 2i32)", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.BuiltinOpExpression)

    def test_module_statement(self):
        tokens = tokenize("namespace Fred\n", "file")
        result = p.parse_statement(tokens)
        self.assertIsInstance(result.value, s.NamespaceStatement)
        self.assertEqual("Fred", result.value.path)

    def test_type_statement(self):
        tokens = tokenize("typealias Int32 : __builtin_type__<int32>\n", "file")
        result = p.parse_statement(tokens)
        self.assertIsInstance(result.value, s.TypeAliasStatement)
        self.assertIsInstance(result.value.type, t.BuiltinSpec)

    def test_fully_qualified_name_expression(self):
        tokens = tokenize("System::Int32::add", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.NamedExpression)
        self.assertEqual("System::Int32::add", result.value.name)

    def test_function_statement(self):
        tokens = tokenize("fun test()\n  println()\n  ret 0\n", "file")
        result = p.parse_statement(tokens)
        self.assertIsInstance(result.value, s.FunctionStatement)
        statements = result.value.statements
        self.assertEqual(2, len(statements))
        st1, st2 = statements
        self.assertIsInstance(st1, s.ActionStatement)
        self.assertIsInstance(st2, s.ReturnStatement)

    def test_simple_class(self):
        tokens = tokenize("class Simple(value: System::Int32)", "file")
        result = p.parse_statement(tokens)
        self.assertIsInstance(result.value, s.ClassStatement)
        self.assertFalse(result.value.is_interface)
        params = result.value.parameters.targets
        self.assertEqual(1, len(params))
        self.assertIn("value@", params[0].name)
        self.assertIsInstance(params[0].declared_type, t.NamedSpec)

    def test_simple_interface(self):
        tokens = tokenize("interface Simple", "file")
        result = p.parse_statement(tokens)
        self.assertIsInstance(result.value, s.ClassStatement)
        self.assertTrue(result.value.is_interface)
        params = result.value.parameters.targets
        self.assertEqual(0, len(params))

    def test_class_with_function(self):
        tokens = tokenize(
            "namespace System\n"
            "\n"
            "typealias Int32 : __builtin_type__<int32>\n"
            "\n"
            "class Class(value: System::Int32)\n"
            "    fun doit(): System::Int32\n"
            "        ret value\n"
            "\n"
            "fun main(): System::Int32\n"
            "    let v: System::Class = Class(27)\n"
            "    ret v.doit()\n"
            , "file")

        result = p.parse(tokens)
        result = [x for x in result.value if isinstance(x, s.ClassStatement)]
        self.assertEqual(1, len(result))
        statement = result[0]

        params = statement.parameters.targets
        self.assertEqual(1, len(params))
        self.assertIn("value@", params[0].name)
        self.assertIsInstance(params[0].declared_type, t.NamedSpec)
