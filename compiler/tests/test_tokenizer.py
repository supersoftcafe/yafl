
from tests.testutil import TimedTestCase as TestCase
from pathlib import Path

from parsing.tokenizer import tokenize, TokenKind


class Test(TestCase):
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

    def test_tokenize_char(self):
        tokens = tokenize("'A'", "file")
        self.assertEqual(2, len(tokens))
        self.assertEqual(TokenKind.CHAR, tokens[0].kind)
        self.assertEqual("'A'", tokens[0].value)

    def test_tokenize_char_escaped_quote(self):
        # The escaped single quote is consumed by the \. branch, so the
        # literal spans the whole '\'' rather than ending early.
        tokens = tokenize(r"'\''", "file")
        self.assertEqual(2, len(tokens))
        self.assertEqual(TokenKind.CHAR, tokens[0].kind)
        self.assertEqual(r"'\''", tokens[0].value)

    def test_tokenize_two_chars_split(self):
        # A quote is neither \. nor [^\\'], so the body stops at the closing
        # quote: "'a' 'b'" is two separate char tokens, not one run.
        tokens = tokenize("'a' 'b'", "file")
        kinds = [tok.kind for tok in tokens]
        self.assertEqual([TokenKind.CHAR, TokenKind.CHAR, TokenKind.EOF], kinds)
        self.assertEqual("'a'", tokens[0].value)
        self.assertEqual("'b'", tokens[1].value)

    def test_apostrophe_in_comment_is_not_a_char(self):
        # The comment rule runs first, so an apostrophe after '#' never starts
        # a char literal.
        tokens = tokenize("x  # don't tokenise this", "file")
        self.assertEqual([TokenKind.IDENTIFIER, TokenKind.EOF],
                         [tok.kind for tok in tokens])

    def test_simple_interface(self):
        tokens = tokenize("interface Simple", "file")
        self.assertEqual(3, len(tokens))
        self.assertEqual(TokenKind.SYMBOLS, tokens[0].kind)
        self.assertEqual("interface", tokens[0].value)
        self.assertEqual(TokenKind.IDENTIFIER, tokens[1].kind)
        self.assertEqual("Simple", tokens[1].value)
        self.assertEqual(TokenKind.EOF, tokens[2].kind)

    def test_pipeline_operator(self):
        tokens = tokenize("fred\n  |>bill", "file")
        self.assertEqual(4, len(tokens))
        self.assertEqual(TokenKind.IDENTIFIER, tokens[0].kind)
        self.assertEqual("fred", tokens[0].value)
        self.assertEqual(TokenKind.SYMBOLS, tokens[1].kind)
        self.assertEqual("|>", tokens[1].value)
        self.assertEqual(TokenKind.IDENTIFIER, tokens[2].kind)
        self.assertEqual("bill", tokens[2].value)
        self.assertEqual(TokenKind.EOF, tokens[3].kind)

    def test_named_with_generics(self):
        tokens = tokenize("fred<bill,bert>", "file")
        self.assertEqual(7, len(tokens))
        self.assertEqual(TokenKind.IDENTIFIER, tokens[0].kind)
        self.assertEqual("fred", tokens[0].value)
        self.assertEqual(TokenKind.SYMBOLS, tokens[1].kind)
        self.assertEqual("<", tokens[1].value)
        self.assertEqual(TokenKind.IDENTIFIER, tokens[2].kind)
        self.assertEqual("bill", tokens[2].value)
        self.assertEqual(TokenKind.SYMBOLS, tokens[3].kind)
        self.assertEqual(",", tokens[3].value)
        self.assertEqual(TokenKind.IDENTIFIER, tokens[4].kind)
        self.assertEqual("bert", tokens[4].value)
        self.assertEqual(TokenKind.SYMBOLS, tokens[5].kind)
        self.assertEqual(">", tokens[5].value)
        self.assertEqual(TokenKind.EOF, tokens[6].kind)
