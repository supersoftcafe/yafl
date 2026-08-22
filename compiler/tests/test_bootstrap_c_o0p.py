"""Bootstrap C emission at -O0 with --profile must match Python byte for byte.

The profile twin of test_bootstrap_c_o0: mode `cp` vs Python's
__create_c_code(profile=True) — instrumented enter/leave ops, the descriptor
table (names, files, lines — the dataclasses.replace-mirroring copy sites must
preserve them), and the yafl_prof_init line in main(). One test per module;
see tests/bootstrap_c_base.py.
"""
from __future__ import annotations

from tests.bootstrap_c_base import BootstrapCBase


class TestBootstrapCO0P(BootstrapCBase):
    def test_c_matches_python(self):
        self._compare_corpus(0, "cp", profile=True)
