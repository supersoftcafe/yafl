
# Type inference

The ideal is to be able to write code without specifying the type of parameters, class members
, function return types etc. Not sure we can get there, but recursive type inference should be
able to do quite a lot.

```
fun getAThing(a)
  ret a + 1
```

In this example we might infer that 'a' is an Int because of the + operation, and then we can
infer that the return type is Int because the result of + is used on a ret statement.

# YAFL (Yet Another Functional Language)

I've read about so many programming languages and worked in a few of them. C, C++, Python, Kotlin,
C#, Java, Modula-2, Miranda, BBC Basic, Visual Basic, various forms of assembly language. I love
watching presentations about Rust and Haskell on t'internet but haven't had a chance to dabble yet.
I have read so many books and papers on compiler design, on register allocators, on optimisation
strategies.

What I am trying to say here, is that I love this stuff, and that I have formed my own opinion
about what a good programming language should be. This project is me trying to bring it to life.

# AI/LLMs

I have re-started this project many times over the years, switching the language I used to build
the compiler, re-doing the parser, and trying to belanance work, family and YAFL. It was becoming
an issue and I really wanted to share this work with somebody, but there was nobody. Until Claude
came along. Claude is my junior developer buddy. I can point Claude at some work, and let Claude
get on with it whilst I have family time. It has accelerated the development of this project
tenfold at least, but at a cost. I have less control over the output quality. I still have control
but that takes time, so I find myself compromising and just merging, with a mental promise to
review/fix regressions later.

Before I started using Claude I had the GC complete, the parser was quite mature and robust but
language features were getting harder and harder to introduce to the compiler. Plus tests were
thin on the ground. This is where I started using Claude, and slowly trusting it bit-by-bit to
do small constrained jobs, and slowly increasing the scope of those jobs as my trust improved.

Recently I have been able to leave it dealing with some quite complex refactors, or adding a
big feature, and with good guidance it does a good job. Then I review, give review feedback
and it fixes those issues. It's working quite well. Case-in-point the async IO module was
specified by me, for simplicity and portability above all other things, and implemented by
Claude.

Does this mean that I'll accept AI PRs. No. Only human PRs. My philosophy is, if you aren't
willing to take personal responsibility for changes, then I can't trust you. It's the same
approach my employer is taking, each individual is free to use AI, but the PR is done by a human
who takes personal responsibility for it.

# Key language features

- Read-only by default. Rust certainly gets this right, a highly functional language in my
  opinion. It should be hard to declare something as mutable not just for correctness, but also
  because it has consequences for efficiency.
- Code layout as syntax. A lot like python, indentation means something, it means that what follows
  is a block that belongs to the first statement. No semi-colons, no curley braces, just tidy code.
- Ambiguity is an error. You can declare what you like. You can even declare the same function with
  the same parameters multiple times, and the compiler will not complain. If you try to call that
  function, then you'll have problems. In nearly all evaluations the compiler treats any kind of
  referential ambiguity as an error.
- Functions are data. You can reference a function by name, and what is returned is a function. You
  can pass that around, store it, and call it later. Most modern popular languages do this.
- There is no guarentee of the order of evaluation. Left to right, right to left. A sequence of
  lets could be swapped around, or even run in parallel. There is a basic assumption that nothing
  has side effects and it is safe to re-order the code whilst respecting chained dependencies. No
  concept like Haskell has of the IO monad. If code is written that has side effects, the programmer
  must be aware and must code defensively. For the vast majority of non-library code, this should
  not be a concern.
- Linear types enforce sequential logic and cleanup for IO.
- Integers have no min/max. They are unbounded, similar to python.
- Traits. Borrowed from Rust, this is a brilliant way of thinking about generics, much better
  than the Java/Kotlin/C# approaches. Declare a local generic name TVal, and then express that it
  must support numeric functions, or certain IO functions, or maybe functions that can stringify
  it. Very powerful.
- OO. We still have the OO concepts from C#/Java. Classes, interfaces, inheritance, overloading.

