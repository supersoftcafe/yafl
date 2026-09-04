"""bootstrap/driver/{toml,zip,libraries}.yafl — library discovery in the port.

THE GAP THIS CLOSES: the self-hosted compiler could not resolve
`import Some::Library` at all. It only ever read a pre-assembled whole-program
stream from stdin, so every library had to be concatenated for it by whoever
invoked it, while the reference compiler had located libraries on a search path
since the build system landed. A compiler that cannot find a library is missing
a capability, not a calling convention.

These diff the port's three new surfaces against the Python implementations
they were ported from:

  `ybootstrap toml`     manifest parsing        vs tomllib + parse_manifest
  `ybootstrap libs`     discovery on YAFL_PATH  vs discover_libraries
  `ybootstrap libsfor`  the load worklist       vs the fixpoint in compile_project

`.yl` archives are covered too: `package_system_library` now writes ZIP_STORED
specifically so the port's reader can be a header walk rather than a DEFLATE
decoder, and a compressed entry must be a clear error rather than an empty read.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import libraries

from tests.testutil import TimedTestCase as TestCase

_REPO = Path(__file__).parent.parent.parent


def _mklib(root: Path, name: str, namespaces: list[str], *, headers=(), statics=()):
    """A directory library: manifest plus one trivial source."""
    d = root / name
    d.mkdir(parents=True)
    ns = ", ".join(f'"{n}"' for n in namespaces)
    manifest = f'name = "{name}"\nnamespaces = [{ns}]\n'
    if headers:
        manifest += "headers = [" + ", ".join(f'"{h}"' for h in headers) + "]\n"
    if statics:
        manifest += "static_libs = [" + ", ".join(f'"{s}"' for s in statics) + "]\n"
    (d / "yafl.toml").write_text(manifest)
    (d / "a.yafl").write_text(f"namespace {namespaces[0]}\n")
    return d


class TestBootstrapLibraries(TestCase):
    _TIMEOUT = 300

    @classmethod
    def setUpClass(cls):
        from tests.testutil import shared_bootstrap_binary
        cls.binary = shared_bootstrap_binary()

    def _run(self, mode: str, stdin: str = "", env_extra: dict | None = None):
        env = dict(os.environ)
        env.pop("YAFL_PATH", None)
        if env_extra:
            env.update(env_extra)
        p = subprocess.run([str(self.binary), mode], input=stdin, env=env,
                           capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout

    # ── manifest parsing ────────────────────────────────────────────────────

    def test_manifest_fields_match_python(self):
        text = ('name = "system"\n'
                'namespaces = ["System", "System::Test"]\n'
                'headers = ["yafl.h"]\n'
                'static_libs = ["libyafl.a"]\n')
        rc, out = self._run("toml", text)
        self.assertEqual(0, rc, out)
        m = libraries.parse_manifest(text, "<test>")
        expected = (f"name={m.name}\n"
                    f"namespaces={','.join(m.namespaces)}\n"
                    f"headers={','.join(m.headers)}\n"
                    f"static_libs={','.join(m.static_libs)}\n")
        self.assertEqual(expected, out)

    def test_comments_and_blank_lines_are_ignored(self):
        rc, out = self._run("toml", '# a comment\n\nname = "x"\nnamespaces = ["N"]\n')
        self.assertEqual(0, rc, out)
        self.assertEqual("name=x\nnamespaces=N\n", out)

    def test_a_hash_inside_a_string_is_data_not_a_comment(self):
        # The naive `indexOf("#")` strip truncates this to `name = "a`.
        rc, out = self._run("toml", 'name = "a#b"\nnamespaces = ["N"]\n')
        self.assertEqual(0, rc, out)
        self.assertEqual("name=a#b\nnamespaces=N\n", out)

    def test_malformed_manifests_are_rejected(self):
        for bad in ('name\n', 'name = \n', 'name = "unterminated\n',
                    'name = ["a"\n', '= "novalue"\n'):
            rc, out = self._run("toml", bad)
            self.assertEqual(1, rc, f"{bad!r} should be rejected, got {out!r}")
            self.assertTrue(out.startswith("error:"), out)

    # ── discovery ───────────────────────────────────────────────────────────

    def test_discovery_matches_python(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "alpha", ["Alpha"], headers=["a.h"], statics=["liba.a"])
            _mklib(root, "beta", ["Beta", "Beta::Sub"])
            (root / "not-a-library").mkdir()      # no manifest: skipped, not an error

            rc, out = self._run("libs", env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)

            py = sorted(libraries.discover_libraries([root]),
                        key=lambda l: l.manifest.name)
            expected = "".join(
                f"{l.manifest.name}|{','.join(l.manifest.namespaces)}|"
                f"{','.join(l.manifest.headers)}|{','.join(l.manifest.static_libs)}\n"
                for l in py)
            self.assertEqual(expected, out)

    def test_a_directory_without_a_manifest_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "junk").mkdir()
            rc, out = self._run("libs", env_extra={"YAFL_PATH": td})
            self.assertEqual(0, rc, out)
            self.assertEqual("", out)

    def test_a_missing_search_path_is_skipped(self):
        rc, out = self._run("libs", env_extra={"YAFL_PATH": "/no/such/dir"})
        self.assertEqual(0, rc, out)
        self.assertEqual("", out)

    # ── .yl archives ────────────────────────────────────────────────────────

    def test_stored_yl_archive_is_read(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            yl = root / "packed.yl"
            with zipfile.ZipFile(yl, "w", zipfile.ZIP_STORED) as z:
                z.writestr("yafl.toml", 'name = "packed"\nnamespaces = ["Packed"]\n')
                z.writestr("a.yafl", "namespace Packed\n")
            rc, out = self._run("libs", env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("packed|Packed||\n", out)

    def test_a_COMPRESSED_entry_is_a_clear_error_not_an_empty_read(self):
        # The whole reason packaging uses ZIP_STORED. If someone switches it
        # back, this must fail loudly rather than yield a library with no
        # sources — which would look like an empty but valid library.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with zipfile.ZipFile(root / "z.yl", "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("yafl.toml", 'name = "z"\nnamespaces = ["Z"]\n' + "x" * 4000)
            rc, out = self._run("libs", env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(1, rc, out)
            self.assertIn("compressed", out)

    def test_the_shipped_system_yl_is_stored(self):
        """package_system_library must keep writing uncompressed."""
        import inspect
        src = inspect.getsource(libraries.package_system_library)
        self.assertIn("ZIP_STORED", src)
        self.assertNotIn("ZIP_DEFLATED", src)

    # ── the worklist ────────────────────────────────────────────────────────

    # Every source here carries a real statement, and that is not padding.
    # parse() CONSUMES the `import` lines and attaches each block's group to
    # the named statements of that block, so a file of nothing but a namespace
    # and imports has no statements — and therefore no visible imports — in
    # BOTH compilers. `_candidate_namespaces` returns the empty set for it.
    _PRELUDE = "fun f(): Int\n  ret 0\n"

    def test_an_import_resolves_to_its_library(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "alpha", ["Alpha"])
            _mklib(root, "beta", ["Beta"])
            src = "namespace P\nimport Alpha\n" + self._PRELUDE
            rc, out = self._run("libsfor", src, env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("alpha|Alpha||\n", out)
            self.assertEqual({"Alpha", "P"}, self._python_candidates(src))

    def test_a_source_with_NO_statements_sees_no_imports(self):
        """Pins the surprise above rather than leaving it to be rediscovered."""
        src = "namespace P\nimport Alpha\n"
        self.assertEqual(set(), self._python_candidates(src))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "alpha", ["Alpha"])
            rc, out = self._run("libsfor", src, env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("", out)

    def test_an_import_of_a_nested_namespace_resolves(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "deep", ["Deep::Inner"])
            src = "namespace P\nimport Deep::Inner\n" + self._PRELUDE
            rc, out = self._run("libsfor", src, env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("deep|Deep::Inner||\n", out)

    def test_a_QUALIFIED_REFERENCE_pulls_a_library_in_without_an_import(self):
        """`import` is not mandatory — the AST half of the candidate set.

        This is the half the port originally lacked: it collected the declared
        imports only, so a file that wrote `Alpha::thing` without importing
        Alpha compiled under the reference compiler and not under the port.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "alpha", ["Alpha"])
            src = "namespace P\nfun f(): Int\n  ret Alpha::thing\n"
            rc, out = self._run("libsfor", src, env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("alpha|Alpha||\n", out)
            # ...and the same set Python would compute.
            self.assertIn("Alpha", self._python_candidates(src))

    def test_a_qualified_reference_in_a_TYPE_counts_too(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "alpha", ["Alpha"])
            src = "namespace P\nfun f(x: Alpha::T): Int\n  ret 0\n"
            rc, out = self._run("libsfor", src, env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("alpha|Alpha||\n", out)

    def _python_candidates(self, src: str) -> set[str]:
        """What compiler.py would consider — the thing the port must match.

        `getattr` by string, not `c.__tokenize_and_parse`: inside a class body
        the latter mangles to `c._TestBootstrapLibraries__tokenize_and_parse`.
        """
        import compiler as c
        tokenize_and_parse = getattr(c, "__tokenize_and_parse")
        stmts, errors = tokenize_and_parse([c.Input(src, "x")])
        self.assertFalse(errors, errors)
        return c._candidate_namespaces(stmts)

    def test_TRANSITIVE_loading_follows_what_was_just_loaded(self):
        """The worklist is a fixpoint: a loaded library's own imports count.

        compile_project loops `while frontier`. A single round would load
        `mid` and stop, leaving `deep` — which `mid` imports — unloaded.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "deep", ["Deep"])
            mid = _mklib(root, "mid", ["Mid"])
            (mid / "a.yafl").write_text("namespace Mid\nimport Deep\n"
                                        "fun g(): Int\n  ret 0\n")
            rc, out = self._run("libsfor", "namespace P\nimport Mid\n" + self._PRELUDE,
                                env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("deep|Deep||\nmid|Mid||\n", out)

    def test_an_unresolvable_import_is_silently_no_library(self):
        # A miss is harmless by design: the candidate set is an
        # over-approximation, so most candidates match nothing.
        with tempfile.TemporaryDirectory() as td:
            rc, out = self._run("libsfor", "namespace P\nimport Nope\n" + self._PRELUDE,
                                env_extra={"YAFL_PATH": td})
            self.assertEqual(0, rc, out)
            self.assertEqual("", out)

    # ── things the port originally got wrong ────────────────────────────────
    # Each of these was a real defect found by review, and each is written so
    # that it fails against the code as it was rather than merely describing
    # the fix.

    def test_SOURCES_IN_SUBDIRECTORIES_are_read(self):
        """`yafl_sources` is `rglob`, not a listing of immediate children.

        The port listed one level, so a library laid out in sub-directories
        contributed ZERO statements — silently, because a library with no
        sources is not an error. Asserted through transitivity, so the missing
        statements are what shows.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "third", ["Third"])
            deep = _mklib(root, "deep", ["Deep"])
            (deep / "a.yafl").unlink()
            (deep / "sub").mkdir()
            (deep / "sub" / "b.yafl").write_text(
                "namespace Deep\nimport Third\nfun h(): Int\n  ret 0\n")
            rc, out = self._run("libsfor", "namespace P\nimport Deep\n" + self._PRELUDE,
                                env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("deep|Deep||\nthird|Third||\n", out)

    def test_TWO_LIBRARIES_CLAIMING_ONE_NAMESPACE_is_an_error(self):
        """namespace_index raises; the port must not silently pick the first."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "alpha", ["Shared"])
            _mklib(root, "beta", ["Shared"])
            rc, out = self._run("libsfor", "namespace P\nimport Shared\n" + self._PRELUDE,
                                env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(1, rc, out)
            self.assertIn("Shared", out)
            self.assertIn("two libraries", out)
            with self.assertRaises(libraries.LibraryError):
                libraries.namespace_index(libraries.discover_libraries([root]))

    def test_libraries_with_the_SAME_MANIFEST_NAME_are_both_loaded(self):
        """The worklist keys on identity, not on the manifest name.

        Every manifest without a `name` defaults to the same "unnamed", so a
        name-keyed worklist loaded the first and skipped the rest.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for d, ns in (("one", "One"), ("two", "Two")):
                p = root / d
                p.mkdir()
                (p / "yafl.toml").write_text(f'namespaces = ["{ns}"]\n')
                (p / "a.yafl").write_text(f"namespace {ns}\n")
            src = "namespace P\nimport One\nimport Two\n" + self._PRELUDE
            rc, out = self._run("libsfor", src, env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("unnamed|One||\nunnamed|Two||\n", out)
            # ...and "unnamed" is what Python calls them too.
            names = [l.manifest.name for l in libraries.discover_libraries([root])]
            self.assertEqual(["unnamed", "unnamed"], names)

    def test_a_DIRECTORY_named_dot_yl_does_not_kill_discovery(self):
        """_read_library_at tests is_dir() first; the port keyed on the suffix,
        so one oddly-named directory anywhere on the path aborted everything."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "alpha", ["Alpha"])
            (root / "notreally.yl").mkdir()
            rc, out = self._run("libs", env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("alpha|Alpha||\n", out)
            self.assertEqual(1, len(libraries.discover_libraries([root])))

    def test_the_same_directory_twice_on_the_path_is_ONE_library(self):
        """discover_libraries dedupes by resolved root; without it the
        duplicate-namespace check above would fail an ordinary repeated path."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mklib(root, "alpha", ["Alpha"])
            rc, out = self._run("libs", env_extra={"YAFL_PATH": f"{root}:{root}"})
            self.assertEqual(0, rc, out)
            self.assertEqual("alpha|Alpha||\n", out)

    # ── manifest edge cases, all diffed against parse_manifest ──────────────

    def test_a_MULTI_LINE_array_is_accepted(self):
        text = 'name = "x"\nnamespaces = [\n  "A",\n  "B",\n]\n'
        rc, out = self._run("toml", text)
        self.assertEqual(0, rc, out)
        m = libraries.parse_manifest(text, "<test>")
        self.assertEqual(("A", "B"), m.namespaces)
        self.assertEqual(f"name=x\nnamespaces={','.join(m.namespaces)}\n", out)

    def test_an_escaped_quote_before_a_hash_is_not_a_comment(self):
        text = 'name = "a\\"#b"\nnamespaces = ["N"]\n'
        rc, out = self._run("toml", text)
        self.assertEqual(0, rc, out)
        self.assertEqual(libraries.parse_manifest(text, "<t>").name, 'a"#b')
        self.assertEqual('name=a"#b\nnamespaces=N\n', out)

    def test_a_QUOTED_KEY_is_the_key_without_its_quotes(self):
        text = '"name" = "q"\nnamespaces = ["N"]\n'
        rc, out = self._run("toml", text)
        self.assertEqual(0, rc, out)
        self.assertEqual("q", libraries.parse_manifest(text, "<t>").name)
        self.assertEqual("name=q\nnamespaces=N\n", out)

    def test_an_EMPTY_name_falls_back_to_unnamed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "e"
            p.mkdir()
            (p / "yafl.toml").write_text('name = ""\nnamespaces = ["E"]\n')
            rc, out = self._run("libs", env_extra={"YAFL_PATH": str(root)})
            self.assertEqual(0, rc, out)
            self.assertEqual("unnamed|E||\n", out)
            self.assertEqual("unnamed",
                             libraries.discover_libraries([root])[0].manifest.name)

    def test_manifests_tomllib_REJECTS_are_rejected_here_too(self):
        """Accepting invalid input diverges just as much as rejecting valid."""
        for bad in ('name = "x"\nnamespaces = ["a" "b"]\n',      # missing comma
                    'name = "x"\nname = "y"\nnamespaces = ["N"]\n'):  # duplicate key
            with self.subTest(bad=bad):
                with self.assertRaises(libraries.LibraryError):
                    libraries.parse_manifest(bad, "<test>")
                rc, out = self._run("toml", bad)
                self.assertEqual(1, rc, out)
                self.assertTrue(out.startswith("error:"), out)

    def test_a_LARGE_manifest_does_not_overflow_the_stack(self):
        """`toml` mode reads arbitrary stdin; 30k lines used to abort (rc=134)."""
        text = 'name = "x"\nnamespaces = ["N"]\n' + "".join(
            f'k{i} = "v"\n' for i in range(30000))
        rc, out = self._run("toml", text)
        self.assertEqual(0, rc, out[:400])
        self.assertIn("name=x\n", out)

    def test_a_large_yl_is_read_in_reasonable_time(self):
        """readWholeFile accumulated with `acc + s`, which is quadratic: 40 MB
        took nearly two minutes. Well under the module timeout, but the shipped
        system.yl grows with libyafl.a."""
        import time
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with zipfile.ZipFile(root / "big.yl", "w", zipfile.ZIP_STORED) as z:
                z.writestr("yafl.toml", 'name = "big"\nnamespaces = ["Big"]\n')
                z.writestr("pad.bin", b"\0" * (24 * 1024 * 1024))
            started = time.monotonic()
            rc, out = self._run("libs", env_extra={"YAFL_PATH": str(root)})
            elapsed = time.monotonic() - started
            self.assertEqual(0, rc, out)
            self.assertEqual("big|Big||\n", out)
            self.assertLess(elapsed, 20.0, f"24MB .yl took {elapsed:.1f}s")
