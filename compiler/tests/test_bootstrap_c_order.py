"""Input order must not change the emitted C.

One test per module: unittest-parallel shards by MODULE. See
tests/bootstrap_c_base.py for the shared fixture.
"""
from __future__ import annotations

import random

from tests.bootstrap_c_base import (BootstrapCBase, _CORPUS, _STDLIB,
                                    _port_stream, _python_c_text,
                                    _run_port_c, _terminated)


class TestBootstrapCOrder(BootstrapCBase):

    def test_input_order_does_not_matter(self):
        """Statement order IS emission order, so the same files fed in a
        different order used to emit different C — which made the byte
        contract depend on every caller ordering its inputs by hand. Both
        compilers now sort by file NAME (the only key the port has: it sees
        `#FILE# <name>`, never a path). This guards that."""
        target = _CORPUS[0]
        canonical = _run_port_c(self.binary, _port_stream(target), "c")
        self.assertTrue(canonical, "port produced no C for the canonical order")
        files = _STDLIB + [target]
        for seed in (1, 2):
            shuffled = list(files)
            random.Random(seed).shuffle(shuffled)
            stream = "".join(f"#FILE# {q.name}\n{_terminated(q)}" for q in shuffled)
            self.assertEqual(canonical, _run_port_c(self.binary, stream, "c"),
                             f"port C changed when inputs were shuffled (seed {seed})")
        self.assertEqual(canonical.splitlines(),
                         _python_c_text(target.name, 0).splitlines(),
                         "port and Python disagree on the canonical order")
