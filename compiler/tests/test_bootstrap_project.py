"""`ybootstrap project` — COMPILING WITH LIBRARIES, byte-identical to Python.

This is the test the discovery work exists for. Finding a library proves
nothing on its own: the question is whether the port, handed a program that
says `import Some::Library` and nothing else, produces the same C as
`compiler.compile(..., lib_paths=[...])` does for the same inputs.

The layering mirrors Python's, and that is why there are two modes:

    `c`        __create_c_code over a statement set the CALLER assembled
    `project`  compile_project — the same pipeline, plus the loader

so `c` keeps its byte contract (~25 modules pin it) and stays independent of
the environment, while `project` is the one that reads YAFL_PATH.

Both sides are given the SAME library set and nothing else: the stdlib is
staged as an ordinary directory library, exactly as `package_system_library`
would ship it, and Python runs with `use_stdlib=False` so it takes the stdlib
from that library too rather than from its dev fallback. Anything less and the
two would be loading different statements in a different order, and statement
order is emission order.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import compiler as c
import libraries

from tests.testutil import TimedTestCase as TestCase

_REPO = Path(__file__).parent.parent.parent
_STDLIB_DIR = _REPO / "compiler" / "stdlib"


def _stage_stdlib_library(root: Path) -> Path:
    """The stdlib as a discoverable directory library.

    Namespaces are scanned exactly as `package_system_library` scans them, so
    this library owns precisely what the shipped `system.yl` owns. No headers
    or static_libs: this test compares emitted C, and a `static_libs` entry
    would drag in the native-artefact question that has nothing to do with it.
    """
    d = root / "system"
    d.mkdir(parents=True)
    sources = sorted(_STDLIB_DIR.glob("*.yafl"))
    ns = libraries._scan_namespaces(sources)
    (d / "yafl.toml").write_text(
        'name = "system"\nnamespaces = [%s]\n' % ", ".join(f'"{n}"' for n in ns))
    for src in sources:
        (d / src.name).write_text(src.read_text())
    return d


class TestBootstrapProject(TestCase):
    _TIMEOUT = 1800

    @classmethod
    def setUpClass(cls):
        assert os.environ.get("PYTHONHASHSEED") == "0", (
            "byte-identical C is only deterministic under PYTHONHASHSEED=0")
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    def _port(self, mode: str, source: str, yafl_path: Path):
        """Fed as a `#FILE# prog.yafl` stream, and the name is load-bearing:
        the filename feeds hash6, which feeds the generated names, which feed
        the emitted C. Bare stdin parses as "x" and every generated symbol
        then differs from Python's by its hash suffix alone."""
        env = dict(os.environ)
        env["YAFL_PATH"] = str(yafl_path)
        stream = f"#FILE# prog.yafl\n{source}"
        p = subprocess.run([str(self.binary), mode], input=stream, env=env,
                           capture_output=True, text=True, timeout=900)
        return p.returncode, p.stdout

    def _python(self, source: str, yafl_path: Path, level: int = 0) -> str:
        # use_stdlib=False: the stdlib comes from the staged library, not from
        # available_libraries' dev fallback, which would be a SECOND library
        # owning System and therefore a duplicate-namespace error.
        return c.compile([c.Input(source, "prog.yafl")], use_stdlib=False,
                         optimization_level=level, lib_paths=[str(yafl_path)])

    # ── the capability ──────────────────────────────────────────────────────

    def test_the_port_COMPILES_a_program_against_a_discovered_library(self):
        """Byte-identical C, from a program that only names its library."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            greet = root / "greet"
            greet.mkdir()
            (greet / "yafl.toml").write_text(
                'name = "greet"\nnamespaces = ["Greet"]\n')
            (greet / "greet.yafl").write_text(
                "namespace Greet\n"
                "import System\n"
                "\n"
                "fun greeting(): System::Int\n"
                "  ret 40 + 2\n")
            src = ("namespace Main\n"
                   "import System\n"
                   "import Greet\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Greet::greeting()\n")

            rc, port_c = self._port("project", src, root)
            self.assertEqual(0, rc, port_c[:2000])
            self.assertIn("main", port_c)
            python_c = self._python(src, root)
            self.assertTrue(python_c, "python produced no C")
            self.assertEqual(python_c.splitlines(), port_c.splitlines())

    def test_a_TRANSITIVE_library_is_compiled_in_too(self):
        """`Greet` imports `Punct`; the program never names `Punct`."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            punct = root / "punct"
            punct.mkdir()
            (punct / "yafl.toml").write_text(
                'name = "punct"\nnamespaces = ["Punct"]\n')
            (punct / "punct.yafl").write_text(
                "namespace Punct\n"
                "import System\n"
                "\n"
                "fun bang(): System::Int\n"
                "  ret 1\n")
            greet = root / "greet"
            greet.mkdir()
            (greet / "yafl.toml").write_text(
                'name = "greet"\nnamespaces = ["Greet"]\n')
            (greet / "greet.yafl").write_text(
                "namespace Greet\n"
                "import System\n"
                "import Punct\n"
                "\n"
                "fun greeting(): System::Int\n"
                "  ret 41 + Punct::bang()\n")
            src = ("namespace Main\n"
                   "import System\n"
                   "import Greet\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Greet::greeting()\n")

            rc, port_c = self._port("project", src, root)
            self.assertEqual(0, rc, port_c[:2000])
            self.assertEqual(self._python(src, root).splitlines(),
                             port_c.splitlines())

    def test_a_library_named_only_by_a_QUALIFIED_REFERENCE_is_loaded(self):
        """No `import Greet` at all — the AST half of the candidate set,
        end to end through a real compile."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            greet = root / "greet"
            greet.mkdir()
            (greet / "yafl.toml").write_text(
                'name = "greet"\nnamespaces = ["Greet"]\n')
            (greet / "greet.yafl").write_text(
                "namespace Greet\n"
                "import System\n"
                "\n"
                "fun greeting(): System::Int\n"
                "  ret 42\n")
            src = ("namespace Main\n"
                   "import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Greet::greeting()\n")

            rc, port_c = self._port("project", src, root)
            self.assertEqual(0, rc, port_c[:2000])
            self.assertEqual(self._python(src, root).splitlines(),
                             port_c.splitlines())

    def test_a_STORED_yl_library_compiles_the_same_as_a_directory(self):
        """The shipped shape: a library read out of a `.yl` archive."""
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            with zipfile.ZipFile(root / "greet.yl", "w", zipfile.ZIP_STORED) as z:
                z.writestr("yafl.toml", 'name = "greet"\nnamespaces = ["Greet"]\n')
                z.writestr("greet.yafl",
                           "namespace Greet\nimport System\n\n"
                           "fun greeting(): System::Int\n  ret 42\n")
            src = ("namespace Main\n"
                   "import System\n"
                   "import Greet\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Greet::greeting()\n")

            rc, port_c = self._port("project", src, root)
            self.assertEqual(0, rc, port_c[:2000])
            self.assertEqual(self._python(src, root).splitlines(),
                             port_c.splitlines())

    def test_sources_in_SUBDIRECTORIES_compile_in_the_same_order(self):
        """Order is the whole game: `__tokenize_and_parse` sorts a library's
        sources by BASENAME, while `yafl_sources` walks them by path. A library
        whose files sort differently the two ways pins that."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            lib = root / "multi"
            (lib / "sub").mkdir(parents=True)
            (lib / "yafl.toml").write_text(
                'name = "multi"\nnamespaces = ["Multi"]\n')
            # By path: "b.yafl" then "sub/a.yafl". By basename: a then b.
            (lib / "b.yafl").write_text(
                "namespace Multi\nimport System\n\n"
                "fun second(): System::Int\n  ret 2\n")
            (lib / "sub" / "a.yafl").write_text(
                "namespace Multi\nimport System\n\n"
                "fun first(): System::Int\n  ret 40\n")
            src = ("namespace Main\n"
                   "import System\n"
                   "import Multi\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Multi::first() + Multi::second()\n")

            rc, port_c = self._port("project", src, root)
            self.assertEqual(0, rc, port_c[:2000])
            self.assertEqual(self._python(src, root).splitlines(),
                             port_c.splitlines())

    def test_optimised_levels_match_too(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            greet = root / "greet"
            greet.mkdir()
            (greet / "yafl.toml").write_text(
                'name = "greet"\nnamespaces = ["Greet"]\n')
            (greet / "greet.yafl").write_text(
                "namespace Greet\nimport System\n\n"
                "fun greeting(): System::Int\n  ret 42\n")
            src = ("namespace Main\n"
                   "import System\n"
                   "import Greet\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Greet::greeting()\n")
            for mode, level in (("project1", 1),):
                with self.subTest(level=level):
                    rc, port_c = self._port(mode, src, root)
                    self.assertEqual(0, rc, port_c[:2000])
                    self.assertEqual(self._python(src, root, level).splitlines(),
                                     port_c.splitlines())

    # ── headers ─────────────────────────────────────────────────────────────

    def test_a_librarys_HEADERS_reach_the_generated_C(self):
        """`link_spec.headers` become #includes, yafl.h first and once."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            greet = root / "greet"
            greet.mkdir()
            # `sub/greet.h` — declared with a directory, included by BASENAME.
            (greet / "yafl.toml").write_text(
                'name = "greet"\nnamespaces = ["Greet"]\n'
                'headers = ["yafl.h", "sub/greet.h"]\n')
            (greet / "greet.yafl").write_text(
                "namespace Greet\nimport System\n\n"
                "fun greeting(): System::Int\n  ret 42\n")
            src = ("namespace Main\n"
                   "import System\n"
                   "import Greet\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Greet::greeting()\n")

            rc, port_c = self._port("project", src, root)
            self.assertEqual(0, rc, port_c[:2000])
            self.assertEqual(self._python(src, root).splitlines(),
                             port_c.splitlines())
            # By BASENAME (`sub/greet.h` -> `greet.h`), and yafl.h leads and
            # appears once even though the manifest declares it as well.
            self.assertIn("#include <greet.h>", port_c)
            self.assertEqual(1, port_c.count("#include <yafl.h>"), port_c[:400])

    # ── --test, with the library pulled in by the synthesised main ──────────

    def test_projecttest_LOADS_System_Test_through_the_worklist(self):
        """The `--test` path loads libraries too.

        `__test_registry_source` emits fully-qualified `System::Test::run`, and
        that reference is what pulls System::Test in — the registry is part of
        the user statements BEFORE the worklist runs. The port used to require
        the caller to have concatenated System::Test into the stream.
        """
        import shutil
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            shutil.copytree(_REPO / "compiler" / "libs" / "system-test",
                            root / "system-test")
            src = ("namespace Demo\n"
                   "import System\n"
                   "import System::Test\n"
                   "\n"
                   "fun [test(\"one plus one\")] adds(): None|TestFailure\n"
                   "  ret assertEqInt(1 + 1, 2, \"1+1\")\n")

            rc, port_c = self._port("projecttest", src, root)
            self.assertEqual(0, rc, port_c[:2000])
            python_c, _spec, _warn = c.compile_project(
                [c.Input(src, "prog.yafl")], use_stdlib=False,
                lib_paths=[str(root)], test_mode=True)
            self.assertTrue(python_c, "python produced no C")
            self.assertEqual(python_c.splitlines(), port_c.splitlines())

    # ── native artefacts: the LinkSpec, and extracting them from a .yl ──────

    def _spec(self, source: str, yafl_path: Path):
        rc, out = self._port("linkspec", source, yafl_path)
        self.assertEqual(0, rc, out[:800])
        got = {}
        for line in out.splitlines():
            key, _, rest = line.partition("=")
            got[key] = [v for v in rest.split(",") if v]
        return got

    def _python_spec(self, source: str, yafl_path: Path):
        _c, spec, _w = c.compile_project(
            [c.Input(source, "prog.yafl")], use_stdlib=False,
            lib_paths=[str(yafl_path)])
        self.assertIsNotNone(spec, "python produced no link spec")
        headers = ("yafl.h",) + tuple(h for h in spec.headers if h != "yafl.h")
        return {"headers": list(headers),
                "includes": [str(p) for p in spec.include_dirs],
                "statics": [str(p) for p in spec.static_libs]}

    _USES_GREET = ("namespace Main\n"
                   "import System\n"
                   "import Greet\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Greet::greeting()\n")

    def test_the_LINK_SPEC_of_a_directory_library_matches_python(self):
        """Headers by basename, -I dirs by the header's directory, archives by
        absolute path — and de-duplicated in INSERTION order, not sorted."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            greet = root / "greet"
            (greet / "inc").mkdir(parents=True)
            (greet / "yafl.toml").write_text(
                'name = "greet"\nnamespaces = ["Greet"]\n'
                'headers = ["inc/greet.h"]\nstatic_libs = ["libgreet.a"]\n')
            (greet / "greet.yafl").write_text(
                "namespace Greet\nimport System\n\n"
                "fun greeting(): System::Int\n  ret 42\n")
            (greet / "inc" / "greet.h").write_text("/* greet */\n")
            (greet / "libgreet.a").write_bytes(b"!<arch>\n")

            self.assertEqual(self._python_spec(self._USES_GREET, root),
                             self._spec(self._USES_GREET, root))

    def test_a_yl_s_NATIVE_FILES_ARE_EXTRACTED_to_the_same_cache_as_python(self):
        """The point of the content-hash cache: a `.yl`'s header and archive
        live inside the zip, where no linker can reach them. Both compilers
        must extract them to the SAME directory, or each writes a copy the
        other never looks at."""
        import shutil
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            yl = root / "greet.yl"
            with zipfile.ZipFile(yl, "w", zipfile.ZIP_STORED) as z:
                z.writestr("yafl.toml",
                           'name = "greet"\nnamespaces = ["Greet"]\n'
                           'headers = ["inc/greet.h"]\nstatic_libs = ["libgreet.a"]\n')
                z.writestr("greet.yafl",
                           "namespace Greet\nimport System\n\n"
                           "fun greeting(): System::Int\n  ret 42\n")
                z.writestr("inc/greet.h", "/* greet */\n")
                z.writestr("libgreet.a", b"!<arch>\n" + b"\0" * 64)

            # A cold cache, so what appears is what the PORT extracted.
            cache = Path(tempfile.gettempdir()) / "yafl-lib-cache"
            expected = libraries._read_library_at(yl)._materialised_native_dir()
            shutil.rmtree(expected, ignore_errors=True)

            got = self._spec(self._USES_GREET, root)
            self.assertEqual([str(expected / "inc")], got["includes"])
            self.assertEqual([str(expected / "libgreet.a")], got["statics"])
            self.assertEqual(["yafl.h", "greet.h"], got["headers"])
            # Extracted by the PORT, byte for byte, into Python's directory.
            self.assertTrue(expected.is_dir(), f"{expected} was not created")
            self.assertEqual(b"/* greet */\n", (expected / "inc" / "greet.h").read_bytes())
            self.assertEqual(b"!<arch>\n" + b"\0" * 64,
                             (expected / "libgreet.a").read_bytes())
            self.assertEqual(str(cache), str(expected.parent))
            # ...and Python agrees on every path.
            self.assertEqual(self._python_spec(self._USES_GREET, root), got)

    def test_a_library_with_no_native_files_contributes_no_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            greet = root / "greet"
            greet.mkdir()
            (greet / "yafl.toml").write_text(
                'name = "greet"\nnamespaces = ["Greet"]\n')
            (greet / "greet.yafl").write_text(
                "namespace Greet\nimport System\n\n"
                "fun greeting(): System::Int\n  ret 42\n")
            got = self._spec(self._USES_GREET, root)
            self.assertEqual(["yafl.h"], got["headers"])
            self.assertEqual([], got["includes"])
            self.assertEqual([], got["statics"])

    def test_a_manifest_naming_a_MISSING_zip_entry_is_an_error(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            with zipfile.ZipFile(root / "greet.yl", "w", zipfile.ZIP_STORED) as z:
                z.writestr("yafl.toml",
                           'name = "greet"\nnamespaces = ["Greet"]\n'
                           'static_libs = ["absent.a"]\n')
                z.writestr("greet.yafl",
                           "namespace Greet\nimport System\n\n"
                           "fun greeting(): System::Int\n  ret 42\n")
            rc, out = self._port("linkspec", self._USES_GREET, root)
            self.assertEqual(1, rc, out[:400])
            self.assertIn("absent.a", out)

    # ── end to end, against the SHIPPED system.yl ───────────────────────────

    def test_the_port_builds_a_RUNNING_BINARY_from_the_shipped_system_yl(self):
        """The whole chain, with nothing staged by hand.

        `build/stage/system.yl` is the artefact CMake installs: a ZIP_STORED
        archive holding the stdlib sources, `yafl.h` and `libyafl.a`. The port
        is given only the search path and a program. It has to discover the
        archive, read the sources out of it, emit C, extract yafl.h and
        libyafl.a to the cache so the C compiler and linker can reach them,
        and hand back the paths — and the binary that comes out has to run.
        """
        system_yl = _REPO / "build" / "stage" / "system.yl"
        if not system_yl.is_file():
            self.skipTest(f"{system_yl} not built")
        src = ("namespace Main\n"
               "import System\n"
               "\n"
               "fun main(): System::Int\n"
               "  ret 42\n")
        stage = system_yl.parent

        rc, port_c = self._port("project", src, stage)
        self.assertEqual(0, rc, port_c[:2000])
        spec = self._spec(src, stage)
        self.assertTrue(spec["statics"], "no archive to link")
        self.assertTrue(spec["includes"], "no -I directory")
        for path in spec["statics"] + spec["includes"]:
            self.assertTrue(Path(path).exists(), f"{path} was not extracted")

        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "prog"
            inc = [a for d in spec["includes"] for a in ("-I", d)]
            link = subprocess.run(
                ["clang", "-x", "c", "-", "-O1", "-std=c11", *inc,
                 "-x", "none", *spec["statics"],
                 "-lpthread", "-lm", "-ldl", "-o", str(binary)],
                input=port_c, text=True, capture_output=True, timeout=600)
            self.assertEqual(0, link.returncode, link.stderr[:3000])
            run = subprocess.run([str(binary)], capture_output=True, timeout=120)
            self.assertEqual(42, run.returncode,
                             f"stdout={run.stdout!r} stderr={run.stderr!r}")

    # ── failure paths ───────────────────────────────────────────────────────

    def test_an_UNRESOLVABLE_import_fails_like_any_undefined_name(self):
        """A missing library is not a loader error: the candidate set is an
        over-approximation, so it simply matches nothing and the reference
        goes undefined — which both compilers then report."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            src = ("namespace Main\n"
                   "import System\n"
                   "\n"
                   "fun main(): System::Int\n"
                   "  ret Absent::thing()\n")
            rc, port_out = self._port("project", src, root)
            self.assertEqual(1, rc, port_out[:800])
            self.assertIn("Absent", port_out)

    def test_a_broken_manifest_on_the_path_is_reported_not_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _stage_stdlib_library(root)
            bad = root / "bad"
            bad.mkdir()
            (bad / "yafl.toml").write_text("namespaces = [oops]\n")
            src = ("namespace Main\nimport System\n\n"
                   "fun main(): System::Int\n  ret 0\n")
            rc, port_out = self._port("project", src, root)
            self.assertEqual(1, rc, port_out[:800])
            self.assertIn("error:", port_out)
            with self.assertRaises(libraries.LibraryError):
                libraries.discover_libraries([root])
