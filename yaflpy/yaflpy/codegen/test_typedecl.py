from __future__ import annotations

from unittest import TestCase

from codegen.typedecl import Int, FuncPointer, word_size, Struct, DataPointer, Array


class TestInt(TestCase):
    def setUp(self):
        self.target = Int(32)
        self.cache = {}

    def test_size(self):
        size = self.target.size
        self.assertEqual(size, 4)

    def test_initialise(self):
        str = self.target.initialise({}, 100)
        self.assertEqual(str, "100")

    def test_declare(self):
        str = self.target.declare(self.cache)
        self.assertEqual(str, "int32_t")

    def test_declare_bigint(self):
        str = Int(0).declare(self.cache)
        self.assertEqual(str, "void*")

    def test_get_pointer_paths(self):
        paths = self.target.get_pointer_paths("v")
        self.assertListEqual([], paths)


class TestFuncPointer(TestCase):
    def setUp(self):
        self.target = FuncPointer()
        self.cache = {}

    def test_size(self):
        size = self.target.size
        self.assertEqual(word_size * 2, size)

    def test_offsetof(self):
        offset = self.target.offsetof(0)
        self.assertEqual(0, offset)
        offset = self.target.offsetof(1)
        self.assertEqual(word_size, offset)

    def test_initialise(self):
        str = self.target.initialise({}, "@globalfunction")
        self.assertRegex(str, r'\s*{\s*\.f\s*=\s*@globalfunction\s*,\s*\.o\s*=\s*NULL\s*}\s*')
        str = self.target.initialise({}, {'f': "@otherfunc", 'o': "@object"})
        self.assertRegex(str, r'\s*{\s*\.f\s*=\s*@otherfunc\s*,\s*\.o\s*=\s*@object\s*}\s*')

    def test_declare(self):
        str = self.target.declare(self.cache)
        self.assertEqual('fun_t', str)

    def test_get_pointer_paths(self):
        paths = self.target.get_pointer_paths("v")
        self.assertListEqual(["v.o"], paths)


class TestStruct(TestCase):
    def setUp(self):
        self.target = Struct((('1chr', Int(8)), ('2int', Int(32)), ('3ptr', DataPointer()), ('4fun', FuncPointer())))
        self.cache = {}

    def test_size(self):
        size = self.target.size
        self.assertEqual(8 + (word_size * 3), size)

    def test_alignment(self):
        alignment = self.target.alignment
        self.assertEqual(word_size, alignment)

    def test_offsetof(self):
        offset = self.target.offsetof(1)
        self.assertEqual(4, offset)
        offset = self.target.offsetof(3, 0)
        self.assertEqual(8 + word_size, offset)
        offset = self.target.offsetof(3, 1)
        self.assertEqual(8 + (word_size * 2), offset)

    def test_initialise(self):
        str = self.target.initialise({}, {'1chr': 1, '2int': 2, '4fun': {'f': "@fun", 'o': "@obj"}})
        self.assertRegex(str, r'\.1chr\s*=\s*1\s*,')
        self.assertRegex(str, r'\.2int\s*=\s*2\s*,')
        self.assertNotRegex(str, r'.3ptr')
        self.assertRegex(str, r'(?m)\.4fun\s*=\s*\(fun_t\){\s*\.f\s*=\s*@fun\s*')

    def test_declare(self):
        str = self.target.declare(self.cache)
        self.assertRegex(str, r'struct_anon_[0-9]+_t')
        name, declaration = self.cache[self.target]
        self.assertRegex(declaration, r'int8_t\s+1chr\s*;')
        self.assertRegex(declaration, r'int32_t\s+2int\s*;')
        self.assertRegex(declaration, r'void\*\s+3ptr\s*;')

    def test_get_pointer_paths(self):
        paths = self.target.get_pointer_paths("v")
        self.assertListEqual(["v.3ptr", "v.4fun.o"], paths)


class TestArray(TestCase):
    def setUp(self):
        self.target = Array(Int(16), 0)
        self.cache = {}

    def test_size(self):
        size = self.target.size
        self.assertEqual(0, size)

    def test_offsetof(self):
        offset = self.target.offsetof(6)
        self.assertEqual(12, offset)

    def test_initialise(self):
        str = Array(Int(16), 3).initialise({}, [1, 2, 3])
        self.assertRegex(str, r'\.a\[0\]\s*=\s*1\s*')
        self.assertRegex(str, r'\.a\[1\]\s*=\s*2\s*')
        self.assertRegex(str, r'\.a\[2\]\s*=\s*3\s*')

    def test_get_pointer_paths(self):
        paths = Array(FuncPointer(), 2).get_pointer_paths("v")
        self.assertListEqual(["v.a[0].o", "v.a[1].o"], paths)

