# Port library discovery — decisions for review

Status: **implemented and gated, NOT committed.** Every point below is a
judgement call I made without being able to ask. They are ordered by how much
they could bite: things that change behaviour or admit a divergence first.

Gate: **29/29, 7448s** (bootstrap_binary 852s, compiler_suite 5887s,
self_compile 628s, stdlib_tests, 24 C tests). Two things had to happen first,
both worth knowing:

- **`ctest` never builds.** Adding `sys_getenv` to `object.c` meant the gate
  linked `build/yafllib/libyafl.a` — the CMake tree's copy, which `ctest` does
  not refresh — and died on `undefined reference`. All four
  `yafllib/build/*/libyafl.a` had the symbol; the one it actually links did
  not. Run `make` in `build/` after any runtime change.
- **A stdlib change invalidates the reference cache.** `cached_reference` keys
  on the corpus file's text, not the stdlib's, so 67 tests failed on union
  discriminator tags (`._tag = 31` vs `29`) — my new `String|None` shifted the
  numbering. `build_bootstrap.py --refresh-references`, then green.

## The gap being closed

The self-hosted compiler could not resolve `import Some::Library` at all. It
read a pre-assembled whole-program stream on stdin, so every library had to be
concatenated for it by the caller, while the reference compiler has located
libraries on a search path since the build system landed. `grep` for
`yafl.toml`, `namespace_index`, `search_path` or `discover_librar` across
`bootstrap/` returned nothing.

New files: `bootstrap/driver/{toml,zip,libraries,references}.yafl`; the
diagnostic modes `toml`, `libs`, `libsfor`, `linkspec`; the compiling modes
`project` and `projecttest` (with -O1..-O3 twins); SHA-256 in the port;
`fs_mkdir` + `System::IO::makeDirs` and `System::argv0` in the runtime and
stdlib; and two test modules — `test_bootstrap_libraries.py` (29 tests) and
`test_bootstrap_project.py` (15 tests).

The port does not merely find libraries. `ybootstrap project` compiles a
program that says `import Greet` and nothing else and emits the same C as
`compiler.compile(..., lib_paths=[...])`, byte for byte — and given the
shipped `system.yl`, it extracts `yafl.h` and `libyafl.a` out of the archive,
reports the `-I` and link paths, and the binary that comes out of the linker
runs.

## What a review pass found after I first called this done

I had this working and was writing the summary when a review of the four new
files turned up **eight real defects**, six of them silent. They are fixed and
each now has a test that fails against the old code. Listing them because the
pattern matters more than the individual bugs — every one of them was a place
where the port did something *reasonable* that Python does not do:

| defect | effect |
|---|---|
| directory sources read one level deep, not `rglob` | a library laid out in sub-directories contributed **zero** statements, silently |
| duplicate-namespace check documented but never written | first-match-wins shadowing — the exact directory-order dependence the comment forbade |
| worklist keyed on manifest name | two manifests without a `name` both default to `"unnamed"`, so the second never loaded |
| `.yl` dispatch keyed on the suffix | a *directory* called `foo.yl` anywhere on the path aborted all discovery |
| comment scanner blind to `\"` | `"a\"#b"` truncated, then failed as an unterminated string |
| multi-line arrays rejected | the commonest way to write a long array — accepted by tomllib |
| missing comma in an array accepted | accepting invalid input is the same divergence, just quieter |
| whole-file read accumulated with `acc + s` | quadratic: 40 MB took 1m51s, and a `.yl` grows with `libyafl.a` |

Two more surfaced only because the tests existed: `listDir` returns `.` and
`..` (which `rglob` never does), so the new recursive walk descended into `.`
for ever; and I changed the worklist key to `libRoot` in one file while the
caller still accumulated names, so nothing ever counted as loaded and the
fixpoint spun. Both were caught by tests, not by reading.

**The honest lesson: I reported this finished before it was.** The functional
checks I ran — does an import resolve, does the candidate set match Python —
all passed, and none of them touched a sub-directory, a second unnamed library,
or a 40 MB archive.

---

## 1. `.yl` archives are now written UNCOMPRESSED

`package_system_library` writes `ZIP_STORED` instead of `ZIP_DEFLATED`, on your
instruction, and the port's reader supports stored entries **only** — a
compressed entry is a hard error naming the entry, never a silent empty read.

