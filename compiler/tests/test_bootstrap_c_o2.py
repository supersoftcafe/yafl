"""Bootstrap C emission at -O2 must match Python byte for byte.

One test per module: unittest-parallel shards by MODULE, so keeping all four
optimisation levels in one file pinned them to a single worker. See
tests/bootstrap_c_base.py for the shared fixture and the comparison itself.
"""
from __future__ import annotations

from tests.bootstrap_c_base import BootstrapCBase


class TestBootstrapCO2(BootstrapCBase):
    def test_c_matches_python_O2(self):
        # -O2 adds the bounded small-function inline fixpoint (IR inliner
        # + trim to shape stability) on both sides.
        self._compare_corpus(2, "c2")

