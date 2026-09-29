"""Tagged-union slots are laid out largest nominal size first, tag last.

Each IR type states a nominal size — Float64/Int64 8, DataPointer 6, IntPtr 5,
Float32/Int32 4, Int16 2, Int8 1, Str 16 — and compute_union_slots orders the
slots by it, so small fields pack together instead of padding the wide ones
apart. The order is an IR decision, not a C one: the numbers are ranks, not
byte counts (a DataPointer's 6 just places pointers between the 8s and 4s).

Str was missing from the old rank table and sorted LAST, after the byte
slots: `{obj, i8, i8, str_t, tag}` — json_pretty's Result union padded to
40 bytes where 32 suffice.
"""
import unittest

import codegen.typedecl as cg_t


def _slot_types(*variants):
    container, _ = cg_t.compute_union_slots(list(variants))
    return [ftype for _, ftype in container.fields[:-1]]   # drop $tag


class TestUnionSlotOrder(unittest.TestCase):
    def test_str_slot_precedes_pointer_and_byte_slots(self):
        variant = cg_t.Struct((("a", cg_t.Int(8)), ("b", cg_t.Str()), ("c", cg_t.DataPointer())))
        self.assertEqual([cg_t.Str(), cg_t.DataPointer(), cg_t.Int(8)], _slot_types(variant))

    def test_pointers_sit_between_eight_and_four(self):
        variant = cg_t.Struct((("a", cg_t.Int(32)), ("b", cg_t.DataPointer()),
                               ("c", cg_t.Float(64)), ("d", cg_t.Int(16))))
        self.assertEqual([cg_t.Float(64), cg_t.DataPointer(), cg_t.Int(32), cg_t.Int(16)],
                         _slot_types(variant))

    def test_gc_pointer_precedes_code_pointer(self):
        variant = cg_t.Struct((("f", cg_t.FuncPointer()),))
        self.assertEqual([cg_t.DataPointer(), cg_t.IntPtr()], _slot_types(variant))

    def test_equal_sizes_keep_first_use_order(self):
        variant = cg_t.Struct((("a", cg_t.Float(64)), ("b", cg_t.Int(64))))
        self.assertEqual([cg_t.Float(64), cg_t.Int(64)], _slot_types(variant))

    def test_the_tag_is_last(self):
        container, _ = cg_t.compute_union_slots([cg_t.Struct((("a", cg_t.Str()),))])
        self.assertEqual("$tag", container.fields[-1][0])


if __name__ == "__main__":
    unittest.main()
