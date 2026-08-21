"""Bootstrap C emission at -O3 must match Python byte for byte.

One test per module: unittest-parallel shards by MODULE, so keeping all four
optimisation levels in one file pinned them to a single worker. See
tests/bootstrap_c_base.py for the shared fixture and the comparison itself.
"""
from __future__ import annotations

from tests.bootstrap_c_base import BootstrapCBase


class TestBootstrapCO3(BootstrapCBase):
    def test_c_matches_python_O3(self):
        # -O3 adds [inline(always)] fusion and the single-caller fold with
        # vtable-slot trimming.
        self._compare_corpus(3, "c3")

