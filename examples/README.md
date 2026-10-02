# YAFL examples

Example programs written in YAFL, kept here to show what the language looks
like in real use. Each one is a complete program with a `main`, and most are
useful tools in their own right.

This folder holds examples only. Tests, regression pins and compiler corpus
programs belong in `compiler/tests/` (for corpus programs,
`compiler/tests/corpus_converge/`), not here.

## The examples

| Example | What it does | What it shows |
|---|---|---|
| `helloWorld.yafl` | Prints a greeting. | The smallest complete program: a namespace, an import, a global `let` and `main`. |
| `linenumbers.yafl` | Copies stdin to stdout, numbering each line. | A streaming IO pipeline (`asStream`, `toLines`, `writeToFile`) and closing linear IO handles. |
| `json_pretty.yafl` | Pretty-prints JSON from stdin, one file, or a whole directory tree. | `System::Json`, lazy streams that run in constant memory, and pipelines written without type arguments or `let`. |
| `findstr.yafl` | Searches every file under a directory for a substring, printing `file:line:text`. | `__parallel__` doing real work, with deterministic output and per-file error reporting. |
| `yspell.yafl` | Spell-checks text files against a dictionary, suggesting words one edit away. | A large immutable set built once and queried many times. |
| `hashed_tree.yafl` | Hashes a recursive tree. | `[hashed]` on a function: the result is cached in the value, and a recursive hash reuses the children's caches. |
| `raytracer.yafl` | Renders a scene from stdin (for example `scenes/spheres.scene`) to a PPM image on stdout. | Floating-point arithmetic in bulk, small value structs, a union dispatched per hit, optional values and recursion. |
| `ylisp.yafl` | A small Lisp interpreter, with the program on stdin. | Enums as an interpreter's core, closures and environment chains, bignum arithmetic, and errors carried as unions. |
| `yaflc.yafl` | A miniature compiler for a core subset of YAFL, emitting C. | Tokenising, recursive-descent parsing with precedence, name resolution and code generation, all in YAFL. |

The comment at the top of each file gives its usage, behaviour and exit codes.

## Building

`CMakeLists.txt` builds `json_pretty`, `findstr`, `yspell` and `linenumbers` with
an installed `yafl` compiler:

    cmake -B build && cmake --build build

Any example can also be built directly:

    yafl -O2 -o raytracer raytracer.yafl