The cost is archive size, and it is not trivial: a `.yl` is mostly `libyafl.a`.
The benefit is that the port's zip reader is a header walk and a byte copy
rather than a Huffman decoder and an LZ77 window — several hundred lines of
exactly the code that stays subtly wrong for years. A test asserts the
packaging still says `ZIP_STORED`, so flipping it back fails loudly instead of
silently producing libraries that appear to contain no sources.

## 2. `System::env` returns `String|None`, and NULL is the None arm

Unset is `None`, distinct from set-to-empty — `YAFL_PATH=` and an absent
`YAFL_PATH` are different statements. The runtime returns `NULL` for the None
arm, which is correct **here** because every member of `String|None` is
pointer-represented, so the union collapses to a pointer. That condition is
written into the comment rather than the shorthand "None is NULL", which is
false in general.

`env` lives in `stdlib/args.yafl`, so it joins the System library and therefore
**every compilation in the tree**. That is a stdlib API addition — a design
decision, not a mechanical port — and it is why all four `yafllib/build/*`
archives were rebuilt.

## 3. Manifest parsing REJECTS the TOML it does not implement

The port parses exactly the manifest subset: top-level `key = value` where the
value is a quoted string or an array of quoted strings, `#` comments, blank
lines, and the escapes `\\ \" \n \t`. Tables, numbers, booleans, nested arrays
and multi-line *strings* are **errors naming the line**, not ignored keys.

Skipping what it does not understand would let a manifest mean one thing to
`tomllib` and another to the port, silently. I would rather a manifest using
real TOML fail loudly than load with fields missing. It does mean the port
rejects some valid TOML that Python accepts.

The line I drew after review: things tomllib accepts **and manifests are
actually written with** are now supported rather than rejected — arrays
spanning lines, trailing commas, quoted keys, `#` and `\"` inside strings. And
the divergence runs both ways, so two things tomllib *rejects* are now errors
here too: a missing comma between array values, and a duplicate key. Every one
of these is a test that diffs the port against `parse_manifest`, so the ruling
is pinned rather than remembered.

## 4. The qualified-reference collector is a hand-written walk

`_candidate_namespaces` gets its AST half from one reflective
`search_and_replace`, keeping `::`-containing names that sit on a
`NamedExpression` or a `NamedSpec`. The port has no reflective walk, so
`references.yafl` is that walk written out — an arm per `PStmt`, `PExpr`,
`Spec`, `PArm`, `PLit` and `SEntry` variant.

Two things make it a decision rather than transcription:

- It collects from `PeName.refName` and `SNamed.snName` **only**, matching what
  the Python predicate admits. `SClass` and `SEnum` carry names too, but the
  parser never builds one — they are what `compile()` resolves a `SNamed`
  *into*, long after libraries are loaded. If that ever stops being true, this
  under-collects.
- It names the closed leaf groups `PeLiteral` and `PeLowered` instead of
  trailing a catch-all, so a future node with children is a
  non-exhaustive-match error here rather than a silent failure to descend —
  the trap that broke 21 walkers at once when `??` landed.

Verified against Python rather than assumed: for `Alpha::thing` written with no
import, Python's set is `{Alpha, Alpha::thing, P, P::Alpha, P::Alpha::thing}`,
and six libraries claiming exactly those namespaces load precisely the five —
compositions included, `Unrelated` untouched.

## 5. A source with NO statements sees NO imports — in both compilers

`parse()` consumes the `import` lines and attaches each block's group to the
**named statements** of that block. So `namespace P` + `import Alpha` and
nothing else has no statements, hence no visible imports, and
`_candidate_namespaces` returns the empty set.

I found this by diffing against Python, having first written the port tests
with exactly that shape — they would have "passed" against a port that agreed
by accident. Every test source now carries a real statement, and
`test_a_source_with_NO_statements_sees_no_imports` pins the surprise so the
next person meets it as a test and not as a mystery.

## 6. The worklist is a fixpoint, and that needed fixing

`compile_project` loops `while frontier`: what was just loaded becomes the next
frontier, because a library the program imports may import a third. My first
cut did one round. It now parses each loaded library's sources and follows
their references too, carrying the loaded names so each library is taken once,
with a test (`test_TRANSITIVE_loading_follows_what_was_just_loaded`) that a
single round would fail.

