"""bootstrap/format/ — the formatter (#91): `yaflc --format` and
`--format-check`.

There is one layout for YAFL source; nobody chooses it per project. Two kinds
of test pin it down:

  the rules      one small program per layout rule (USER RULINGS #91), with
                 the formatter's output written out verbatim — a change to
                 the layout is a change to this file;
  the round trip every source the repository ships (the bootstrap and the
                 standard library) formatted: it still parses to the same
                 tree, keeps every comment in order, and a second format
                 changes nothing.

The formatter is the port's alone (USER RULING #91), so there is no Python
side to compare with.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from parsing import tokenizer

from tests.testutil import TimedTestCase, shared_bootstrap_binary, stdlib_files, _RUN_ENV

_REPO = Path(__file__).resolve().parent.parent.parent

# The repository's own sources: what the round trip formats.
_CORPUS = stdlib_files() + sorted((_REPO / "bootstrap").rglob("*.yafl"))


def _comments(src: str) -> list[str]:
    """The comments in `src`, in order, each without trailing blanks: read
    with the Python tokenizer's own token table, so a `#` inside a string is
    not taken for one."""
    kinds = vars(tokenizer)["__kinds"]
    found = []
    for line in src.splitlines():
        at = 0
        while at < len(line):
            for expr, _kind in kinds:
                if m := expr.match(line, at):
                    if m[0].startswith("#"):
                        found.append(m[0].rstrip())
                    at = m.end()
                    break
            else:
                at += 1
    return found


def _tree(dump: str) -> str:
    """An AST dump without what layout changes: positions and the name
    hashes made from them. The names `true` and `false` count as the literals:
    `a ? b : false` prints as `a && b`, whose parse holds the literal (USER
    RULING #91)."""
    dump = re.sub(r"\|\d+:\d+\|", "||", dump)
    dump = re.sub(r"Name\|\|(true|false)\|", lambda m: "Bool||" + m[1].capitalize(), dump)
    return re.sub(r"[@$][A-Za-z0-9]{6}", "@H", dump)


# ── the rules ────────────────────────────────────────────────────────────────

# Each: the source as written, and its one layout.

_RULES = {
    # Wrapped arguments: broken after `(`, four in, filled.
    "args_fill": ("""\
namespace Fmt

import System

fun combine(alpha: Int, beta: Int, gamma: Int, delta: Int, epsilon: Int, zeta: Int, eta: Int, theta: Int): Int => alpha
fun use(): Int => combine(1000000001, 1000000002, 1000000003, 1000000004, 1000000005, 1000000006, 1000000007, 1000000008)
""",
"""\
namespace Fmt

import System

fun combine(alpha: Int, beta: Int, gamma: Int, delta: Int, epsilon: Int, zeta: Int, eta: Int, theta: Int): Int => alpha
fun use(): Int => combine(
    1000000001, 1000000002, 1000000003, 1000000004, 1000000005, 1000000006, 1000000007, 1000000008)
"""),

    # A `=>` body stays on its line when wrapping its call's arguments is enough.
    "arrow_body": ("""\
namespace Fmt

import System

fun describeTheThingWithAVeryLongNameIndeed(first: String, second: String, third: String): String => first + second
fun wrapped(first: String, second: String, third: String): String => describeTheThingWithAVeryLongNameIndeed(first, second, third)
""",
"""\
namespace Fmt

import System

fun describeTheThingWithAVeryLongNameIndeed(first: String, second: String, third: String): String => first + second
fun wrapped(first: String, second: String, third: String): String => describeTheThingWithAVeryLongNameIndeed(
    first, second, third)
"""),

    # A ternary chain: each `:` link leads its line, four in.
    "ternary_chain": ("""\
namespace Fmt

import System

fun grade(score: Int): String
  let label = score > 90 ? "excellent work, top of the class" : score > 75 ? "good work, well above the middle" : score > 50 ? "a pass" : "not yet"
  ret label
""",
"""\
namespace Fmt

import System

fun grade(score: Int): String
  let label = score > 90 ? "excellent work, top of the class"
      : score > 75 ? "good work, well above the middle"
      : score > 50 ? "a pass"
      : "not yet"
  ret label
"""),

    # Pipelines: once wrapped, every `|>` on its own line, four in. A lambda stage whose
    # body is a pipeline carries it on at the same depth.
    "pipeline": ("""\
namespace Fmt

import System
import System::Containers

fun short(xs: List<Int>): List<Int> => xs |> (ys) => map(ys, (y) => y + 1)
fun long(xs: List<Int>): List<Int> => xs |> (ys) => map(ys, (y) => y + 1) |> (ys) => filter(ys, (y) => y > 10) |> (ys) => map(ys, (y) => y * 2)
fun chained(xs: List<Int>): Int => xs |> (ys) => map(ys, (y) => y + 1) |> (ys) => fold(ys, 0, (a, y) => a + y)
""",
"""\
namespace Fmt

import System
import System::Containers

fun short(xs: List<Int>): List<Int> => xs |> (ys) => map(ys, (y) => y + 1)
fun long(xs: List<Int>): List<Int> => xs
    |> (ys) => map(ys, (y) => y + 1)
    |> (ys) => filter(ys, (y) => y > 10)
    |> (ys) => map(ys, (y) => y * 2)
fun chained(xs: List<Int>): Int => xs |> (ys) => map(ys, (y) => y + 1) |> (ys) => fold(ys, 0, (a, y) => a + y)
"""),

    # Match arms: one space before `=>`, no alignment. Wrapped literal alternatives: `|` leads.
    "match_arms": ("""\
namespace Fmt

import System

fun name(x: Int|String|None): String => match(x)
  (i: Int)       => "int"
  (s: String)    => s
  ()             => "none"

fun kind(c: Int32): String => match(c)
  ('0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' | 'a' | 'b' | 'c' | 'd' | 'e' | 'f' | 'A' | 'B' | 'C' | 'D') => "hex"
  ()       => "other"
""",
"""\
namespace Fmt

import System

fun name(x: Int|String|None): String => match(x)
  (i: Int) => "int"
  (s: String) => s
  () => "none"

fun kind(c: Int32): String => match(c)
  (
      '0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' | 'a' | 'b' | 'c' | 'd' | 'e' | 'f' | 'A' | 'B' | 'C'
      | 'D') => "hex"
  () => "other"
"""),

    # Blank lines: one between declarations, two above a banner and one below, runs inside
    # a block collapse to one.
    "blank_lines": ("""\
namespace Fmt
import System
fun one(): Int
  let a = 1


  let b = 2
  ret a + b
# ── section ──────────────────────────────────────────────────────────────────
fun two(): Int
  let t = 2
  ret t



fun three(): Int
  let t = 3
  ret t
""",
"""\
namespace Fmt

import System

fun one(): Int
  let a = 1

  let b = 2
  ret a + b


# ── section ──────────────────────────────────────────────────────────────────

fun two(): Int
  let t = 2
  ret t

fun three(): Int
  let t = 3
  ret t
"""),

    # Unions are tight.
    "unions": ("""\
namespace Fmt

import System

fun pick(x: Int | String | None): Int | None => None
""",
"""\
namespace Fmt

import System

fun pick(x: Int|String|None): Int|None => None
"""),

    # Comments are re-indented, never rewrapped; a trailing one is one space after the code.
    "comments": ("""\
namespace Fmt

import System

# A leading comment.
fun f(a: Int): Int
      # Re-indented, not rewrapped:   spacing   kept.
      let b = a + 1    # trailing, one space before
      ret b
""",
"""\
namespace Fmt

import System

# A leading comment.
fun f(a: Int): Int
  # Re-indented, not rewrapped:   spacing   kept.
  let b = a + 1 # trailing, one space before
  ret b
"""),

    # Imports: the `System` group, then the rest, each sorted, duplicates dropped.
    "imports": ("""\
namespace Fmt

import Zeta::Thing
import System::IO
import Alpha
import System
import Zeta::Thing

fun f(): System::Int => 0
""",
"""\
namespace Fmt

import System
import System::IO

import Alpha
import Zeta::Thing

fun f(): System::Int => 0
"""),

    # A wrapped signature: parameters four in, filled; the return type after `)`; `where` on
    # its own line.
    "signature": ("""\
namespace Fmt

import System

fun streamSomethingAlongTheWay<S, T, E>(source: S, initialValue: T, errorFallback: E, howManyTimes: Int): (stream: S, value: T) where Stream<S, T, E> => (stream = source, value = initialValue)
""",
"""\
namespace Fmt

import System

fun streamSomethingAlongTheWay<S, T, E>(
    source: S, initialValue: T, errorFallback: E, howManyTimes: Int): (stream: S, value: T)
    where Stream<S, T, E> => (stream = source, value = initialValue)
"""),

    # A body that is only `ret e` is `=> e`.
    "ret_only": ("""\
namespace Fmt

import System

fun f(a: Int): Int
  ret a * 2
""",
"""\
namespace Fmt

import System

fun f(a: Int): Int => a * 2
"""),

    # Members: one-liners pack; a member on more than one line has a blank line each side.
    "members": ("""\
namespace Fmt

import System

class Point(x: Int, y: Int)
  fun sum(): Int => x + y
  fun diff(): Int => x - y
  fun scaled(k: Int): Point
    let nx = x * k
    ret Point(nx, y * k)
  fun neg(): Point => Point(0 - x, 0 - y)
""",
"""\
namespace Fmt

import System

class Point(x: Int, y: Int)
  fun sum(): Int => x + y
  fun diff(): Int => x - y

  fun scaled(k: Int): Point
    let nx = x * k
    ret Point(nx, y * k)

  fun neg(): Point => Point(0 - x, 0 - y)
"""),

    # Top level: one-line declarations pack, as members do.
    "packing": ("""\
namespace Fmt

import System

let [const] ONE: Int = 1
let [const] TWO: Int = 2
fun three(): Int => 3
fun four(): Int
  ret ONE + 3
fun five(): Int => 5
class Six(x: Int)
fun seven(x: Int): Int => match(x)
  (0) => 0
  ()  => 7
fun eight(): Int => 8
""",
"""\
namespace Fmt

import System

let [const] ONE: Int = 1
let [const] TWO: Int = 2
fun three(): Int => 3
fun four(): Int => ONE + 3
fun five(): Int => 5
class Six(x: Int)

fun seven(x: Int): Int => match(x)
  (0) => 0
  () => 7

fun eight(): Int => 8
"""),

    # The shortest spelling: `&&`, `||`, `is`, and brackets only where precedence needs them.
    "minimal": ("""\
namespace Fmt

import System

fun both(a: Bool, b: Bool): Bool => a ? b : false
fun either(a: Bool, b: Bool): Bool => a ? true : b
fun isInt(x: Int|String): Bool => match(x)
  (_: Int) => true
  ()       => false
fun parens(a: Int, b: Int, c: Int): Int => ((a + b)) * (c) + (a * b)
""",
"""\
namespace Fmt

import System

fun both(a: Bool, b: Bool): Bool => a && b
fun either(a: Bool, b: Bool): Bool => a || b
fun isInt(x: Int|String): Bool => x is Int
fun parens(a: Int, b: Int, c: Int): Int => (a + b) * c + a * b
"""),

    # A ternary in the `?` branch keeps its brackets; one in the `:` branch is a chain link.
    "nested_ternary": ("""\
namespace Fmt

import System

fun f(a: Bool, b: Bool): Int => a ? (b ? 1 : 2) : 3
fun g(a: Bool, b: Bool): Int => a ? 1 : (b ? 2 : 3)
""",
"""\
namespace Fmt

import System

fun f(a: Bool, b: Bool): Int => a ? (b ? 1 : 2) : 3
fun g(a: Bool, b: Bool): Int => a ? 1 : b ? 2 : 3
"""),

    # A wrapped operator run: each operator leads its line, four in.
    "operator_runs": ("""\
namespace Fmt

import System

fun anyOf(first: Bool, second: Bool, third: Bool): Bool => first
fun check(alphaCondition: Bool, betaCondition: Bool, gammaCondition: Bool, deltaCondition: Bool): Bool
  ret anyOf(alphaCondition, betaCondition, gammaCondition) || anyOf(betaCondition, gammaCondition, deltaCondition) || deltaCondition
""",
"""\
namespace Fmt

import System

fun anyOf(first: Bool, second: Bool, third: Bool): Bool => first
fun check(alphaCondition: Bool, betaCondition: Bool, gammaCondition: Bool, deltaCondition: Bool): Bool =>
    anyOf(alphaCondition, betaCondition, gammaCondition)
    || anyOf(betaCondition, gammaCondition, deltaCondition)
    || deltaCondition
"""),

    # Literals keep their spelling.
    "literals": ("""\
namespace Fmt

import System

let [const] MASK: Int = 0x1F
let [const] BIG: Int = 1_000_000
let [const] BYTE: Int8 = 7i8
let [const] LETTER: Int32 = 'a'
let [const] HALF: Float = 0.50
""",
"""\
namespace Fmt

import System

let [const] MASK: Int = 0x1F
let [const] BIG: Int = 1_000_000
let [const] BYTE: Int8 = 7i8
let [const] LETTER: Int32 = 'a'
let [const] HALF: Float = 0.50
"""),

    # Three or more nested one-argument calls become a pipeline; two stay calls.
    "repipe": ("""\
namespace Fmt

import System

fun inc(a: Int): Int => a + 1
fun dbl(a: Int): Int => a * 2
fun two(a: Int): Int => dbl(inc(a))
fun three(a: Int): Int => dbl(inc(dbl(a)))
""",
"""\
namespace Fmt

import System

fun inc(a: Int): Int => a + 1
fun dbl(a: Int): Int => a * 2
fun two(a: Int): Int => dbl(inc(a))
fun three(a: Int): Int => a |> dbl |> inc |> dbl
"""),

    # `a & ~b` survives the parser's `&~`.
    "andnot": ("""\
namespace Fmt

import System

fun clear(a: Int, b: Int): Int => a & ~b
""",
"""\
namespace Fmt

import System

fun clear(a: Int, b: Int): Int => a & ~b
"""),

    # `typealias Name: Type`, colon tight like every other.
    "typealias": ("""\
namespace Fmt

import System

typealias Count : Int
""",
"""\
namespace Fmt

import System

typealias Count: Int
"""),

}


class TestBootstrapFormat(TimedTestCase):
    _TIMEOUT = 600   # the round trip formats ~160 files, three runs each

    @classmethod
    def setUpClass(cls):
        cls.binary = shared_bootstrap_binary()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="yafl-format-")
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.binary, *args], capture_output=True, text=True, timeout=60, env=_RUN_ENV)

    def _dump(self, src: str) -> str:
        r = subprocess.run([self.binary, "--stage", "ast"], input=src, capture_output=True, text=True,
                           timeout=60, env=_RUN_ENV)
        self.assertEqual(0, r.returncode, r.stderr)
        return r.stdout

    def _format(self, name: str, src: str) -> str:
        path = self.dir / name
        path.write_text(src)
        r = self._run("--format", str(path))
        self.assertEqual((0, "", ""), (r.returncode, r.stdout, r.stderr), f"{name}: --format")
        return path.read_text()

    # ── the rules ───────────────────────────────────────────────────────────

    def test_rules(self):
        for name, (src, expected) in _RULES.items():
            with self.subTest(rule=name):
                self.assertEqual(expected, self._format(name + ".yafl", src))
                # The layout is a fixed point: formatted text formats to itself.
                self.assertEqual(expected, self._format(name + "_again.yafl", expected))

    # ── the command line ────────────────────────────────────────────────────

    def test_check_lists_what_is_not_formatted(self):
        src, expected = _RULES["ret_only"]
        bad, good = self.dir / "bad.yafl", self.dir / "good.yafl"
        bad.write_text(src)
        good.write_text(expected)
        r = self._run("--format-check", str(bad), str(good))
        self.assertEqual((1, f"{bad}\n", ""), (r.returncode, r.stdout, r.stderr))
        self.assertEqual(src, bad.read_text(), "--format-check rewrites nothing")
        r = self._run("--format-check", str(good))
        self.assertEqual((0, "", ""), (r.returncode, r.stdout, r.stderr))

    def test_a_directory_means_every_yafl_file_under_it(self):
        src, expected = _RULES["ret_only"]
        (self.dir / "sub").mkdir()
        for p in (self.dir / "a.yafl", self.dir / "sub" / "b.yafl", self.dir / "c.txt"):
            p.write_text(src)
        r = self._run("--format", str(self.dir))
        self.assertEqual((0, "", ""), (r.returncode, r.stdout, r.stderr))
        self.assertEqual(expected, (self.dir / "a.yafl").read_text())
        self.assertEqual(expected, (self.dir / "sub" / "b.yafl").read_text())
        self.assertEqual(src, (self.dir / "c.txt").read_text(), "only .yafl files are formatted")

    def test_a_file_that_does_not_parse_is_reported_and_left_alone(self):
        broken = "namespace Fmt\n\nfun f(: Int\n"
        path, other = self.dir / "broken.yafl", self.dir / "other.yafl"
        path.write_text(broken)
        other.write_text(_RULES["ret_only"][0])
        r = self._run("--format", str(path), str(other))
        self.assertEqual(1, r.returncode)
        self.assertEqual("", r.stdout)
        self.assertIn(f"{path}[", r.stderr)
        self.assertEqual(broken, path.read_text())
        self.assertEqual(_RULES["ret_only"][1], other.read_text(), "the other files are still formatted")

    def test_help_lists_the_formatter_options(self):
        r = self._run("-h")
        self.assertEqual(0, r.returncode)
        for option in ("--format", "--format-check"):
            self.assertIn(option, r.stdout)

    # ── the round trip ──────────────────────────────────────────────────────

    def test_round_trip_over_the_repository(self):
        self.assertGreater(len(_CORPUS), 100, "corpus went missing?")
        for path in _CORPUS:
            rel = path.relative_to(_REPO)
            with self.subTest(file=str(rel)):
                src = path.read_text()
                out = self._format(str(rel).replace("/", "_"), src)
                self.assertEqual(_comments(src), _comments(out), "every comment kept, in order")
                self.assertEqual(_tree(self._dump(src)), _tree(self._dump(out)), "the same tree")
                r = self._run("--format-check", str(self.dir / str(rel).replace("/", "_")))
                self.assertEqual(0, r.returncode, "a second format changes nothing")
