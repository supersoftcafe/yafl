"""Bootstrap C emission at -O0 must match Python byte for byte.

One test per module: unittest-parallel shards by MODULE, so keeping all four
optimisation levels in one file pinned them to a single worker. See
tests/bootstrap_c_base.py for the shared fixture and the comparison itself.
"""
from __future__ import annotations

from tests.bootstrap_c_base import BootstrapCBase


class TestBootstrapCO0(BootstrapCBase):
    def test_c_matches_python(self):
        self._compare_corpus(0, "c")

