"""Bootstrap C emission at -O1 must match Python byte for byte.

One test per module: unittest-parallel shards by MODULE, so keeping all four
optimisation levels in one file pinned them to a single worker. See
tests/bootstrap_c_base.py for the shared fixture and the comparison itself.
"""
from __future__ import annotations

from tests.bootstrap_c_base import BootstrapCBase


class TestBootstrapCO1(BootstrapCBase):
    def test_c_matches_python_O1(self):
        # bounds_elim, dead stores, static-object promotion, and the
        # pre-async collapse fixpoint (struct/tag/discriminator folds,
        # string concat/accumulation) plus stack promotion, both sides.
        self._compare_corpus(1, "c1")

