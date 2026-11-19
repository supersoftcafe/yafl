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
