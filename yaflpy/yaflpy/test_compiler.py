from unittest import TestCase

from compiler import *


class Test(TestCase):
    def test_compile(self):
        content = ("namespace System\n"
                   "\n"
                   "typealias Int16 : __builtin_type__<int16>\n"
                   "typealias Int32 : __builtin_type__<int32>\n"
                   "typealias Int64 : __builtin_type__<int64>\n"
                   "\n"
                   "fun `+`(left: System::Int32, right: System::Int32): System::Int32\n"
                   "    ret __builtin_op__<int32>(\"add\", left, right)\n"
                   "\n"
                   "fun `+`(left: System::Int64, right: System::Int64): System::Int64\n"
                   "    ret __builtin_op__<int64>(\"add\", left, right)\n"
                   "\n"
                   "fun `=`(value: System::Int32): System::Int64\n"
                   "    ret __builtin_op__<int64>(\"sign_extend\", value)\n"
                   "\n"
                   "fun `=`(value: System::Int16): System::Int64\n"
                   "    ret __builtin_op__<int64>(\"sign_extend\", value)\n"
                   "\n"
                   "namespace System\n"
                   "\n"
                   "fun main(): System::Int32\n"
                   "    ret 1i32 + 2i32 # Resolve correct plus method\n")

        result = compile([Input(content, "file.yafl")], just_testing=False)
        self.assertNotEqual("", result)
        print(result)
