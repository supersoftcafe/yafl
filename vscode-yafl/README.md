# YAFL for Visual Studio Code

Language support for [YAFL](../README.md) source files (`.yafl`):

- **A language client** (`extension.js`) — the compiler is the language
  server: `yaflc --lsp`, started for the workspace when a `.yafl` file opens.
  It gives every error and warning a compile would, as you type; go to
  definition; and find references, into the libraries too. The compiler to run
  is the `yafl.server.path` setting, `yaflc` on `PATH` by default.

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

The workspace folder is the program: every `.yafl` under it, as
`yaflc <folder>` compiles it. The installed libraries are found as a compile
finds them (`YAFL_PATH`, then the install's own).

## Build and install

Standalone CMake project (like `examples/`); it is **not** part of the top-level
YAFL build.

```sh
cmake -S vscode-yafl -B vscode-yafl/build
cmake --build vscode-yafl/build --target install-extension
```

`install-extension` installs the client's npm dependencies (`npm ci`, from
`package-lock.json`; needs Node.js), then symlinks this directory into
`~/.vscode/extensions/yafl-0.2.0` (override the parent with
`-DYAFL_VSCODE_EXTENSIONS_DIR=...`). Run **Developer: Reload Window** in VS Code
afterwards. Because it is a symlink, later edits take effect on the next reload
with no rebuild.

Other targets:

| Target                 | Effect                                                        |
|------------------------|-------------------------------------------------------------|
| `uninstall-extension`  | Remove the symlink.                                          |
| `package-vsix`         | Build `vscode-yafl-0.2.0.vsix`, dependencies included, via `npx @vscode/vsce`. |

## Possible future work

Hover types, completion, semantic highlighting and formatting are the
language server's to add; the client needs nothing new for them.
