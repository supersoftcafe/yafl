# Changelog

## 0.2.0

- A language client: `.yafl` documents are served by `yaflc --lsp`, which
  gives diagnostics, go to definition and find references. The compiler to
  run is the `yafl.server.path` setting.

## 0.1.0

- Initial release: TextMate grammar, language configuration, and snippets for
  YAFL. Replaces the old `yafl.tmbundle/` at the repository root; grammar
  reconciled with `compiler/parsing/tokenizer.py`.
