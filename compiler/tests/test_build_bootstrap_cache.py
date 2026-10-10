"""build_bootstrap.py's reuse decision, with the expensive steps stubbed out.

The cached Python build of the port may compile new port sources in Python's
place only once a self-compile has VERIFIED it — passed against the C Python
emitted for it. Otherwise a divergence the failed self-compile exposed would
be carried into every later build, reproduced by the port it builds, and pass.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_bootstrap as bb


class TestReuseNeedsAVerifiedEntry(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "ybootstrap"
        self.c_out = self.dir / "ybootstrap.c"
        self.keys = {"python": "P", "sources": "S1", "link": "L"}
        self.calls: list[str] = []
        patches = [
            mock.patch.object(bb, "_python_key", lambda level: self.keys["python"]),
            mock.patch.object(bb, "_sources_key", lambda: self.keys["sources"]),
            mock.patch.object(bb, "_link_key", lambda: self.keys["link"]),
            mock.patch.object(bb, "_python_emit", self._python_emit),
            mock.patch.object(bb, "_port_emit", self._port_emit),
            mock.patch.object(bb, "_link", lambda c, out: out.write_text("bin:" + c)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def _python_emit(self, level):
        self.calls.append("python")
        return "C from python"

    def _port_emit(self, binary, level, lib):
        self.calls.append("port")
        return "C from port"

    def _build(self):
        bb.build(self.out, 3, self.c_out, reuse_lib_path="libs")
        return bb.reference_of(self.c_out)["reference"]

    def test_unverified_entry_is_rebuilt_by_python(self):
        self._build()                       # caches the Python build of S1
        self.keys["sources"] = "S2"         # the port's sources change...
        self.calls.clear()
        self.assertEqual("python", self._build())   # ...but no self-compile passed
        self.assertEqual(["python"], self.calls)

    def test_verified_entry_compiles_new_sources(self):
        self._build()
        bb.record_verified(self.c_out)      # the self-compile passed against it
        self.keys["sources"] = "S2"
        self.calls.clear()
        self.assertEqual("port", self._build())
        self.assertEqual(["port"], self.calls)

    def test_port_reference_does_not_verify(self):
        self._build()
        bb.record_verified(self.c_out)
        self.keys["sources"] = "S2"
        self._build()                        # reference: the cached port
        bb.record_verified(self.c_out)       # verifies nothing new
        verified = json.loads((self.dir / "bootstrap-cache" / "O3" / "verified.json").read_text())
        self.assertEqual({"python": "P", "sources": "S1"}, verified)

    def test_unchanged_sources_reuse_without_verification(self):
        # Nothing the build depends on changed: the cached binary IS Python's
        # build, so it is reused whether or not it was verified.
        self._build()
        self.calls.clear()
        self.assertEqual("python", self._build())
        self.assertEqual([], self.calls)


if __name__ == "__main__":
    unittest.main()
