
from tests.testutil import TimedTestCase as TestCase
from pathlib import Path

from parsing.tokenizer import tokenize

import parsing.parser as p
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

    def test_float_decimal(self):
        result = p.parse_expression(tokenize("1.5", "file"))
        self.assertIsInstance(result.value, e.FloatExpression)
        self.assertEqual(1.5, result.value.value)
        self.assertEqual(64, result.value.precision)

    def test_float_scientific(self):
        result = p.parse_expression(tokenize("1e10", "file"))
        self.assertIsInstance(result.value, e.FloatExpression)
        self.assertEqual(1e10, result.value.value)

    def test_float_scientific_signed_exponent(self):
        result = p.parse_expression(tokenize("3.14e-2", "file"))
        self.assertIsInstance(result.value, e.FloatExpression)
        self.assertAlmostEqual(0.0314, result.value.value)

    def test_float_f32_suffix(self):
        result = p.parse_expression(tokenize("1.5f32", "file"))
        self.assertIsInstance(result.value, e.FloatExpression)
        self.assertEqual(1.5, result.value.value)
        self.assertEqual(32, result.value.precision)

    def test_float_f64_suffix_no_decimal(self):
        result = p.parse_expression(tokenize("1f64", "file"))
        self.assertIsInstance(result.value, e.FloatExpression)
        self.assertEqual(1.0, result.value.value)
        self.assertEqual(64, result.value.precision)

    def test_hex_literal_with_e_digit_is_integer(self):
        # 0xCAFE contains 'E' but must parse as a hex integer, not a float.
        result = p.parse_expression(tokenize("0xCAFE", "file"))
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(0xCAFE, result.value.value)

    def test_string(self):
        tokens = tokenize("\"fred\"", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.StringExpression)

    def test_negative_integer_literal_folds(self):
        """`-2` parses as a negative IntegerExpression, not a call to `-`."""
        result = p.parse_expression(tokenize("-2", "file"))
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(-2, result.value.value)

    def test_negative_sized_integer_literal_folds(self):
        """`-1i32` keeps its precision and folds the sign into the literal."""
        result = p.parse_expression(tokenize("-1i32", "file"))
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(-1, result.value.value)
        self.assertEqual(32, result.value.precision)

    def test_negate_non_literal_stays_a_call(self):
        """`-x` where `x` is a name still lowers to a call to `-`."""
        result = p.parse_expression(tokenize("-x", "file"))
        self.assertIsInstance(result.value, e.CallExpression)
        self.assertIsInstance(result.value.function, e.NamedExpression)
        self.assertEqual("`-`", result.value.function.name)

    def test_negative_float_literal_folds(self):
        """`-3.14` parses as a negative FloatExpression, not a call to `-`."""
        result = p.parse_expression(tokenize("-3.14", "file"))
        self.assertIsInstance(result.value, e.FloatExpression)
        self.assertEqual(-3.14, result.value.value)

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
        body = result.value.body
        self.assertIsInstance(body, e.BlockExpression)
        self.assertEqual(1, len(body.statements))
        self.assertIsInstance(body.statements[0], s.ActionStatement)
        self.assertIsInstance(body.value, e.IntegerExpression)

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

        r = p.parse(tokens)
        result = [x for x in r.value if isinstance(x, s.ClassStatement)]
        self.assertEqual(1, len(result))
        self.assertEqual(0, len(r.errors))
        statement = result[0]

        params = statement.parameters.targets
        self.assertEqual(1, len(params))
        self.assertIn("value@", params[0].name)
        self.assertIsInstance(params[0].declared_type, t.NamedSpec)

    def test_class_with_generics(self):
        tokens = tokenize(
            "interface Number<TValue> : Add<TValue>|Equal<TValue> where SomethingElse<TValue>|yetAnother<TValue>\n"
            "    def `+`(a:TValue,b:TValue):TValue\n"
            "    def `=`(a:TValue,b:TValue):Bool\n"
            , "file"
        )

        result = p.parse(tokens)
        result = [x for x in result.value if isinstance(x, s.ClassStatement)]
        self.assertEqual(1, len(result))
        statement = result[0]

    def test_trait(self):
        tokens = tokenize(
            "let [trait] t:Number<Int> = IntNumber()\n"
            , "file"
        )

        result = p.parse(tokens)
        result = [x for x in result.value if isinstance(x, s.LetStatement)]
        self.assertEqual(1, len(result))
        statement = result[0]

        attributes = statement.attributes
        self.assertIn("trait", attributes)

        type = statement.declared_type
        self.assertIsInstance(type, t.NamedSpec)

        type_params = type.type_params
        self.assertEqual(1, len(type_params))
        self.assertIsInstance(type_params[0], t.NamedSpec)
        self.assertEqual("Int", type_params[0].name)

    def test_function_with_generics(self):
        tokens = tokenize(
            "fun doNothing<TValue>(value: TValue): TValue where Number<TValue>\n"
            "    ret value\n"
            , "file")

        result = p.parse(tokens)
        result = [x for x in result.value if isinstance(x, s.FunctionStatement)]
        self.assertEqual(1, len(result))
        statement = result[0]

        type_params = statement.type_params
        self.assertEqual(1, len(type_params))
        self.assertIn("TValue@", type_params[0].name)

        trait_params = statement.trait_params
        self.assertEqual(1, len(trait_params))
        self.assertEqual("Number", trait_params[0].name)


    def test_access_with_generics(self):
        tokens = tokenize(
            "fun main(): Int\n"
            "    ret doNothing<Int>(1)\n",
            "file")

        result = p.parse(tokens)
        result = [x for x in result.value if isinstance(x, s.FunctionStatement)]
        self.assertEqual(1, len(result))
        statement = result[0]

        self.assertIsInstance(statement.body, e.BlockExpression)
        call_expr = statement.body.value
        self.assertIsInstance(call_expr, e.CallExpression)
        self.assertIsInstance(call_expr.function, e.NamedExpression)
        load = call_expr.function

        self.assertEqual(1, len(load.type_params))
        type_param = load.type_params[0]
        self.assertIsInstance(type_param, t.NamedSpec)
        self.assertEqual("Int", type_param.name)

    def test_integer_binary_literal_long(self):
        # 0b11110000 has 8 content characters; the buggy slice [2:8] gives "111100" (60)
        # instead of "11110000" (240).
        tokens = tokenize("0b11110000", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(0b11110000, result.value.value)

    def test_integer_hex_literal_long(self):
        # 0xDEADBEEF has 8 hex digits; the buggy slice trims 2 extra from the right.
        tokens = tokenize("0xDEADBEEF", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(0xDEADBEEF, result.value.value)

    def test_integer_octal_literal_long(self):
        # 0o12345670 has 8 octal digits
        tokens = tokenize("0o12345670", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(0o12345670, result.value.value)

    def test_integer_binary_with_size_suffix(self):
        # 0b11110000i32 — prefix and suffix both present
        tokens = tokenize("0b11110000i32", "file")
        result = p.parse_expression(tokens)
        self.assertIsInstance(result.value, e.IntegerExpression)
        self.assertEqual(0b11110000, result.value.value)
        self.assertEqual(32, result.value.precision)

    def test_no_dead_test_function(self):
        import parsing.parser as parser_module
        self.assertFalse(hasattr(parser_module, 'test'),
                         "parsing.parser still exposes a module-level 'test' function (dead code)")

    def test_less_than_ambiguity(self):
        # `x < 0` is ambiguous: the parser greedily tries to interpret `<` after an
        # identifier as the start of a generic type parameter list (e.g. `foo<T>`).
        # It tries to parse `0` as a type argument, fails to find the closing `>`,
        # then backtracks and correctly parses `<` as the comparison operator.
        # However, it leaves behind a spurious "missing generics" error, which causes
        # compilation to fail even though the expression itself is parsed correctly.
        # This replicates the real failure in stdlib/string.yafl line 15.
        tokens = tokenize("x < 0", "file")
        result = p.parse_expression(tokens)

        # The parser does recover and produce the right AST
        self.assertIsNotNone(result.value)
        self.assertIsInstance(result.value, e.CallExpression)

        # And it should emit no errors — the failed generic attempt must not leak errors
        self.assertEqual(0, len(result.errors))
