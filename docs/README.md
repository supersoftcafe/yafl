# YAFL Documentation

This folder contains design and reference documentation for YAFL. These documents cover the language's design philosophy, runtime architecture, and implementation internals.

Planned work is tracked in [GitHub issues](https://github.com/supersoftcafe/yafl/issues), not here.

Documents with a status line at the top (proposal, parked, design agreed, implemented) say how far the design has gone. A design note describes what was decided when it was written, so where it and the code disagree, the code is right.

## Using the language

| Document | Description |
|----------|-------------|
| [Language Guide](guide.md) | Narrative walkthrough of the language, from first program to advanced features |
| [Language Reference](reference.md) | Authoritative reference for every language construct and built-in type |
| [Source layout](style.md) | The one layout `yaflc --format` puts source in: blank lines, `=>` or `ret`, wrapping, ternaries, pipelines, comments |
| [Language server](language-server.md) | `yaflc --lsp`: what it serves, what the program is, how libraries and analysis work, and the `System::Server` loop it runs on |
| [Language design](lang_info.md) | A pointer to the guide and the reference, where this page's content moved |

## How the compiler and runtime work

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | Runtime design decisions: the parser, task-based async lowering, thread pool, virtual dispatch, and memory model |
| [Compiler internals](compiler-internals.md) | The ideas the compiler is built on, pass by pass, for someone reading `compiler/` for the first time |
| [Internals](internals.md) | The garbage collector as built: stages, pacing, marking by pages, the page allocator, and where the code lives |
| [Generations](generations-design.md) | Old stays old: a card per object marks an old object that may point at young ones; minors trace the cards; majors keep old pages old and compact sparse ones into pages born old. Mechanism, the stamp and card protocols, measurements |
| [Enum representation](enum-representation.md) | The enum-encoding principle: minimal shared fields + tag, deconstruction, the 8-word threshold, per-variant boxing |
| [Containers](containers.md) | The container design law: no iteration on unordered containers; the containers and what each is for; what was removed and why |
| [Array](array-design.md) | `Array<T>` as a value over a growable buffer (`[capacity]` fields, element `:=`, append/push) |
| [Port library discovery](port-library-discovery-review.md) | How the self-hosted compiler finds, loads and links libraries: the search path, shadowing by name, `.yl` archives, and each decision taken |
| [One type merge](type-merge-design.md) | Inference combines two types in eight places; the one merge that replaces them, and how far the move has got |
| [Derived equality](derived-equality-plan.md) | Derived `BasicEquality` for enums and tuples, with precise keys (complete) |
| [`[test]`](testing-proposal.md) | The compiler builds the test binary: `yaflc --test`, test discovery and the runner's output |

## Tools

| Document | Description |
|----------|-------------|
| [Profiling](profiling-design.md) | `--profile`: exact call counters + sampled CPU time, callgrind/folded output, attribution semantics |
| [Heap profiling](heap-profiling-design.md) | Live census by type → massif; sampled inuse_space by allocation site → pprof; instrument the collection boundary, never allocation counts |
| [Logging](logging-design.md) | Structured logging and runtime metrics: levels, contexts, the runtime's clock and destination (`System::Log`) |

## Proposals, parked and removed designs

| Document | Description |
|----------|-------------|
| [Parser proposal](parser-proposal.md) | Design note: a self-hosted YAFL parser in the `parselib` combinator style |
| [`memoize`](memoize-proposal.md) | A function that wraps a function with the same signature, so repeated calls share the first answer |
| [The `with` expression](preserving-rewrites-design.md) | Copy-with-replacements that preserves identity when nothing changes |
| [Copy elimination (parked)](copy-elimination-design.md) | Eliding the copy in `with`; checked against the compiler and parked, with what shipped instead |
| [Inlining and async](inlining-async-policy.md) | Notes on when inlining a sync callee into an async caller helps, and when it does not |
| [Pin-region barriers](pin-region-barriers-design.md) | GC bookkeeping at pin and unpin rather than per store (design, not built) |
| [Heap recycling (parked)](heap-recycling-design.md) | Reusing provably dead objects without the collector: stream representations, the String trick vs overwrite, safe reuse on a thread's unscanned pages, the caller-releases design with escape summaries, and what the prototype on `claude/recycling-prototype` measured |
| [Thread-local nursery prototype](local-nursery-prototype.md) | REMOVED 2026-10-30, replaced by the collector's dwell between cycles (the status note says why). Was on by default, any worker count: a thread traces its own birth-protected pages and reuses the dead ones without charging the pacing clock. Mechanism, the promotion hole it hit, measurements (−30% / −26% on short-lived allocation, neutral elsewhere) and what async-heavy code needs next |
