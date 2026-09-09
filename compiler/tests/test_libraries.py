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


class TestUnitNamesAreRelativePaths(TestCase):
    """A unit is named by its path relative to the library root, and a `.yl`
    stores that same path. The property that matters is the EQUALITY of the two
    forms: shipping a library as a package must not rename its units.

    The name is not cosmetic — `LineRef.hash6` hashes it into every generated
    symbol — so naming units by basename made two same-named units in different
    sub-directories indistinguishable to the hash.
    """

    _NESTED = {
        "Math/area.yafl": "namespace Math\nfun area(): Int\n  ret 0\n",
        "Math/Solid/volume.yafl": "namespace Math::Solid\nfun volume(): Int\n  ret 0\n",
        "top.yafl": "namespace Math\nfun top(): Int\n  ret 0\n",
    }

    def _write_nested(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "yafl.toml").write_text(
            'name = "mathlib"\nnamespaces = ["Math", "Math::Solid"]\n', encoding="utf-8")
        for rel, text in self._NESTED.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")

    def test_directory_units_are_named_by_relative_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "mathlib"
            self._write_nested(root)
            lib = L.discover_libraries([Path(d)])[0]
            # Sorted by the relative path, so sub-directories come first.
            self.assertEqual(["Math/Solid/volume.yafl", "Math/area.yafl", "top.yafl"],
                             [s.filename for s in lib.yafl_sources()])

    def test_packaging_preserves_paths_and_the_two_forms_agree(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            root = base / "mathlib"
            self._write_nested(root)
            header = base / "math.h"
            header.write_text("/* math */\n", encoding="utf-8")
            static = base / "libmath.a"
            static.write_bytes(b"!<arch>\n")
            yl = base / "pkg" / "system.yl"
            L.package_system_library(yl, root, header, static)

            with zipfile.ZipFile(yl) as zf:
                stored = sorted(n for n in zf.namelist() if n.endswith(".yafl"))
            self.assertEqual(["Math/Solid/volume.yafl", "Math/area.yafl", "top.yafl"],
                             stored, "the archive must keep each unit's relative path")

            packaged = L.discover_libraries([yl.parent])[0]
            self.assertTrue(packaged.is_zip)
            from_dir = L.discover_libraries([base])[0].yafl_sources()
            from_zip = packaged.yafl_sources()
            self.assertEqual([s.filename for s in from_dir],
                             [s.filename for s in from_zip],
                             "a library must present the same unit names however it ships")
            self.assertEqual([s.content for s in from_dir],
                             [s.content for s in from_zip])

    def test_same_basename_in_two_directories_hashes_apart(self):
        from parsing.tokenizer import LineRef
        a = LineRef("Math/util.yafl", 12, 15)
        b = LineRef("Text/util.yafl", 12, 15)
        self.assertNotEqual(a.hash6(), b.hash6(),
                            "the directory must reach hash6, or the two units "
                            "generate colliding symbol names")
        self.assertEqual("Math/util.yafl[12:15]", repr(a),
                         "a diagnostic names the unit, path included")
