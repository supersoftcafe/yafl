
from unittest import TestCase
from pathlib import Path

from tokenizer import tokenize, TokenKind


class Test(TestCase):
    def test_tokenize_test1(self):
        path = Path(__file__).parent / "samples" / "test1.yafl"
        with path.open() as f:
            tokens = tokenize(f.read(), str(path))

        self.assertEqual(9, len(tokens))
        self.assertEqual(TokenKind.NUMBER, tokens[-2].kind)
        self.assertEqual(TokenKind.EOF, tokens[-1].kind)
        self.assertEqual("1i32", tokens[-2].value)

    def test_tokenize_qualified_type(self):
        tokens = tokenize("somewhere  ::    something", "file")
        self.assertEqual(4, len(tokens))
        self.assertEqual(TokenKind.IDENTIFIER, tokens[0].kind)
        self.assertEqual("somewhere", tokens[0].value)
        self.assertEqual(TokenKind.SYMBOLS, tokens[1].kind)
        self.assertEqual("::", tokens[1].value)
        self.assertEqual(TokenKind.IDENTIFIER, tokens[2].kind)
        self.assertEqual("something", tokens[2].value)

    def test_tokenize_builtin_type(self):
        tokens = tokenize("__builtin_type__", "file")
        self.assertEqual(2, len(tokens))
        self.assertEqual(TokenKind.SYMBOLS, tokens[0].kind)
        self.assertEqual("__builtin_type__", tokens[0].value)

    def test_tokenize_quoted_identifier(self):
        tokens = tokenize("`+`", "file")
        self.assertEqual(2, len(tokens))
        self.assertEqual(TokenKind.IDENTIFIER, tokens[0].kind)
        self.assertEqual("`+`", tokens[0].value)

    def test_tokenize_string(self):
        tokens = tokenize("\"fred\"", "file")
        self.assertEqual(2, len(tokens))
        self.assertEqual(TokenKind.STRING, tokens[0].kind)
        self.assertEqual("\"fred\"", tokens[0].value)

    def test_simple_interface(self):
        tokens = tokenize("interface Simple", "file")
        self.assertEqual(3, len(tokens))
        self.assertEqual(TokenKind.SYMBOLS, tokens[0].kind)
        self.assertEqual("interface", tokens[0].value)
        self.assertEqual(TokenKind.IDENTIFIER, tokens[1].kind)
        self.assertEqual("Simple", tokens[1].value)
        self.assertEqual(TokenKind.EOF, tokens[2].kind)