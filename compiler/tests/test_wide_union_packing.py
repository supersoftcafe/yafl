"""Wide unions pack scalar and function members into one 16-byte str_t.

A collapsing union with a String or function member is a String value:
scalar members ride as spare codes in word 0 with the payload in word 1, a
function stores its environment in word 0 and its code pointer in word 1.
The two programs live in the bootstrap parity corpus (corpus_converge/), so
the port's C for them is pinned against Python's too; here they run, at -O0
and -O2, against output checked by hand when the packing was introduced.
"""
from __future__ import annotations

from pathlib import Path

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import compile_and_run_stdlib_capture

_CORPUS = Path(__file__).parent / "corpus_converge"

_SCALARS_EXPECTED = 'S:three the-string-three str three S:a much longer string than fifteen bytes S:even I:0 S:p0 sthree\nI:10 five-or-ten num 10 F:0.25 L:1000000000000 N N i10\nN none nothing F S:even I:2 S:p2 n\nS:three the-string-three str three N L:3000000000000 N N sthree\nI:40 other-int:40 num 40 S:a much longer string than fifteen bytes S:even I:4 S:p4 i40\nN none nothing F:1.25 L:5000000000000 N N n\nS:three the-string-three str three T S:even I:6 S:p6 sthree\nI:70 other-int:70 num 70 N L:7000000000000 N N i70\nN none nothing S:a much longer string than fifteen bytes S:even I:8 S:p8 n\nS:three the-string-three str three F:2.25 L:9000000000000 N N sthree\nI:100 other-int:100 num 100 T S:even I:10 S:p10 i100\nN none nothing N L:11000000000000 N N n\nS:three;I:10;N;S:three;I:40;N;S:three;I:70;\nI:40 F:1.25\n'

_FUNS_EXPECTED = 'f10 sstr0 i0 w0 f1 p1\nf20 f101 f6 f6 f2 f3\nnone n i14 w2 n p5\nf13 sstr3 f6 f8 f4 f5\nf20 f401 i28 w4 f2 p9\nnone n f6 f10 n f7\nf16 sstr6 i42 w6 f7 p13\nf20 f701 f6 f12 f2 f9\nnone n i56 w8 n p17\nf13 f401\n'


class TestWideUnionPacking(TestCase):
    def _check(self, name: str, expected: str):
        src = (_CORPUS / name).read_text()
        for level in (0, 2):
            with self.subTest(optimization_level=level):
                rc, out = compile_and_run_stdlib_capture(src, timeout=15,
                                                         optimization_level=level)
                self.assertEqual(0, rc)
                self.assertEqual(expected, out)

    def test_scalar_members(self):
        self._check("wide_union_scalars.yafl", _SCALARS_EXPECTED)

    def test_function_members(self):
        self._check("wide_union_funs.yafl", _FUNS_EXPECTED)