# Key runtime features

- All functions are async. Think about C# and the async keyword, it spreads like a virus throughout
  a code-base, until you're wondering why the keyword even exists. In YAFL everything is async
  under the covers unless the compiler can prove otherwise. The programmer is ignorant to this fact.
- Any tuple creation could be transformed into parallel execution by the compiler. All function
  calls have a tuple construction for their parameters. Any sequence of lets might be transformedd
  into a tuple construction by the compiler. It is free to make these decisions for any reason, but
  will take into account a cost/benefit estimator.
- Worker threads only do CPU work. All IO is async.
- Heap is GC managed. There is no concept of a finalizer or of the C# IDisposable. This need is
  covered by linear types at the language level.
- Integers and strings are heap managed, unless they are small enough to be packed into a pointer
  sized object. The runtime uses this, and with some GC help, to avoid heap allocations.

# Garbage Collector

This is a concurrent compacting mark sweep garbage collector. There is no generational optimisation
here, so it just walks the entire heap every time. For now I need something that works without
pausing the runtime, and this is it.

There is no GC thread. All work happens on the main worker threads as a side-quest of any heap
allocation calls, and of checkpoint code that is injected into the generated code from the YAFL
compiler.

There is a strong assumption that the worker threads are running YAFL code, which is known to
yield often. That matters because the start/end of a GC is marked by all worker threads passing
a checkpoint.

All GC managed heap must be comprised of well behaved well structured YAFL objects, with a
descriptor that tells GC exactly where to find pointers. Not things that might be pointers, but
fields in the heap that are definately pointers to other well structured objects. However, there
is a global rule that allows the YAFL runtime to pack other data into pointer fields. If any of
the lower bits are not zero, then the GC will skip the pointer.

Compaction only works on read-only objects. This is defined as an object that is initialised only
and where that initialisation is completed before any other call to a heap allocation function
or to a check-point function. This is the window of opportunity where the runtime can be confident
that this newly allocated object is not being compacted. During compaction two copies of a read-only
object may exist at the same time whilst GC is re-writing referencing pointers. This keeps the
runtime safe and happy. At the end of GC, after the all threads have gone through at least one
cycle of returning to the outer event loop, GC is in a known safe state where none of the old heap
is referenced and then releases those pages. This is yet another assumption that we are running
with the YAFL compiler, where everything is read-only by default.

# IO

Eventually I want IO to have platform optimised modules, but that's not an early requirement.
Right now async IO uses the C stdio API as a standard platform agnostic way of doing IO and
a thread pool separate from worker threads to do the actual IO. It's simple, it adds overhead
but it gets the ideas in there early. Later we can use io_uring on Linux, and whatever platform
specific accelarated APIs exist when porting. On embedded devices this then also maps nicely
into an interrupt driven model.

# Build and use

Requirements.
* Python 3.12+ (the compiler uses PEP 695 generics and `tomllib`)
* PyInstaller — `pip install -r compiler/requirements.txt` (build-time only; it packages the compiler into the `yafl` binary)
* CMake
* A C compiler like gcc, clang or msvc

The compiler has no third-party *runtime* dependencies; only the build step needs
PyInstaller. Installing also lays down the `System` library as
`${CMAKE_INSTALL_PREFIX}/lib/yafl/system.yl`, which the `yafl` binary discovers
automatically (override the search path with the `YAFL_PATH` environment variable).

Build and install everything — the `yafl` compiler and the `System` library — from
the repository root:
```
cmake -B build -DCMAKE_INSTALL_PREFIX=/usr/local
cmake --build build -j
sudo cmake --install build
```
This installs `yafl` to `<prefix>/bin` and the `System` library to
`<prefix>/lib/yafl/system.yl`; nothing is written to `<prefix>/include` or the
`<prefix>/lib` root. On Windows, drop `sudo` and pick a writable
`-DCMAKE_INSTALL_PREFIX`.

## Running the tests

### The full protocol, one command