## 7. Two `[tail]` markers dropped, one function restructured

`[tail]` requires **direct** self-recursion:

- `quoteBody` ⇄ `quoteEscape` — **restructured**, escape handling inlined, so
  the marker is kept. A string body can be long.
- `tomlLines` ⇄ `tomlLine` — **dropped**; depth is the manifest's line count.
- `nsIndexLoop` ⇄ `nsAddAll` — **dropped**; depth is the library count.
- `libsFrontier` — **not marked**: the recursion sits under a ternary and then
  a match (the shape that has mis-lowered before), and its depth is a library
  dependency chain, not a data walk.

Dropping `[tail]` means real C stack frames. Each is bounded by a single-digit
count; if any can grow, it needs restructuring like the first.

## 8. Sources are read in SORTED order, and duplicate namespaces are an ERROR

`listDir` returns a `Set`, and statement order is emission order, so reading in
directory order would make the emitted C depend on the filesystem. Sorting
matches `libraries.py`, which sorts in both the directory and zip paths.

Sorted **per directory, depth first**, which is a decision and not an
implementation detail: `sorted(root.rglob("*.yafl"))` orders by path *parts*,
so `a/b.yafl` comes before `a-b/c.yafl` — a flat sort of the joined strings
gets that pair backwards, because `-` sorts before `/`. Per-directory DFS
reproduces the parts order exactly.

Two libraries claiming one namespace fails rather than silently shadowing —
otherwise which copy you got would depend on scan order. This mirrors
`namespace_index`.

One knock-on worth flagging: making that an error means a duplicated search
path must not yield the library twice, so discovery now dedupes seen roots as
`discover_libraries` does. Python keys on `entry.resolve()`; the port keys on
the joined path, because **the runtime exposes no realpath**. Repeated
identical entries are caught; two paths aliased through a *symlink* are not,
and would surface as the duplicate-namespace error instead of being merged.
That is the one place I know the port is stricter than the reference compiler,
and it fails loudly rather than silently.

## 9. The port COMPILES with libraries — `project`, alongside `c`

The port now has `project` / `project1..3` and `projecttest` / `project1..3test`
beside the existing `c` family. `project` is `compile_project`: it takes the
user's program, discovers libraries, runs the worklist, prepends the loaded
statements and passes the libraries' headers to codegen.

**Why a second mode rather than teaching `c` to load libraries.** It is the
layering Python already has — `c` mirrors `__create_c_code` over a statement
set the *caller* assembled, `compile_project` is that plus the loader — and
keeping them separate matters for two concrete reasons:

- ~25 bootstrap modules pin `c` as the byte contract. Giving it a second,
  environment-dependent source of statements would make that contract depend on
  whether `YAFL_PATH` happened to be set.
- Those harnesses feed the stdlib *in the stream*. If `c` also loaded a
  discovered System library, the stdlib would be loaded twice and every name in
  it would become ambiguous.

`projecttest` closes the same gap on the `--test` path: the synthesised main
references `System::Test::run`, and because the registry joins the user
statements *before* the worklist runs, that reference is what pulls System::Test
in. The port previously required the caller to have concatenated it.

**Proved by byte-identical output, not by inspection.**
`tests/test_bootstrap_project.py` stages the stdlib as an ordinary directory
library (namespaces scanned exactly as `package_system_library` scans them) and
runs Python with `use_stdlib=False`, so both compilers load the same libraries
from the same path and nothing else. Ten tests, each comparing whole C files:
a direct import, a transitive library the program never names, a library reached
only by a qualified reference, a `.yl` archive, sources in sub-directories, -O1,
headers reaching the `#include` list, `projecttest`, plus an unresolvable import
and a broken manifest.

Two ordering rules had to be right for that to hold, and both are the sort of
thing that would otherwise emit valid-but-different C:

- `__tokenize_and_parse` sorts **per library, by basename** — so the port parses
  each library's sources as its own sorted group. Sorting the round's sources as
  one flat list interleaves two libraries' files.
- `lib_statements + user_statements`, libraries first.

