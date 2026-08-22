"""Bootstrap C emission at -O2 with --profile must match Python byte for byte.

The -O2 twin exists to pin the inliner gating: under --profile both IR
inliner blocks are DISABLED (compiler.py's `and not profile` mirrored by
create_c_code.yafl's `&& !profile`), so a divergence here means one compiler
inlined what the other kept. One test per module; see tests/bootstrap_c_base.py.
"""
from __future__ import annotations

from tests.bootstrap_c_base import BootstrapCBase


class TestBootstrapCO2P(BootstrapCBase):
    def test_c_matches_python(self):
        self._compare_corpus(2, "c2p", profile=True)
