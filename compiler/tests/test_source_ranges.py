"""Source positions carry the length of the token they mark (#140).

A LineRef is a file, a line, the 1-based column a token starts at, and the
token's length in characters. Every real position has length >= 1; the only
exceptions are positions the compiler invents (LineRef.synthetic / invented),
which mark no source text and have length 0.
"""
import dataclasses
from pathlib import Path

from tests.testutil import TimedTestCase as TestCase

import parsing.parser as p
import pyast.expression as e
from parsing.tokenizer import tokenize, LineRef, TokenKind


def _refs(node, seen=None):
    """Every (LineRef, owner) reachable from a parse result."""
    seen = set() if seen is None else seen
    if id(node) in seen:
        return
    if isinstance(node, LineRef):
        yield node, None
        return
    if isinstance(node, (list, tuple, frozenset, set)):
        for x in node:
            yield from _refs(x, seen)
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _refs(k, seen)
            yield from _refs(v, seen)
    elif dataclasses.is_dataclass(node) and not isinstance(node, type):
        seen.add(id(node))
        for f in dataclasses.fields(node):
            v = getattr(node, f.name)
            if isinstance(v, LineRef):
                yield v, node
            else:
                yield from _refs(v, seen)


class TestTokenLengths(TestCase):
    def test_a_token_is_as_long_as_its_text(self):
        for tok in tokenize("fun f(x: Int): Int => x + 12\n", "f")[:-1]:
            self.assertEqual(len(tok.value), tok.line_ref.length, tok.value)

    def test_columns_and_lengths_are_in_characters_not_bytes(self):
        toks = tokenize('let héllo = "añb" + "😀"', "f")
        by_text = {t.value: t.line_ref for t in toks}
        self.assertEqual(5, by_text["héllo"].length)
        self.assertEqual(5, by_text['"añb"'].length)
        self.assertEqual(3, by_text['"😀"'].length)
        # `"😀"` starts at character column 21 whatever the bytes before it.
        self.assertEqual(21, by_text['"😀"'].offset)

    def test_a_backtick_name_counts_its_backticks(self):
        tok = tokenize("fun `+`(a: Int)", "f")[1]
        self.assertEqual("`+`", tok.value)
        self.assertEqual(3, tok.line_ref.length)

    def test_end_of_file_is_one_wide_just_past_the_last_token(self):
        toks = tokenize("let x", "f")
        eof = toks[-1]
        self.assertEqual(TokenKind.EOF, eof.kind)
        self.assertEqual((1, 6, 1), (eof.line_ref.line, eof.line_ref.offset, eof.line_ref.length))
        self.assertEqual(1, tokenize("", "f")[-1].line_ref.length)

    def test_the_length_takes_part_in_equality_but_not_in_the_name_hash(self):
        a, b = LineRef("f", 1, 1, 3), LineRef("f", 1, 1, 4)
        self.assertNotEqual(a, b)
        self.assertEqual(a.hash6(), b.hash6())

    def test_only_invented_positions_have_no_length(self):
        self.assertEqual(0, LineRef.synthetic("$x", 1, 1).length)
        self.assertEqual(0, LineRef("f", 2, 3, 5).invented().length)
        self.assertEqual((2, 3), (LineRef("f", 2, 3, 5).invented().line, LineRef("f", 2, 3, 5).invented().offset))


class TestParsedLengths(TestCase):
    def _find(self, source, kind, pred=lambda n: True):
        stmts = p.parse(tokenize(source, "f")).value
        return [o for _, o in _refs(stmts) if o is not None and isinstance(o, kind) and pred(o)]

    def test_a_qualified_name_spans_every_token_of_the_path(self):
        found = self._find("fun g(): Int => System::length(s)\n", e.NamedExpression,
                           lambda n: n.name == "System::length")
        self.assertEqual(1, len(found))
        ref = found[0].line_ref
        self.assertEqual((1, 17, 14), (ref.line, ref.offset, ref.length))

    def test_a_plain_name_is_its_token(self):
        found = self._find("fun g(): Int => other(1)\n", e.NamedExpression, lambda n: n.name == "other")
        self.assertEqual((17, 5), (found[0].line_ref.offset, found[0].line_ref.length))

    def test_a_member_after_a_dot_is_the_member_token(self):
        found = self._find("fun g(): Int => a.member\n", e.DotExpression)
        self.assertEqual("member", found[0].name)
        self.assertEqual((19, 6), (found[0].line_ref.offset, found[0].line_ref.length))

    def test_literals_are_as_long_as_they_are_written(self):
        for text, kind in (("0x1F", e.IntegerExpression), ('"a\\nb"', e.StringExpression)):
            found = self._find(f"fun g(): Int => {text}\n", kind)
            self.assertEqual(len(text), found[0].line_ref.length, text)

    def test_an_interpolation_slot_spans_its_braces_and_the_show_it_calls_is_invented(self):
        # `{x, 3}` starts at column 23 and is six characters. The slot becomes
        # a call to `show`: the call is the slot, the name `show` is made up.
        source = 'fun g(): String => $"a{x, 3}b"\n'
        calls = self._find(source, e.CallExpression, lambda n: isinstance(n.function, e.NamedExpression)
                                                             and n.function.name == "show")
        self.assertEqual(1, len(calls))
        self.assertEqual((23, 6), (calls[0].line_ref.offset, calls[0].line_ref.length))
        shown = calls[0].function.line_ref
        self.assertEqual((23, 0), (shown.offset, shown.length))
        # The expression inside keeps its own token: `x` is column 24, one wide.
        inner = self._find(source, e.NamedExpression, lambda n: n.name == "x")
        self.assertEqual((24, 1), (inner[0].line_ref.offset, inner[0].line_ref.length))