The filename is load-bearing too: it feeds hash6, which feeds every generated
name. The tests hand the port a `#FILE# prog.yafl` stream because bare stdin
parses as `"x"`, and that alone made every symbol differ by its hash suffix —
which is exactly how the first run failed.

## 10. `LinkSpec` is written but not called, deliberately

Nothing invokes `linkSpecFor` yet — it belongs to the wiring in point 9. I kept
it rather than deleting it because both of its rules are silent-divergence
traps that are much easier to get right now than to discover later:

- headers go in by **basename** (`header_names`), so `headers = ["include/foo.h"]`
  emits `#include "foo.h"`;
- de-duplication **preserves insertion order**, because this list becomes
  `#include` order in the generated C, and sorting it would change the emitted
  bytes against a byte-parity contract. (My first version sorted.)

Where Python extracts a `.yl`'s archives to a content-hashed cache directory,
the port has no extraction, and `system.yl/libyafl.a` is a path that cannot
exist. That case is now an explicit error naming the library rather than a
fabricated path handed to the linker.

## 11. Native artefacts ARE extracted, and that needed three new primitives

A `.yl`'s header and archive live inside the zip, where no C compiler or linker
can reach them. `_materialised_native_dir` extracts them to
`<tmp>/yafl-lib-cache/<name>-<sha256(archive)[:16]>` and returns paths into it.
The port now does the same, into the **same directory** — so the two compilers
share one cache rather than each extracting the same archive to a place the
other never looks. Three things had to exist first:

- **`fs_mkdir` in the runtime.** The port could not create a directory at all —
  `fs_exists`, `fs_stat`, `fs_open_dir` and `fs_remove`, but no mkdir. Added as
  one more IO-thread op, one directory per call with EEXIST as success;
  `System::IO::makeDirs` walks the components, so `mkdir -p` lives in YAFL and
  the runtime stays a single syscall.
- **SHA-256 in the port.** The cache key is a sha256 of the archive bytes, and
  the port had only MD5 and SHA-1. It shares SHA-1's padding wholesale — both
  are Merkle–Damgård with a big-endian length — and is verified against
  `hashlib` on the empty string, `abc`, a multi-block input and the 16-char
  prefix.
- **`System::argv0`.** For the search path, below.

`LinkSpec` now carries include directories as well as headers and archives, and
the driver has a `linkspec` mode: `compile_project` *returns* the spec next to
the C, and the port writes C to stdout, so the spec needs its own surface
rather than being computed and thrown away.

**The end-to-end test is the one that matters.** It takes the shipped
`build/stage/system.yl` — the artefact CMake installs, holding the stdlib
sources, `yafl.h` and `libyafl.a` — gives the port nothing but that search path
and a five-line program, then links the C it emits with the archive the port
extracted and *runs the binary*, checking its exit code. Discovery, zip
reading, source loading, C emission, extraction, linking and execution, with
nothing staged by hand.

## 12. The installed search path uses argv[0]

`search_paths` appends `${prefix}/lib/yafl`, derived from the executable —
but only for a frozen build, because only a frozen build is an installed
binary sitting in `bin/`. The port is always that, so it now derives the same
path from `argv[0]`: `dirname(dirname(argv0))/lib/yafl`, lowest precedence,
after the explicit paths and `YAFL_PATH`.

Contentious bit: **when `argv[0]` carries no directory, it contributes
nothing.** A program found on `PATH` cannot say where it lives, and guessing
would put an arbitrary `lib/yafl` on the search path. Python resolves
`sys.executable`, which is always a path; the port has no realpath and no PATH
search, so this is the one place it can come up empty where Python would not.

## 13. What is NOT done

- The dev-System fallback (`dev_system_library`) and the `compiler/libs`
  gating in `available_libraries`. These synthesise a System library from the
  **source tree** — `compiler/stdlib` plus `yafllib/yafl.h` and a built
  `libyafl.a` — for running un-installed. They are located relative to
  `libraries.py`, and a compiled `ybootstrap` has no equivalent notion of "my
  repository": there is no path it could look at that would be right. The
  port's un-installed use is the test harnesses, which hand it the stdlib
  directly. This is the one item I am recording as genuinely not portable
  rather than not yet done — if you disagree, the fix is to teach the port a
  configured build-tree root, and I would rather be told than guess.
