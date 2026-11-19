# The language server

`yaflc --lsp` is the compiler serving the
[Language Server Protocol](https://microsoft.github.io/language-server-protocol/)
on stdin and stdout. An editor starts it for a workspace and asks it about the
program as it is edited. The VS Code extension in `vscode-yafl/` is a client
for it; any LSP client can use it the same way. Only the YAFL compiler has
the flag: the Python compiler does not serve.

## What it answers

| Request | Answer |
|---------|--------|
| `textDocument/diagnostic` | Every error and warning in the document, from an analysis of the whole program. The client pulls them; the server does not push. |
| `textDocument/definition` | Where the name under the cursor is declared: a function, a local, a parameter, a field or member reached through `.`, a class or an enum, in the program or a library. |
| `textDocument/references` | Every use of that name in the program, with its declaration when the client asks for it. |

Documents are synchronised whole on every change. Positions are UTF-16 units,
the protocol's default: a character beyond U+FFFF is one column to the
compiler and two to the client.

## The program

The workspace folder is the program: every `.yafl` file under it, each named by
its path relative to the folder, exactly the units `yaflc <folder>` compiles.
Libraries are what is installed, outside it. A document the editor has open
replaces the file on disk, until it is closed. A document outside the
workspace folder has no diagnostics.

## The libraries

The installed libraries are found as a compile finds them. A compile prunes
each library to the namespaces its program reaches; the server cannot, since
an edit can add an import at any time, so it loads every library whole. The
libraries converge once, each on the ones beneath it, the first time they are
needed, and are never converged again. Only the program converges with each
analysis, on top of them.

A library installed as a `.yl` keeps its sources inside the zip, where an
editor cannot open them. The server writes them out where a compile writes the
library's native files, `<process temp folder>/libs/<name>/`, so a definition
in one opens a file. That folder belongs to the server and goes when it exits.

## Analysis

Analysis is lazy. Opening, changing or closing a document only records its
text. A request that answers from an analysis runs one first if the stored one
is older than the latest edit, so a burst of edits costs one analysis, and no
answer comes from text older than the request.

An analysis is a compile's front end: parse, converge, and the checks that
follow, stopping before lowering. Every error a program can have is found by
then; one found later is a compiler bug, not something to show the user.

Navigation needs no index of its own. Every declaration's name is unique from
the parse on (`name@hash`, the hash taken from where it is declared), and
convergence resolves each name the program uses to the one it means. So the
declarations by unique name, and every use in the converged program, are the
whole index.

## The loop

The server runs on `System::Server`, a loop in the standard library:

```
serve(input, output, state, read, capture, process, write)
```

It reads a message, captures what handling it needs from outside the state,
handles it, and writes the replies, until the input ends or a stage stops it.
Each stage answers with `Next<T>`: `More(value)`, `Done()` or `Failed(why)`.
The caller opens the streams and closes them; `serve` hands both back with
the final state.

`process` is pure. For the language server it is a step from the state, the
captured files and a message to the next state and the replies. `capture` is
the only stage besides reading and writing that looks at the world: it reads
the program's files when a message needs an analysis, and the libraries the
first time. Each reply is flushed as it is written, since the client waits for
it before sending more.

An analysis holds up the loop while it runs, so a request to cancel cannot
take effect in the middle of one.

## The lifecycle

Requests before `initialize` are refused, and after `shutdown` only `exit` is
accepted. `exit` ends the session: with status 0 when `shutdown` came first,
1 when it did not. An input that closes or breaks without an `exit` ends it
with 1.
