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


_INITIALIZE = _request(1, "initialize", {"processId": None, "rootUri": None, "capabilities": {}})


class TestLifecycle(TestCase):

    def _serve(self, stream: bytes) -> tuple[int, list[dict]]:
        p = subprocess.run([shared_bootstrap_binary(), "--lsp"], input=stream,
                           capture_output=True, timeout=60)
        return p.returncode, _replies(p.stdout)

    def _session(self, *messages: dict) -> tuple[int, list[dict]]:
        return self._serve(b"".join(_frame(m) for m in messages))

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
        p = subprocess.run([shared_bootstrap_binary(), "--lsp"], input=stream,
                           capture_output=True, timeout=60)
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


class TestDiagnostics(TestCase):
    """Pull diagnostics over a workspace folder: files on disk, documents the
    editor has open, and the libraries beneath them."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name).resolve()

    def tearDown(self):
        self._dir.cleanup()

    def _write(self, unit: str, text: str) -> str:
        path = self.root / unit
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path.as_uri()

    def _uri(self, unit: str) -> str:
        return (self.root / unit).as_uri()

    def _session(self, *messages: dict) -> dict:
        """Each diagnostic reply's items, by request id."""
        stream = [_request(1, "initialize", {"rootUri": self.root.as_uri(), "capabilities": {}}),
                  _notification("initialized"), *messages,
                  _request(99, "shutdown"), _notification("exit")]
        p = subprocess.run([shared_bootstrap_binary(), "--lsp"],
                           input=b"".join(_frame(m) for m in stream),
                           capture_output=True, timeout=300)
        self.assertEqual(0, p.returncode, p.stderr)
        return {r["id"]: r["result"]["items"] for r in _replies(p.stdout)
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

    def test_an_edit_in_one_file_changes_another(self):
        self._write("main.yafl", "namespace Main\nimport System\nfun main(): Int\n  ret helper()\n")
        self._write("lib/helper.yafl", "namespace Main\nimport System\nfun helper(): Int\n  ret 0\n")
        items = self._session(self._pull(2, "main.yafl"),
                              self._open("lib/helper.yafl", "namespace Main\nimport System\nfun other(): Int\n  ret 0\n"),
                              self._pull(3, "main.yafl"))
        self.assertEqual([], items[2])
        self.assertIn("Failed to resolve helper", " ".join(m for *_, m in self._summary(items[3])))

    def test_a_library_folder_is_not_the_program(self):
        self._write("main.yafl", self._CLEAN)
        self._write("mylib/yafl.toml", 'name = "mylib"\nnamespaces = ["MyLib"]\n')
        self._write("mylib/broken.yafl", "namespace MyLib\nfun broken(: Int\n")
        items = self._session(self._pull(2, "main.yafl"))[2]
        self.assertEqual([], items)

    def test_a_document_outside_the_workspace_has_none(self):
        self._write("main.yafl", "namespace Main\nimport System\nfun main(): Int\n  ret nosuch\n")
        items = self._session(_request(2, "textDocument/diagnostic",
                                       {"textDocument": {"uri": "file:///elsewhere/x.yafl"}}))[2]
        self.assertEqual([], items)


class TestNavigation(TestCase):
    """Go to definition and find references, over a workspace folder and the
    libraries beneath it."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name).resolve()

    def tearDown(self):
        self._dir.cleanup()

    def _write(self, unit: str, text: str) -> None:
        path = self.root / unit
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def _uri(self, unit: str) -> str:
        return (self.root / unit).as_uri()

    def _session(self, *messages: dict) -> dict:
        """Each reply's result, by request id."""
        stream = [_request(1, "initialize", {"rootUri": self.root.as_uri(), "capabilities": {}}),
                  _notification("initialized"), *messages,
                  _request(99, "shutdown"), _notification("exit")]
        p = subprocess.run([shared_bootstrap_binary(), "--lsp"],
                           input=b"".join(_frame(m) for m in stream),
                           capture_output=True, timeout=300)
        self.assertEqual(0, p.returncode, p.stderr)
        return {r["id"]: r.get("result") for r in _replies(p.stdout)}

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

    def test_the_server_says_it_navigates(self):
        got = self._session()
        caps = got[1]["capabilities"]
        self.assertTrue(caps["definitionProvider"])
        self.assertTrue(caps["referencesProvider"])


class TestPackagedLibraries(TestCase):
    """A library installed as a `.yl` keeps its sources inside the zip; the
    server writes them out, under its own temp folder, for as long as it runs,
    so a definition in one can be opened."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self._dir = tempfile.TemporaryDirectory()
        base = Path(self._dir.name).resolve()
        self.root, self.libs = base / "work", base / "libs"
        self.root.mkdir()
        self.libs.mkdir()

    def tearDown(self):
        self._dir.cleanup()

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