`full_protocol.py` is the correctness gate — build, the CTest gate, and every
example compiled and run against a fixture — printing one line per stage:
```
python3 full_protocol.py                    # against the self-hosted compiler (the default)
python3 full_protocol.py --compiler python  # against the Python compiler
python3 full_protocol.py --only ctest,examples
python3 full_protocol.py --keep-going       # every stage, fail at the end
```
The two compilers have parity, so either is a drop-in replacement for the
other: `--compiler` picks the one every behaviour test and example runs
against. The CTest gate starts by having the Python compiler build the
self-hosted one (`build/ybootstrap`, keeping the C it emitted), runs the
compiler suite and the YAFL `[test]` folders, and ends with ONE self-compile:
the port compiles its own sources and must reproduce that C byte for byte.
Each run tees its output to `build/protocol-runs/<timestamp>/`. It is also what
CI runs (`.github/workflows/full-gate.yml`).

### Speed, separately

`speed_protocol.py` is the measurement step, run after a green full protocol:
the port built through the -O3 pipeline, then a timed best-of-three
self-compile (wall time and peak RSS per leg, every run byte-identical).
```
python3 speed_protocol.py
python3 speed_protocol.py --only o3_timed   # re-time an existing -O3 build
```

### The test set alone

The whole test set is wired into CTest. From a configured build, `--target
check` builds everything (so the runtime archive and C test binaries exist) and
runs it all:
```
cmake -B build                                  # -DYAFL_TEST_COMPILER=python to test that one
cmake --build build --target check
```
Or drive CTest directly after a build (`cmake --build build && ctest --test-dir build`).

Behaviour tests come in two kinds:

* **YAFL `[test]` folders** — `compiler/stdlib_tests/` and `compiler/yafl_tests/`.
  Each folder is built into one test binary with `--test` by the compiler under
  test; each file is its own unit with its own namespace. Write new behaviour
  tests here: one compile serves the whole folder.
* **The Python suite** — `compiler/tests/`. Its compile-and-run tests drive the
  compiler under test through its command line (`YAFL_COMPILER=port|python`,
  default `port`); the tests that reach into `pyast`/`lowering`/… are unit
  tests of the Python implementation itself.

To run the Python suite by hand from `compiler/`, point it at a built port and
runtime archive:
```
cd compiler
YAFL_BOOTSTRAP_BIN=../build/ybootstrap YAFL_LIBYAFL_A=../build/yafllib/libyafl.a \
PYTHONHASHSEED=0 unittest-parallel -j 0 -s tests -t .
```
`YAFL_COMPILER=python` runs the same tests against the Python compiler.

Compiled programs are statically linked against the runtime, so they need no
`LD_LIBRARY_PATH` or installed `libyafl.so` to run.

You can test that the compiler is installed and working like so:
```
cd examples
yafl -o test hellowWorld.yafl
./test
```

If you like, you can examine the intermediate C code like so:
```
cd examples
yafl -c test.c hellowWorld.yafl
more test.c
```

## Editor support

`vscode-yafl/` is a small, purely declarative Visual Studio Code extension for
`.yafl` files: a TextMate grammar for syntax highlighting (kept in step with
`compiler/parsing/tokenizer.py`), comment/bracket/indentation configuration, and
a handful of snippets. It carries no language server and no bundled code.

It builds with its own standalone CMake project (like `examples/`, it is not part
of the top-level build):
```
cmake -S vscode-yafl -B vscode-yafl/build
cmake --build vscode-yafl/build --target install-extension
```
`install-extension` symlinks `vscode-yafl/` into `~/.vscode/extensions/yafl-0.1.0`
(override the parent directory with `-DYAFL_VSCODE_EXTENSIONS_DIR=...`); run
**Developer: Reload Window** in VS Code afterwards. Because it is a symlink,
later grammar edits take effect on the next reload with no rebuild. Other
targets: `uninstall-extension`, and `package-vsix` to build a `.vsix` via
`npx @vscode/vsce` (needs Node.js). See `vscode-yafl/README.md` for details.



