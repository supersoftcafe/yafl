"""Input order must not change the emitted C.

One test per module: unittest-parallel shards by MODULE. See
tests/bootstrap_c_base.py for the shared fixture.
"""
from __future__ import annotations

import random
from pathlib import Path

from tests.bootstrap_c_base import BootstrapCBase
from tests.testutil import compile_c_result, python_c_result

# Several units of ONE program — small [test] files, built as a test binary.
_UNITS = [Path(__file__).parent.parent / "yafl_tests" / name
          for name in ("args.yafl", "closure_capture_names.yafl",
                       "index_operator.yafl", "lambda_lift.yafl")]


class TestBootstrapCOrder(BootstrapCBase):

    def test_input_order_does_not_matter(self):
        """Statement order IS emission order, so the same files fed in a
        different order used to emit different C — which made the byte
        contract depend on every caller ordering its inputs by hand. Both
        compilers now sort by unit NAME — the path relative to the unit's
        root. A library's units are ordered by the loader; this guards the
        program's own, handed over in whatever order the command line lists
        them.

        Every ordering names each unit EXACTLY as the canonical one does: the
        name feeds hash6 and so feeds the emitted C, and renaming the inputs
        would make this test fail for a reason that has nothing to do with
        their order."""
        units = [(p.name, p.read_text()) for p in _UNITS]
        canonical = compile_c_result(units, test=True, command=self.port)
        self.assertTrue(canonical.c, f"port produced no C for the canonical order\n"
                                     f"{canonical.describe()}")
        for seed in (1, 2):
            shuffled = list(units)
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(canonical.c,
                             compile_c_result(shuffled, test=True, command=self.port).c,
                             f"port C changed when inputs were shuffled (seed {seed})")
        self.assert_same_compile(python_c_result(units, test=True), canonical,
                                 "canonical order")
