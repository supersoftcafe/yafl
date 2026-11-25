"""`yaflc --lsp`, the language server (#26), driven the way an editor drives it:
framed JSON-RPC messages on stdin, replies read back from stdout.

The server exists only in the port, so these tests always run the port
binary, whichever compiler the suite is testing.
"""
from __future__ import annotations

import json
import subprocess

from tests.testutil import TimedTestCase as TestCase
from tests.testutil import shared_bootstrap_binary


def _frame(message: dict, extra_headers: bytes = b"") -> bytes:
    body = json.dumps(message, ensure_ascii=False).encode()
    return b"Content-Length: %d\r\n" % len(body) + extra_headers + b"\r\n" + body


def _request(id_, method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


def _notification(method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "method": method, "params": params or {}}


def _replies(out: bytes) -> list[dict]:
    replies = []
    while out:
        head, _, rest = out.partition(b"\r\n\r\n")
        length = int(head.split(b":")[1])
        replies.append(json.loads(rest[:length]))
        out = rest[length:]
    return replies


def _ask(p: subprocess.Popen, message: dict) -> dict:
    """Send one request to a running server and read its reply."""
    p.stdin.write(_frame(message))
    p.stdin.flush()
    head = b""
    while not head.endswith(b"\r\n\r\n"):
        head += p.stdout.read(1)
    return json.loads(p.stdout.read(int(head.split(b":")[1])))


def _serve(stream: bytes, timeout: int = 60, env: dict | None = None) -> subprocess.CompletedProcess:
    """One session of the server on `stream`, run to its end."""
    return subprocess.run([shared_bootstrap_binary(), "--lsp"], input=stream,
                          capture_output=True, timeout=timeout, env=env)


class _Workspace(TestCase):
    """A workspace folder of its own for each test, and a session over it:
    initialised on the folder, `messages`, then shut down."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name).resolve() / "work"
        self.root.mkdir()

    def tearDown(self):
        self._dir.cleanup()

    def _write(self, unit: str, text: str) -> None:
        path = self.root / unit
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def _uri(self, unit: str) -> str:
        return (self.root / unit).as_uri()

    def _replies(self, *messages: dict, env: dict | None = None) -> list[dict]:
        stream = [_request(1, "initialize", {"rootUri": self.root.as_uri(), "capabilities": {}}),
                  _notification("initialized"), *messages,
                  _request(99, "shutdown"), _notification("exit")]
        p = _serve(b"".join(_frame(m) for m in stream), timeout=300, env=env)
        self.assertEqual(0, p.returncode, p.stderr)
        return _replies(p.stdout)


_INITIALIZE = _request(1, "initialize", {"processId": None, "rootUri": None, "capabilities": {}})


class TestLifecycle(TestCase):

    def _session(self, *messages: dict) -> tuple[int, list[dict]]:
        p = _serve(b"".join(_frame(m) for m in messages))
        return p.returncode, _replies(p.stdout)

    def test_a_session_ends_cleanly(self):
        code, replies = self._session(_INITIALIZE, _notification("initialized"),
                                      _request(2, "shutdown"), _notification("exit"))
        self.assertEqual(0, code)
        self.assertEqual([1, 2], [r["id"] for r in replies])
        self.assertEqual("utf-16", replies[0]["result"]["capabilities"]["positionEncoding"])
        self.assertIsNone(replies[1]["result"])

    def test_requests_before_initialize_are_refused(self):
        code, replies = self._session(_request(7, "textDocument/hover"), _INITIALIZE,
                                      _request(2, "shutdown"), _notification("exit"))
        self.assertEqual(0, code)
        self.assertEqual(-32002, replies[0]["error"]["code"])
        self.assertEqual(7, replies[0]["id"])

    def test_after_shutdown_only_exit_is_accepted(self):
        code, replies = self._session(_INITIALIZE, _request(2, "shutdown"),
                                      _request(3, "textDocument/hover"), _notification("exit"))
        self.assertEqual(0, code)
        self.assertEqual(-32600, replies[2]["error"]["code"])

    def test_exit_without_shutdown_fails(self):
        code, _ = self._session(_INITIALIZE, _notification("exit"))
        self.assertEqual(1, code)

    def test_a_closed_stream_ends_the_session(self):
        code, replies = self._session(_INITIALIZE)
        self.assertEqual(1, code)
        self.assertEqual([1], [r["id"] for r in replies])

    def test_a_reply_arrives_while_the_input_stays_open(self):
        # An editor waits for each reply before it sends more.
        import select
        p = subprocess.Popen([shared_bootstrap_binary(), "--lsp"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with p:
            try:
                p.stdin.write(_frame(_INITIALIZE))
                p.stdin.flush()
                ready, _, _ = select.select([p.stdout], [], [], 30)
                self.assertTrue(ready, "no reply while the input is open")
            finally:
                p.kill()

    def test_unknown_methods(self):
        # A request gets an error; a notification is ignored.
        code, replies = self._session(_INITIALIZE, _notification("$/unknown"),
                                      _request("a", "nonsense"), _request(2, "shutdown"),
                                      _notification("exit"))
        self.assertEqual(0, code)
        self.assertEqual(["a", 2], [r["id"] for r in replies[1:]])
        self.assertEqual(-32601, replies[1]["error"]["code"])


class TestFraming(TestCase):

    def _serve(self, stream: bytes) -> tuple[int, list[dict]]:
        p = _serve(stream)
        return p.returncode, _replies(p.stdout)

    def test_content_length_counts_bytes(self):
        # Two- and four-byte characters, and a control character the JSON
        # must escape, in both directions.
        method = "café \U0001F600 \u0001"
        code, replies = self._serve(_frame(_INITIALIZE) + _frame(_request(2, method))
                                    + _frame(_request(3, "shutdown")) + _frame(_notification("exit")))
        self.assertEqual(0, code)
        self.assertEqual("unknown method: " + method, replies[1]["error"]["message"])

    def test_other_headers_are_ignored(self):
        code, replies = self._serve(
            _frame(_INITIALIZE, b"Content-Type: application/vscode-jsonrpc; charset=utf-8\r\n")
            + _frame(_request(2, "shutdown")) + _frame(_notification("exit")))
        self.assertEqual(0, code)
        self.assertEqual([1, 2], [r["id"] for r in replies])

    def test_a_header_name_is_not_case_sensitive(self):
        body = json.dumps(_request(2, "shutdown")).encode()
        code, replies = self._serve(_frame(_INITIALIZE)
                                    + b"content-length: %d\r\n\r\n" % len(body) + body
                                    + _frame(_notification("exit")))
        self.assertEqual(0, code)
        self.assertEqual([1, 2], [r["id"] for r in replies])

    def test_a_body_that_is_not_json_gets_a_parse_error(self):
        body = b"{not json"
        code, replies = self._serve(_frame(_INITIALIZE)
                                    + b"Content-Length: %d\r\n\r\n" % len(body) + body
                                    + _frame(_request(2, "shutdown")) + _frame(_notification("exit")))
        self.assertEqual(0, code)
        self.assertEqual(-32700, replies[1]["error"]["code"])
        self.assertIsNone(replies[1]["id"])

    def test_a_stream_that_breaks_inside_a_message_fails(self):
        whole = _frame(_request(2, "shutdown"))
        code, replies = self._serve(_frame(_INITIALIZE) + whole[:-3])
        self.assertEqual(1, code)
        self.assertEqual([1], [r["id"] for r in replies])


class TestDiagnostics(_Workspace):
    """Pull diagnostics over a workspace folder: files on disk, documents the
    editor has open, and the libraries beneath them."""

    def _session(self, *messages: dict, env: dict | None = None) -> dict:
        """Each diagnostic reply's items, by request id."""
        return {r["id"]: r["result"]["items"] for r in self._replies(*messages, env=env)
                if isinstance(r.get("result"), dict) and "items" in r["result"]}

    def _pull(self, id_, unit: str) -> dict:
        return _request(id_, "textDocument/diagnostic", {"textDocument": {"uri": self._uri(unit)}})

    def _open(self, unit: str, text: str, version: int = 1) -> dict:
        return _notification("textDocument/didOpen", {"textDocument": {
            "uri": self._uri(unit), "languageId": "yafl", "version": version, "text": text}})

    def _change(self, unit: str, text: str, version: int) -> dict:
        return _notification("textDocument/didChange", {
            "textDocument": {"uri": self._uri(unit), "version": version},
            "contentChanges": [{"text": text}]})

    _CLEAN = "namespace Main\nimport System\nfun main(): Int\n  ret 0\n"

    @staticmethod
    def _summary(items: list[dict]) -> list[tuple]:
        return [(i["range"]["start"]["line"], i["range"]["start"]["character"],
                 i["severity"], i["message"]) for i in items]

    def test_a_file_on_disk_is_analysed(self):
        self._write("main.yafl", "namespace Main\nimport System\nfun main(): Int\n  ret nosuch\n")
        items = self._session(self._pull(2, "main.yafl"))[2]
        self.assertIn((3, 6, 1, "Failed to resolve nosuch"), self._summary(items))

    def test_an_open_document_replaces_the_disk(self):
        self._write("main.yafl", self._CLEAN)
        items = self._session(self._pull(2, "main.yafl"),
                              self._open("main.yafl", "namespace Main\nimport System\nfun main(): Int\n  ret nosuch\n"),
                              self._pull(3, "main.yafl"),
                              _notification("textDocument/didClose", {"textDocument": {"uri": self._uri("main.yafl")}}),
                              self._pull(4, "main.yafl"))
        self.assertEqual([], items[2])
        self.assertIn("Failed to resolve nosuch", [m for *_, m in self._summary(items[3])])
        self.assertEqual([], items[4])

    def test_columns_are_utf16_units(self):
        # `nosuch` is the 21st character of its line. The compiler counts the
        # emoji before it as one column; the client counts it as two units.
        self._write("main.yafl", "namespace Main\nimport System\nfun main(): Int\n"
                                 "  ret length(\"\U0001F600\") + nosuch\n")
        items = self._session(self._pull(2, "main.yafl"))[2]
        self.assertIn((3, 21, 1, "Failed to resolve nosuch"), self._summary(items))

    def test_warnings_are_warnings(self):
        self._write("main.yafl", "namespace Main\nimport System\nfun main(): Int\n  let unused = 1\n  ret 0\n")
        items = self._session(self._pull(2, "main.yafl"))[2]
        self.assertEqual([(3, 6, 2, "'unused' is never used")], self._summary(items))

    def test_a_document_that_does_not_parse_gets_its_parse_errors(self):
        self._write("main.yafl", self._CLEAN)
        items = self._session(self._change("main.yafl", "", 1),
                              self._open("main.yafl", self._CLEAN),
                              self._change("main.yafl", "namespace Main\nfun main(: Int\n", 2),
                              self._pull(2, "main.yafl"))[2]
        self.assertEqual(1, len(items))
        self.assertEqual(1, items[0]["severity"])
        self.assertEqual(1, items[0]["range"]["start"]["line"])

    @staticmethod
    def _covered(items: list[dict], text: str) -> list[tuple]:
        """(message, the text each diagnostic's range covers) for single-line ranges."""
        lines = text.split("\n")
        out = []
        for i in items:
            start, end = i["range"]["start"], i["range"]["end"]
            if start["line"] == end["line"]:
                out.append((i["message"], lines[start["line"]][start["character"]:end["character"]]))
        return out

    def test_a_diagnostic_covers_the_token_it_points_at(self):
        text = "namespace Main\nimport System\nfun main(): Int\n  ret nosuch\n"
        self._write("main.yafl", text)
        items = self._session(self._pull(2, "main.yafl"))[2]
        self.assertIn(("Failed to resolve nosuch", "nosuch"), self._covered(items, text))

    def test_a_qualified_name_is_covered_whole(self):
        text = "namespace Main\nimport System\nfun main(): Int\n  ret System::nosuch(1)\n"
        self._write("main.yafl", text)
        items = self._session(self._pull(2, "main.yafl"))[2]
        self.assertTrue([c for m, c in self._covered(items, text) if c == "System::nosuch"], items)

    def test_a_warning_covers_the_name(self):
        text = "namespace Main\nimport System\nfun main(): Int\n  let unused = 1\n  ret 0\n"
        self._write("main.yafl", text)
        items = self._session(self._pull(2, "main.yafl"))[2]
        self.assertEqual([("'unused' is never used", "unused")], self._covered(items, text))

    def test_a_range_ends_in_utf16_units(self):
        # The emoji is two units to the client: `nosuch` starts at unit 21 and
        # its six characters end at 27.
        text = "namespace Main\nimport System\nfun main(): Int\n  ret length(\"\U0001F600\") + nosuch\n"
        self._write("main.yafl", text)
        items = self._session(self._pull(2, "main.yafl"))[2]
        ranges = [(i["range"]["start"]["character"], i["range"]["end"]["character"])
                  for i in items if i["message"] == "Failed to resolve nosuch"]
        self.assertEqual([(21, 27)], ranges)

    def test_a_parse_error_covers_the_token_it_stopped_at(self):
        text = "namespace Main\nfun main(: Int\n"
        self._write("main.yafl", text)
        items = self._session(self._pull(2, "main.yafl"))[2]
        self.assertEqual(1, len(items))
        start, end = items[0]["range"]["start"], items[0]["range"]["end"]
        self.assertEqual(start["line"], end["line"])
        self.assertGreater(end["character"], start["character"], items)

    def test_a_name_the_compiler_made_up_is_a_point(self):
        # `$"..."` calls `show`; an error in the call is at the string, which is
        # real, but the made-up name itself has no length. An unresolved `show`
        # reports the slot, whose range is the braces.
        text = ("namespace Main\nimport System\nclass V(x: Int)\n"
                "fun main(): Int\n  let v = V(1)\n  ret length($\"a{v}b\")\n")
        self._write("main.yafl", text)
        items = self._session(self._pull(2, "main.yafl"))[2]
        covered = [c for m, c in self._covered(items, text)]
        self.assertIn("{v}", covered, items)

    def test_an_edit_in_one_file_changes_another(self):
        self._write("main.yafl", "namespace Main\nimport System\nfun main(): Int\n  ret helper()\n")
        self._write("lib/helper.yafl", "namespace Main\nimport System\nfun helper(): Int\n  ret 0\n")
        items = self._session(self._pull(2, "main.yafl"),
                              self._open("lib/helper.yafl", "namespace Main\nimport System\nfun other(): Int\n  ret 0\n"),
                              self._pull(3, "main.yafl"))
        self.assertEqual([], items[2])
        self.assertIn("Failed to resolve helper", " ".join(m for *_, m in self._summary(items[3])))

    def test_every_folder_in_the_workspace_is_the_program(self):
        # As `yaflc <folder>` compiles it: a nested folder is part of the
        # program, whatever else it holds.
        self._write("main.yafl", self._CLEAN)
        self._write("sub/yafl.toml", 'name = "sub"\nnamespaces = ["Sub"]\n')
        self._write("sub/broken.yafl", "namespace Main\nfun broken(: Int\n")
        items = self._session(self._pull(2, "sub/broken.yafl"))[2]
        self.assertEqual(1, len(items))
        self.assertEqual(1, items[0]["range"]["start"]["line"])

    def test_a_library_that_cannot_load_says_where(self):
        # Shown in every document, since the library's file is not one the
        # editor has; each error with its file and position.
        import os
        libs = self.root.parent / "libs"
        (libs / "broken").mkdir(parents=True)
        (libs / "broken" / "yafl.toml").write_text('name = "broken"\nnamespaces = ["Broken"]\n')
        (libs / "broken" / "broken.yafl").write_text("namespace Broken\nfun broken(: Int\n")
        self._write("main.yafl", self._CLEAN)
        items = self._session(self._pull(2, "main.yafl"), env=dict(os.environ, YAFL_PATH=str(libs)))[2]
        self.assertEqual(1, len(items))
        self.assertIn("does not parse", items[0]["message"])
        self.assertIn("broken.yafl[2:", items[0]["message"])

    def test_a_document_outside_the_workspace_has_none(self):
        self._write("main.yafl", "namespace Main\nimport System\nfun main(): Int\n  ret nosuch\n")
        items = self._session(_request(2, "textDocument/diagnostic",
                                       {"textDocument": {"uri": "file:///elsewhere/x.yafl"}}))[2]
        self.assertEqual([], items)


class TestNavigation(_Workspace):
    """Go to definition and find references, over a workspace folder and the
    libraries beneath it."""

    def _session(self, *messages: dict) -> dict:
        """Each reply's result, by request id."""
        return {r["id"]: r.get("result") for r in self._replies(*messages)}

    def _at(self, id_, method: str, unit: str, line: int, character: int, **extra) -> dict:
        return _request(id_, method, {"textDocument": {"uri": self._uri(unit)},
                                      "position": {"line": line, "character": character}, **extra})

    @staticmethod
    def _text(location: dict) -> str:
        """The text a single-line location covers."""
        from urllib.parse import unquote, urlparse
        start, end = location["range"]["start"], location["range"]["end"]
        assert start["line"] == end["line"]
        with open(unquote(urlparse(location["uri"]).path), encoding="utf-8") as f:
            line = f.read().split("\n")[start["line"]]
        return line[start["character"]:end["character"]]

    def _where(self, location: dict) -> tuple:
        return (location["uri"], location["range"]["start"]["line"], self._text(location))

    _MAIN = ("namespace Main\nimport System\n"
             "class Point(x: Int, y: Int)\n"
             "fun area(p: Point): Int\n"
             "  let w = p.x\n"
             "  ret w * p.y + helper()\n"
             "fun main(): Int\n"
             "  ret area(Point(1, 2)) + length(\"ab\") + helper()\n")
    _HELPER = "namespace Main\nimport System\n\nfun helper(): Int\n  ret 0\n"

    def test_definitions(self):
        self._write("main.yafl", self._MAIN)
        self._write("lib/helper.yafl", self._HELPER)
        main, helper = self._uri("main.yafl"), self._uri("lib/helper.yafl")
        got = self._session(
            self._at(2, "textDocument/definition", "main.yafl", 5, 18),   # helper, in another file
            self._at(3, "textDocument/definition", "main.yafl", 5, 6),    # w, a local
            self._at(4, "textDocument/definition", "main.yafl", 4, 10),   # p, a parameter
            self._at(5, "textDocument/definition", "main.yafl", 4, 12),   # x, a field
            self._at(6, "textDocument/definition", "main.yafl", 3, 14),   # Point, a type
            self._at(7, "textDocument/definition", "main.yafl", 7, 9),    # area, a function
            self._at(8, "textDocument/definition", "main.yafl", 1, 0))    # import: nothing
        self.assertEqual((helper, 3, "helper"), self._where(got[2]))
        self.assertEqual((main, 4, "w"), self._where(got[3]))
        self.assertEqual((main, 3, "p"), self._where(got[4]))
        self.assertEqual((main, 2, "x"), self._where(got[5]))
        self.assertEqual((main, 2, "Point"), self._where(got[6]))
        self.assertEqual((main, 3, "area"), self._where(got[7]))
        self.assertIsNone(got[8])

    def test_a_definition_in_a_library(self):
        self._write("main.yafl", self._MAIN)
        self._write("lib/helper.yafl", self._HELPER)
        got = self._session(self._at(2, "textDocument/definition", "main.yafl", 7, 28))
        self.assertIn("/compiler/stdlib/System/", got[2]["uri"])
        self.assertEqual("length", self._text(got[2]))

    def test_definitions_of_types_and_arm_names(self):
        # A type alias and an enum resolve to what they name, which is
        # declared elsewhere: the name as written is what leads there.
        self._write("main.yafl", "namespace Main\nimport System\nimport System::IO\n"
                                 "fun describe(v: String|IOError): Int\n"
                                 "  ret match(v)\n"
                                 "    (s: String)  => length(s)\n"
                                 "    (e: IOError) => e.code\n")
        got = self._session(
            self._at(2, "textDocument/definition", "main.yafl", 3, 16),   # String, an alias
            self._at(3, "textDocument/definition", "main.yafl", 3, 23),   # IOError, an enum
            self._at(4, "textDocument/definition", "main.yafl", 6, 20),   # e, an arm's name
            self._at(5, "textDocument/definition", "main.yafl", 6, 8))    # IOError in an arm
        self.assertEqual("String", self._text(got[2]))
        self.assertEqual("IOError", self._text(got[3]))
        self.assertIn("/compiler/stdlib/System/", got[3]["uri"])
        self.assertEqual((self._uri("main.yafl"), 6, "e"), self._where(got[4]))
        self.assertEqual("IOError", self._text(got[5]))

    def test_operators(self):
        # An operator leads to the function it calls, from where it is
        # written: each `+` of a chain is a use of its own.
        self._write("main.yafl", "namespace Main\nimport System\n"
                                 "class V(x: Int)\n"
                                 "fun `+`(a: V, b: V): V\n  ret V(a.x + b.x)\n"
                                 "fun `-`(a: V): V\n  ret V(0 - a.x)\n"
                                 "fun sum(p: V, q: V, r: V): V\n  ret p + q + -r\n"
                                 "fun big(n: Int): Bool\n  ret n > 0\n")
        main = self._uri("main.yafl")
        got = self._session(
            self._at(2, "textDocument/definition", "main.yafl", 8, 12),   # the second `+`
            self._at(3, "textDocument/definition", "main.yafl", 8, 14),   # unary `-`
            self._at(4, "textDocument/definition", "main.yafl", 10, 8),   # `>` on Int, in System
            self._at(5, "textDocument/references", "main.yafl", 8, 8,
                     context={"includeDeclaration": False}))
        self.assertEqual((main, 3, "+"), self._where(got[2]))
        self.assertEqual((main, 5, "-"), self._where(got[3]))
        self.assertEqual(">", self._text(got[4]))
        self.assertIn("/compiler/stdlib/System/", got[4]["uri"])
        self.assertEqual([(8, 8), (8, 12)],
                         sorted((x["range"]["start"]["line"], x["range"]["start"]["character"]) for x in got[5]))

    def test_references(self):
        self._write("main.yafl", self._MAIN)
        self._write("lib/helper.yafl", self._HELPER)
        main, helper = self._uri("main.yafl"), self._uri("lib/helper.yafl")
        got = self._session(
            self._at(2, "textDocument/references", "lib/helper.yafl", 3, 5,
                     context={"includeDeclaration": True}),
            self._at(3, "textDocument/references", "main.yafl", 5, 18,
                     context={"includeDeclaration": False}))
        self.assertEqual(sorted([(helper, 3, "helper"), (main, 5, "helper"), (main, 7, "helper")]),
                         sorted(self._where(x) for x in got[2]))
        self.assertEqual(sorted([(main, 5, "helper"), (main, 7, "helper")]),
                         sorted(self._where(x) for x in got[3]))

    def test_a_qualified_name_is_the_end_of_its_path(self):
        text = "namespace Main\nimport System\nfun main(): Int\n  ret System::length(\"ab\")\n"
        self._write("main.yafl", text)
        got = self._session(
            self._at(2, "textDocument/definition", "main.yafl", 3, 15),   # on `length`
            self._at(3, "textDocument/definition", "main.yafl", 3, 8),    # on `System`
            self._at(4, "textDocument/references", "main.yafl", 3, 15,
                     context={"includeDeclaration": False}))
        self.assertEqual("length", self._text(got[2]))
        self.assertIsNone(got[3])
        self.assertEqual([(3, 14, 3, 20)], [(x["range"]["start"]["line"], x["range"]["start"]["character"],
                                             x["range"]["end"]["line"], x["range"]["end"]["character"])
                                            for x in got[4]])

    def test_a_slot_of_an_interpolated_string_is_a_use_but_the_call_it_makes_is_not(self):
        text = ("namespace Main\nimport System\nfun main(): Int\n  let n = 5\n"
                "  ret length($\"a{n}b\")\n")
        self._write("main.yafl", text)
        got = self._session(
            self._at(2, "textDocument/definition", "main.yafl", 4, 17),   # `n` in the slot
            self._at(3, "textDocument/definition", "main.yafl", 4, 16),   # the `{`
            self._at(4, "textDocument/definition", "main.yafl", 4, 13),   # the `$`
            self._at(5, "textDocument/references", "main.yafl", 3, 6,
                     context={"includeDeclaration": True}))
        self.assertEqual((self._uri("main.yafl"), 3, "n"), self._where(got[2]))
        self.assertIsNone(got[3])
        self.assertIsNone(got[4])
        self.assertEqual([(3, 6), (4, 17)], sorted((x["range"]["start"]["line"], x["range"]["start"]["character"])
                                                   for x in got[5]))

    def test_names_are_found_by_characters_not_bytes(self):
        line = '  ret length("\U0001F600") + \u00e9'
        text = f'namespace Main\nimport System\nfun main(): Int\n  let \u00e9 = 1\n{line}\n'
        self._write("main.yafl", text)
        unit = len(line[:line.rindex("\u00e9")].encode("utf-16-le")) // 2
        got = self._session(
            self._at(2, "textDocument/definition", "main.yafl", 4, unit),
            self._at(3, "textDocument/references", "main.yafl", 3, 6,
                     context={"includeDeclaration": True}))
        self.assertEqual((self._uri("main.yafl"), 3, "\u00e9"), self._where(got[2]))
        self.assertEqual([(3, 6, 7), (4, unit, unit + 1)],
                         sorted((x["range"]["start"]["line"], x["range"]["start"]["character"],
                                 x["range"]["end"]["character"]) for x in got[3]))

    _RICH = (
        "namespace Main\n"
        "import System\n"
        "import System::Containers\n"
        "\n"
        "class Point(x: Int, y: Int)\n"
        "  fun norm(): Int\n"
        "    ret x * x + y * y\n"
        "\n"
        "enum Shape\n"
        "  enum Circle(radius: Int)\n"
        "  enum Square(side: Int)\n"
        "\n"
        "interface Named<T>\n"
        "  fun nameOf(value: T): String\n"
        "\n"
        "fun `+`(a: Point, b: Point): Point\n"
        "  ret Point(a.x + b.x, a.y + b.y)\n"
        "\n"
        "fun area(s: Shape): Int => match(s)\n"
        "  (c: Circle) => c.radius * c.radius * 3\n"
        "  (q: Square) => q.side * q.side\n"
        "\n"
        "fun twice<T>(f: (:T): T, v: T): T => f(f(v))\n"
        "\n"
        "fun total(ps: List<Point>): Int\n"
        "  let sum = fold(ps, 0, (acc, p) => acc + p.norm())\n"
        "  ret sum\n"
        "\n"
        "fun main(): Int\n"
        "  let p = Point(1, 2) + Point(3, 4)\n"
        "  let moved = with p(x = 9)\n"
        "  let n = twice((v: Int) => v + 1, p.x) |> (r) => r * 2\n"
        "  let label = $\"{n} and {moved.y}\"\n"
        "  let shape: Shape = Circle(n)\n"
        "  ret area(shape) + length(label) + System::length(\"ab\") + (n > 3 ? 1 : 0) + total(List(p))\n")

    def test_every_name_leads_to_itself(self):
        """The definition of any name in a program of every kind of use is the
        name itself, as written where it is declared: never a neighbour, never
        part of a word."""
        import re
        self._write("main.yafl", self._RICH)
        lines = self._RICH.split("\n")
        probes = []   # (id, line, character, word)
        for ln, text in enumerate(lines):
            for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9]*", text):
                probes.append((len(probes) + 2, ln, m.start(), m.group()))
        got = self._session(*[self._at(i, "textDocument/definition", "main.yafl", ln, ch)
                              for i, ln, ch, _ in probes])
        found = 0
        for i, ln, ch, word in probes:
            loc = got.get(i)
            if loc is None:
                continue
            found += 1
            self.assertEqual(word, self._text(loc), (ln, ch, word, loc))
        # Most words in the program are names.
        self.assertGreater(found, len(probes) // 2, (found, len(probes)))

    def test_every_reference_is_the_name(self):
        import re
        self._write("main.yafl", self._RICH)
        lines = self._RICH.split("\n")
        asks = [(10 + k, ln, m.start(), m.group())
                for k, (ln, m) in enumerate((ln, m) for ln, t in enumerate(lines)
                                            for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9]*", t))
                if m.group() in ("p", "n", "x", "area", "twice", "Point", "moved", "label", "acc", "sum")]
        got = self._session(*[self._at(i, "textDocument/references", "main.yafl", ln, ch,
                                       context={"includeDeclaration": True}) for i, ln, ch, _ in asks])
        for i, ln, ch, word in asks:
            locs = got[i]
            for loc in locs:
                self.assertEqual(word, self._text(loc), (ln, ch, word, loc))

    def test_the_server_says_it_navigates(self):
        got = self._session()
        caps = got[1]["capabilities"]
        self.assertTrue(caps["definitionProvider"])
        self.assertTrue(caps["referencesProvider"])


class TestPackagedLibraries(_Workspace):
    """A library installed as a `.yl` keeps its sources inside the zip; the
    server writes them out, under its own temp folder, for as long as it runs,
    so a definition in one can be opened."""

    def setUp(self):
        super().setUp()
        self.libs = self.root.parent / "libs"
        self.libs.mkdir()

    def _package(self) -> None:
        import zipfile
        with zipfile.ZipFile(self.libs / "zed.yl", "w") as z:
            z.writestr("yafl.toml", 'name = "zed"\nnamespaces = ["Zed"]\n')
            z.writestr("Zed/zed.yafl", "namespace Zed\nimport System\n\nfun zedValue(): Int\n  ret 7\n")

    def test_a_definition_in_a_packaged_library(self):
        import os
        from urllib.parse import unquote, urlparse
        self._package()
        (self.root / "main.yafl").write_text("namespace Main\nimport System\nimport Zed\n"
                                             "fun main(): Int\n  ret zedValue()\n")
        env = dict(os.environ, YAFL_PATH=str(self.libs))
        with subprocess.Popen([shared_bootstrap_binary(), "--lsp"], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) as p:
            try:
                _ask(p, _request(1, "initialize", {"rootUri": self.root.as_uri(), "capabilities": {}}))
                found = _ask(p, _request(2, "textDocument/definition", {
                    "textDocument": {"uri": (self.root / "main.yafl").as_uri()},
                    "position": {"line": 4, "character": 7}}))["result"]
                # Read while the server runs: its temp folder goes when it exits.
                path = unquote(urlparse(found["uri"]).path)
                self.assertTrue(path.endswith("/libs/zed/Zed/zed.yafl"), path)
                start, end = found["range"]["start"], found["range"]["end"]
                with open(path, encoding="utf-8") as f:
                    line = f.read().split("\n")[start["line"]]
                self.assertEqual("zedValue", line[start["character"]:end["character"]])
                _ask(p, _request(3, "shutdown"))
                p.stdin.write(_frame(_notification("exit")))
                p.stdin.close()
                self.assertEqual(0, p.wait(timeout=60))
            finally:
                if p.poll() is None:
                    p.kill()


class TestLibraryWorkspace(_Workspace):
    """A workspace folder holding a `yafl.toml` is a library, not a program:
    it is analysed as that library, in place of an installed library of the
    same name (#144), and what is built on it is left out."""

    def _pull(self, id_, unit: str) -> dict:
        return _request(id_, "textDocument/diagnostic", {"textDocument": {"uri": self._uri(unit)}})

    def _items(self, unit: str, env: dict | None = None) -> list[dict]:
        replies = self._replies(self._pull(2, unit), env=env)
        return next(r["result"]["items"] for r in replies if r.get("id") == 2)

    def _installed(self, name: str, namespace: str, source: str) -> dict:
        import os
        libs = self.root.parent / "libs"
        (libs / name).mkdir(parents=True, exist_ok=True)
        (libs / name / "yafl.toml").write_text(f'name = "{name}"\nnamespaces = ["{namespace}"]\n')
        (libs / name / f"{name}.yafl").write_text(source)
        return dict(os.environ, YAFL_PATH=str(libs))

    _ALPHA = "namespace Alpha\nimport System\nfun one(): Int\n  ret 1\n"

    def _own_alpha(self, source: str) -> None:
        self._write("yafl.toml", 'name = "alpha"\nnamespaces = ["Alpha"]\n')
        self._write("alpha.yafl", source)

    def test_the_folder_is_the_library_that_it_shadows(self):
        # As a program it would declare into a namespace a library lists.
        env = self._installed("alpha", "Alpha", self._ALPHA)
        self._own_alpha("namespace Alpha\nimport System\nfun two(): Int\n  ret 2\n")
        self.assertEqual([], self._items("alpha.yafl", env))

    def test_its_own_errors_are_in_its_files(self):
        env = self._installed("alpha", "Alpha", self._ALPHA)
        self._own_alpha("namespace Alpha\nimport System\nfun two(): Int\n  ret nosuch\n")
        items = self._items("alpha.yafl", env)
        self.assertTrue(items)
        lines = {i["range"]["start"]["line"] for i in items}
        self.assertIn(3, lines)                  # the use of nosuch
        self.assertLessEqual(lines, {2, 3})      # nothing outside the function

    def test_what_is_built_on_the_shadowed_library_is_left_out(self):
        # beta imports Alpha. Beside the folder's Alpha it cannot be analysed,
        # and it is not an error in the folder.
        env = self._installed("alpha", "Alpha", self._ALPHA)
        self._installed("beta", "Beta", "namespace Beta\nimport System\nimport Alpha\n"
                                         "fun three(): Int\n  ret one() + 2\n")
        self._own_alpha("namespace Alpha\nimport System\nfun two(): Int\n  ret 2\n")
        self.assertEqual([], self._items("alpha.yafl", env))

    def test_a_namespace_that_another_library_lists_is_still_an_error(self):
        env = self._installed("gamma", "Alpha", self._ALPHA)
        self._own_alpha("namespace Alpha\nimport System\nfun two(): Int\n  ret 2\n")
        items = self._items("alpha.yafl", env)
        self.assertEqual(1, len(items))
        self.assertIn("belongs to library 'gamma'", items[0]["message"])

    def test_the_stdlib_folder_is_System(self):
        # The sources as they are in the tree, with the manifest beside them.
        import shutil
        from pathlib import Path
        shutil.rmtree(self.root)
        shutil.copytree(Path(__file__).parent.parent / "stdlib", self.root)
        # The first statement of System is where a program would be told off.
        self.assertEqual([], self._items("System/abort.yafl"))

