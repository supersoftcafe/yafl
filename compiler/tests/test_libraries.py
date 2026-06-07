"""The library model: manifest parsing, discovery, namespace ownership, the
in-tree dev System fallback, and `.yl` zip libraries.

These exercise `libraries.py` in isolation — no compilation — so they're fast and
don't depend on the toolchain.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import libraries as L
from tests.testutil import TimedTestCase as TestCase


class TestManifest(TestCase):
    def test_parses_namespaces_and_native(self):
        m = L.parse_manifest(
            'name = "sys"\nnamespaces = ["System", "System::IO"]\n'
            'headers = "yafl.h"\nstatic_libs = ["libyafl.a"]\n', "t")
        self.assertEqual("sys", m.name)
        self.assertEqual(("System", "System::IO"), m.namespaces)
        self.assertEqual(("yafl.h",), m.headers)        # scalar normalised to tuple
        self.assertEqual(("libyafl.a",), m.static_libs)

    def test_missing_namespaces_is_an_error(self):
        with self.assertRaises(L.LibraryError):
            L.parse_manifest('name = "x"\n', "t")

    def test_malformed_toml_is_an_error(self):
        with self.assertRaises(L.LibraryError):
            L.parse_manifest("not = = toml", "t")


class TestNamespaceOwnership(TestCase):
    def test_duplicate_namespace_across_libraries_is_rejected(self):
        a = L.Library(L.Manifest("a", ("System",)), root=Path("/tmp/a"))
        b = L.Library(L.Manifest("b", ("System",)), root=Path("/tmp/b"))
        with self.assertRaises(L.LibraryError):
            L.namespace_index([a, b])

    def test_distinct_namespaces_index_cleanly(self):
        a = L.Library(L.Manifest("a", ("Foo",)), root=Path("/tmp/a"))
        b = L.Library(L.Manifest("b", ("Bar", "Bar::Baz")), root=Path("/tmp/b"))
        idx = L.namespace_index([a, b])
        self.assertIs(a, idx["Foo"])
        self.assertIs(b, idx["Bar::Baz"])


class TestDevSystemFallback(TestCase):
    def test_dev_system_library_is_complete(self):
        dev = L.dev_system_library()
        self.assertIsNotNone(dev, "in-tree System fallback should resolve (build yafllib first)")
        self.assertIn("System", dev.namespaces)
        self.assertTrue(dev.yafl_sources(), "should expose the stdlib sources")
        self.assertEqual(["yafl.h"], dev.header_names())
        statics = dev.static_libs()
        self.assertEqual(1, len(statics))
        self.assertTrue(statics[0].exists(), f"libyafl.a should exist at {statics[0]}")

    def test_available_libraries_owns_system(self):
        idx = L.namespace_index(L.available_libraries())
        self.assertIn("System", idx)
        self.assertIn("System::IO", idx)


class TestDirectoryAndZipLibraries(TestCase):
    def _write_dir_library(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "yafl.toml").write_text(
            'name = "mathlib"\nnamespaces = ["Math"]\nheaders = ["math.h"]\n'
            'static_libs = ["libmath.a"]\n', encoding="utf-8")
        (root / "area.yafl").write_text("namespace Math\nfun area(): Int\n  ret 0\n", encoding="utf-8")
        (root / "math.h").write_text("/* math */\n", encoding="utf-8")
        (root / "libmath.a").write_bytes(b"!<arch>\n")

    def test_discovers_directory_library(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write_dir_library(base / "mathlib")
            libs = L.discover_libraries([base])
            self.assertEqual(1, len(libs))
            lib = libs[0]
            self.assertEqual(("Math",), lib.namespaces)
            self.assertEqual(["area.yafl"], [s.filename for s in lib.yafl_sources()])
            self.assertEqual([base / "mathlib"], lib.include_dirs())
            self.assertEqual([base / "mathlib" / "libmath.a"], lib.static_libs())

    def test_discovers_and_materialises_yl_zip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            yl = base / "mathlib.yl"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("yafl.toml",
                    'name = "mathlib"\nnamespaces = ["Math"]\nheaders = ["math.h"]\n'
                    'static_libs = ["libmath.a"]\n')
                zf.writestr("area.yafl", "namespace Math\nfun area(): Int\n  ret 0\n")
                zf.writestr("math.h", "/* math */\n")
                zf.writestr("libmath.a", "!<arch>\n")
            yl.write_bytes(buf.getvalue())

            libs = L.discover_libraries([base])
            self.assertEqual(1, len(libs))
            lib = libs[0]
            self.assertTrue(lib.is_zip)
            self.assertEqual(["area.yafl"], [s.filename for s in lib.yafl_sources()])
            # Native artifacts get extracted to a cache dir that actually exists.
            statics = lib.static_libs()
            self.assertEqual(1, len(statics))
            self.assertTrue(statics[0].exists())
            self.assertTrue((lib.include_dirs()[0] / "math.h").exists())
