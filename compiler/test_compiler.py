from unittest import TestCase

from compiler import *


class Test(TestCase):
    def test_add(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int16 : __builtin_type__<int16>\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "\n"
                   "fun `+`(left: System::Int16, right: System::Int16): System::Int16\n"
                   "    ret __builtin_op__<int16>(\"add\", left, right)\n"
                   "\n"
                   "fun `+`(left: System::Int32, right: System::Int32): System::Int32\n"
                   "    ret __builtin_op__<int32>(\"add\", left, right)\n"
                   "\n"
                   "namespace System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret 1 + 2 # Resolve correct plus method\n")

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_declare_let(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "\n"
                   "fun main(): System::Int32\n"
                   "    let x: System::Int32 = 2\n"
                   "    ret x\n")

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_declare_class(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "\n"
                   "class Pair(left: System::Int32, right: System::Int32)\n"
                   "\n"
                   "fun main(): System::Int32\n"
                   "    let x: System::Pair = System::Pair(1, 2)\n"
                   "    ret x.right\n")

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_string_literal(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias String : __builtin_type__<str>\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "\n"
                   "fun `+`(left: System::String, right: System::String): System::String\n"
                   "    ret __builtin_op__<str>(\"append\", left, right)\n"
                   "\n"
                   "fun print(str: System::String): System::Int32\n"
                   "    ret __builtin_op__<int32>(\"print\", str)\n"
                   "\n"
                   "fun main(): System::Int32\n"
                   "    System::print(\"fred and bill\" + \", bert\")\n"
                   "    ret 0\n")

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_lambda(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias String : __builtin_type__<str>\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "\n"
                   "fun `+`(left: System::Int32, right: System::Int32): System::Int32\n"
                   "    ret __builtin_op__<int32>(\"add\", left, right)\n"
                   "\n"
                   "fun `+`(left: System::String, right: System::String): System::String\n"
                   "    ret __builtin_op__<str>(\"append\", left, right)\n"
                   "\n"
                   "fun do10(f: (:System::Int32):System::Int32):System::Int32\n"
                   "    ret f(10)\n"
                   "\n"
                   "fun main(): System::Int32\n"
                   "    let v: System::Int32 = 20\n"
                   "    ret do10((x: System::Int32) => x + v)\n")

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_class_with_function(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias String : __builtin_type__<str>\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "\n"
                   "class Class(value: System::Int32)\n"
                   "    fun doit(): System::Int32\n"
                   "        ret value\n"
                   "\n"
                   "fun main(): System::Int32\n"
                   "    let v: System::Class = Class(27)\n"
                   "    ret v.doit()\n"
                   )

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)


    def test_inherit(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "\n"
                   "fun `+`(left: System::Int32, right: System::Int32): System::Int32\n"
                   "    ret __builtin_op__<int32>(\"add\", left, right)\n"
                   "\n"
                   "interface Parent1\n"
                   "    fun doit(): System::Int32\n"
                   "        ret 10\n"
                   "    fun doit(other: System::Int32): System::Int32\n"
                   "        ret other\n"
                   "\n"
                   "interface Parent2\n"
                   "    fun doit(): System::Int32\n"
                   "        ret 20\n"
                   "\n"
                   "class Child(value: System::Int32): Parent1|Parent2\n"
                   "    fun doit(other: System::Int32): System::Int32\n"
                   "        ret other + value\n"
                   "\n"
                   "fun main(): System::Int32\n"
                   "    let v: System::Parent1 = Child(27)\n"
                   "    ret v.doit()\n"
                   )

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_ternery(self):
        content = ("namespace System\n"
                   "typealias Bool : __builtin_type__<bool>\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "fun `>`(left: System::Int32, right: System::Int32): System::Bool\n"
                   "    ret __builtin_op__<bool>(\"int32_gt\", left, right)\n"
                   "fun main(): System::Int32\n"
                   "    ret 0 > 0 ? 1 : 2\n")

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)

    def test_stdlib(self):
        content = ("import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret System::print(System::Char(48) + System::Char(49))\n")

        result = compile([Input(content, "file.yafl")], use_stdlib=True, just_testing=False)
        self.assertNotEqual("", result)
        print(result)
