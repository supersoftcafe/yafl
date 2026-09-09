# YAFL for Visual Studio Code

Declarative language support for [YAFL](../README.md) source files (`.yafl`):

- **Syntax highlighting** — a TextMate grammar (`syntaxes/yafl.tmLanguage.json`)
  kept in step with the compiler tokenizer (`compiler/parsing/tokenizer.py`):
  keywords, `#` comments, string / char / `re"..."` regex literals, numeric
  literals with prefixes and type suffixes, pipeline (`|>`) and bind (`?>`)
  operators, `[tail]`-style attributes, type names and type-argument lists,
  `::`-qualified names, and backtick operator identifiers.
- **Editor behaviour** (`language-configuration.json`) — `#` comment toggle and
  continuation, bracket matching / auto-closing for `() [] "" '' `` `` ``, a word
  pattern that treats `` `[]` `` as one word, and indentation after block
  headers. Indentation is pinned to 2 spaces for `.yafl` because the language is
  whitespace-significant.
- **Snippets** (`snippets/yafl.json`) — skeletons for `namespace`, `fun`,
  `class`, `interface`, `enum`, and `match`.

This is intentionally a *static* extension: no language server, no bundled
JavaScript, no activation cost.

## Build and install

Standalone CMake project (like `examples/`); it is **not** part of the top-level
YAFL build.

```sh
cmake -S vscode-yafl -B vscode-yafl/build
cmake --build vscode-yafl/build --target install-extension
```

`install-extension` symlinks this directory into
`~/.vscode/extensions/yafl-0.1.0` (override the parent with
`-DYAFL_VSCODE_EXTENSIONS_DIR=...`). Run **Developer: Reload Window** in VS Code
afterwards. Because it is a symlink, later edits to the grammar take effect on
the next reload with no rebuild.

Other targets:

| Target                 | Effect                                                        |
|------------------------|-------------------------------------------------------------|
| `uninstall-extension`  | Remove the symlink.                                          |
| `package-vsix`         | Build `vscode-yafl-0.1.0.vsix` via `npx @vscode/vsce` (needs Node). |

## Possible future work

Anything type-aware — diagnostics, go-to-definition, hover types, completion,
semantic highlighting, formatting — needs a language server and is deliberately
out of scope here.