class TestEveryNodeInTheCorpus(TestCase):
    """Walk every node of every stdlib, example and test file: a position of
    real source has a length, and the few that do not are named here."""

    ROOT = Path(__file__).resolve().parents[2]

    def test_no_position_from_a_file_lacks_a_length_but_the_invented(self):
        files = [f for d in ("compiler/stdlib", "examples", "compiler/stdlib_tests", "compiler/yafl_tests")
                 for f in sorted((self.ROOT / d).rglob("*.yafl"))]
        self.assertGreater(len(files), 50)
        bad: list[str] = []
        for path in files:
            result = p.parse(tokenize(path.read_text(), str(path)))
            self.assertFalse(result.errors, str(path))
            for ref, owner in _refs(result.value):
                if ref.length == 0 and ref.filename == str(path):
                    kind = type(owner).__name__ if owner is not None else "?"
                    name = getattr(owner, "name", "")
                    if not (kind == "NamedExpression" and name == "show"):
                        bad.append(f"{path.name}[{ref.line}:{ref.offset}] {kind} {name}")
        self.assertEqual([], bad[:20])


class TestParityOfInventedNames(TestCase):
    """The port makes up the same positions as Python: its AST dump of a
    program that interpolates, qualifies names and spreads a type over `>>`
    equals Python's, node for node, lengths included. The corpus tests cover
    the files in the repository; this covers what they do not write."""

    SOURCE = ('namespace Main\nimport System\nimport System::Containers\n'
              'fun f(n: Int): String => $"a{n}b{n, 3}c"\n'
              'fun g(a: Int): Int => System::length("x") + a\n'
              'fun h(xs: List<List<Int>>, ys: System::Containers::List<Int>): Int => 0\n'
              'fun `+`(a: List<Int>, b: List<Int>): List<Int> => a\n'
              'fun k(p: Int): Int => p |> (v) => v + 1\n')

    def test_the_dump_of_the_port_matches_python(self):
        import subprocess
        from tests.astdump import dump
        from tests.testutil import shared_bootstrap_binary, _RUN_ENV
        python = dump(p.parse(tokenize(self.SOURCE, "x")).value)
        r = subprocess.run([shared_bootstrap_binary(), "--stage", "ast"], input=self.SOURCE,
                           capture_output=True, text=True, timeout=120, env=_RUN_ENV)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(python.splitlines(), r.stdout.splitlines())


class TestInventedNamesStillFilterTheirCascade(TestCase):
    """The `show` an interpolation makes is a name with no length, beginning
    where the slot does. The rule "when the argument has errors, the call's own
    complaint is noise" must still see it as the call's own."""

    SOURCE = ('namespace Main\nimport System\nfun main(): Int\n'
              '  System::println($"a {nope} b")\n  ret 0\n')

    def test_an_unresolved_slot_is_reported_alone_by_both_compilers(self):
        from tests.testutil import compile_c_result, python_compiler_command, port_compiler_command
        for command in (python_compiler_command(), port_compiler_command()):
            out = compile_c_result(self.SOURCE, "t.yafl", command=command).stdout
            self.assertIn("Failed to resolve nope", out, command)
            self.assertNotIn("show", out, command)

    def test_the_end_of_a_block_is_one_character_wide(self):
        # `let x =` then a line that ends the block: the error is about the
        # place the value should have been, not about the next line's token.
        parsed = p.parse(tokenize("fun f(): Int\n  let x =\nfun gggg(): Int => 1\n", "x"))
        lengths = {err.line_ref.length for err in parsed.errors}
        self.assertEqual({1}, lengths, parsed.errors)
