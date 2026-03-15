from unittest import TestCase

import compiler as c


class TestNewFeatures(TestCase):
    """Tests for features not yet fully implemented or known to fail."""

    def test_bind(self):
        content = ("namespace System\n"
                   "typealias Int : __builtin_type__<bigint>\n"
                   "typealias String : __builtin_type__<str>\n"
                   "fun print(str: System::String): System::Int\n"
                   "    ret __builtin_op__<bigint>(\"print\", str)\n"
                   "\n"
                   "fun bind(in: String|None, func: (String):Int): Int|None\n"
                   "    ret match in\n"
                   "        (x:String) => func(x)\n"
                   "        (x:None) => None\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "    ret \"Hello\"\n"
                   "        ?> System::print\n")

        result = c.compile([c.Input(content, "file.yafl")], use_stdlib=False, just_testing=False)
        self.assertNotEqual("", result)
        print(result)
