# `[test]` — the compiler builds the test binary

Status: PROPOSAL for discussion. Nothing implemented.

    yaflc --test -o build/mytests src/          # build the test binary
    ./build/mytests                             # run everything
    ./build/mytests --list                      # what tests exist
    ./build/mytests --format json               # for an IDE

You annotate a function; the compiler finds it, builds a registry, and
synthesises the runner. No registration boilerplate, no discovery-by-naming-
convention, no separate test-main to keep in sync.

---

## 1. The thing to settle first: a failing test is a VALUE, not an event

Every mainstream test framework signals failure by throwing, longjmp-ing, or
aborting. YAFL has none of those, and should not grow one for this. So the
first question is not "what syntax" but "what does a test *return*".

**A test returns an outcome union.**

    fun [test] additionCarries(): System::None|TestFailure

`System::None` means it passed. A `TestFailure` means it did not, and carries
why. That single decision does most of the design work, because it makes the
existing `?>` bind operator the assertion combinator for free:

    fun [test("addition carries across the word boundary")]
    additionCarries(): System::None|TestFailure
      ret assertEq<Int>(maxWord() + 1, expectedCarry(), "carry into word 2")
        ?> (:System::None) => assertEq<Int>(0 - 1, negativeOne(), "borrow out")
        ?> (:System::None) => assertTrue(isNormalised(zero()), "zero normalised")

`?>` already means "thread the success member, pass everything else through
unchanged" (`stdlib/result.yafl`). Applied here it gives **short-circuit on
first failure**, which is exactly test semantics, with no new machinery and no
new operator. The first `TestFailure` produced becomes the function's result
and the remaining assertions never run — which matters when a later assertion
would be meaningless, or would crash, once an earlier one has failed.

This is the part I would most like ruled on, because everything else follows
from it. The alternative — assertions that abort the process — is worse for a
specific reason: one failing test would take the whole run with it, and you
would lose the results of every test that had not yet run. A framework whose
first failure destroys the rest of the report is a framework people stop
trusting. Returning a value keeps every test independent.

**Verified, not assumed.** The short-circuit claim was checked with a spike
compiled and run through the real compiler, not reasoned about on paper. The
subtlety is that reporting the correct message does *not* demonstrate
short-circuiting — the first error propagates to the result either way — so
the skipped assertions have to be observable. With a `noisy()` assertion that
prints when evaluated, placed after a failing one:

    allPass    : ok
    firstFails : FAIL first (expected 3 got 2)
    middleFails: FAIL middle (expected 6 got 5)

No `[ran: ...]` line appears anywhere: every assertion after a failure was
genuinely skipped, while `allPass` still ran its chain to the end. `?>` does
what §1 needs it to, with no changes to the operator.

### Why not `Bool`

`ret false` tells you a test failed and nothing else. The message is the
product. `TestFailure` carries it:

    class TestFailure(message: System::String, detail: System::String)

`assertEq` fills `detail` with the actual-versus-expected rendering, so the
report can say *what* was wrong, not merely *that* something was.

### The assertion API

Thin, and honest about what it can do:

    fun assertTrue(cond: System::Bool, why: System::String): System::None|TestFailure
    fun assertEq<T>(actual: T, expected: T, why: System::String): System::None|TestFailure
        where BasicEquality<T>
    fun fail(why: System::String): TestFailure

`assertEq` needs `BasicEquality<T>` to compare and something render-shaped to
report. Derived equality already exists for records; rendering is the open
edge — see §7.

For independent assertions where short-circuiting is not wanted, one
combinator covers it without a chain:

    fun firstFailure(checks: List<System::None|TestFailure>): System::None|TestFailure

Note these are *eager*: `List` construction evaluates every element, so
`firstFailure` reports the first failure but does not prevent the later
assertions from being evaluated. In a pure language that is harmless — no side
effects, no ordering hazard. It is only wrong if a later assertion would
crash on state an earlier one was guarding, and that is precisely when you
should be using `?>` instead. Worth documenting at the call site rather than
pretending the two forms are interchangeable.

---

## 2. Annotation — no new grammar required

Attributes already parse as a generic `[name]` / `[name(expr)]` dictionary
(`parsing/parser.py`, `__parse_attributes`). `[test]` and `[test("...")]` are
free; nothing in the tokeniser or parser changes.

    fun [test] roundTripsEmpty(): System::None|TestFailure
    fun [test("a surrogate pair survives encode/decode")] roundTripsAstral(): ...

**The contract**, checked where the other attribute contracts are checked
(`pyast/statement/function.py`):

- zero parameters;
- return type exactly `System::None|TestFailure`;
- not `[foreign]` (there is no body to run);
- the argument, if present, is a string literal — the description.

Each violation is a CHECK error naming the function, in the style of the
existing `"[tail] takes no arguments"` diagnostics.

### The gap this must close first

**Unknown attributes are currently silently ignored.** There is no rejection
path — `function.py` tests for each known name and never asks whether an
attribute it does not recognise was supplied. So `[tset]` today compiles
clean and does nothing.

For most attributes that is a missed optimisation. For `[test]` it is a
**silently missing test**: the binary builds, the run is green, and the
coverage you think you have does not exist. That is the same failure mode as
the ungated compiler warnings — a check that appears to have run and did not.

I would not ship `[test]` without rejecting unknown attributes first. It is a
small change (validate the attribute dictionary against a per-statement-kind
allowlist) and it is worth doing on its own merits regardless of this
proposal.

### Async tests work, and cost nothing

A test may do IO:

    fun [test("a written file reads back byte-identical")]
    fileRoundTrip(): System::None|TestFailure
      ret writeFile(tmp(), payload())
        ?> (:System::None) => readFile(tmp())
        ?> (c: System::String) => assertEq<System::String>(c, payload(), "content")

Because tests are ordinary functions called from a synthesised ordinary
function, `async_lower` handles suspension exactly as it does anywhere else.
No `[sync]` requirement, no synchronous await, nothing special. This falls out
of §3 and is the main reason for doing it that way.

---

## 3. How the compiler builds it — synthesise YAFL, not IR

Today `compile_project` requires **exactly one** `main`: a
`Namespace::main` returning `bigint` with no parameters (`__is_main_function`),
and errors on none or several. `__create_entry_point` then hand-builds an IR
`Function` that calls it and bridges the sync/task result.

Under `--test` that requirement inverts:

- a `main`, if present, is **ignored** — you want to test a program that has
  one, so its presence is not an error;
- if there are **zero** `[test]` functions, that IS an error. A test binary
  with nothing in it is the "gate ran and checked nothing" failure again, and
  must not exit 0. (Compare the existing `FAIL_REGULAR_EXPRESSION` guard on
  `compiler_suite`, which exists for exactly this reason.)

**The runner is synthesised as YAFL/AST and fed through the normal pipeline —
not hand-built as IR.** This is the load-bearing implementation decision.
`__entrypoint__` is hand-built and is consequently skipped by `async_lower`,
special-cased in `inlining.py`, and special-cased again in `ssa_validate.py`.
Every hand-built function buys another special case in every pass. Worse, a
hand-built runner would have to *reimplement task chaining* to sequence tests
that suspend — re-deriving, badly, what `async_lower` already does.

Synthesising a `main` instead means the runner is an ordinary function:
monomorphisation, inlining, async lowering, SSA validation and trim all treat
it as ordinary code. The async-test support in §2 is then not a feature anyone
implements; it is the absence of a restriction.

Sketch of what gets synthesised — the shape, not the final text:

    fun __testMain(): System::Int
      let cases = List<TestCase>(
        TestCase("Json::roundTripsEmpty",  "", "tests/json.yafl", 42, () => roundTripsEmpty()),
        TestCase("Json::roundTripsAstral", "a surrogate pair …", "tests/json.yafl", 51, () => roundTripsAstral()))
      ret System::Test::run(cases, System::args())

`System::Test::run` is **ordinary YAFL**, not compiler-generated: it parses the
arguments, selects and sequences the cases, renders the output and returns the
exit code. Only the registry literal is synthesised. That keeps the generated
surface to a single list — the part that genuinely requires compiler knowledge
— and puts the runner's behaviour somewhere it can be read, reviewed and
tested like any other code.

### Where it lives: its own library, brought in by `import`

**Not in `stdlib/*.yafl`.** The dev System library is assembled from *every*
file in that directory as one library (`libraries.dev_system_library`), and
loading is per-library, not per-file — so anything dropped in there is parsed
into every compilation in the tree. `trim` would drop the unused code from the
output, but every program would still pay to parse it, and the reference
outputs the suite compares would churn for a feature almost no program uses.

So `System::Test` is its own library. **Nothing special is needed to reach it
— an `import` is all it takes** (USER RULING). The loader is already a
worklist over *referenced namespaces*: whatever names `System::Test` pulls the
library in, and a program that never mentions it never sees it. A test file
imports it like any other library; the synthesised main of §3 references
`System::Test::run`, which is itself enough to load it. No `--test`-specific
library wiring, no special-casing in the loader.

Consequences to handle:

- **`trim.py` must root the registry.** It currently roots
  `__entrypoint__` alone; under `--test` the synthesised main is the root, and
  a `[test]` function reachable only from the registry must not be collected.
- **Tests can live beside the code they test.** In a normal build nothing
  references a `[test]` function, so trim drops it and it costs no bytes in
  the shipped binary. No separate test tree required — though nothing stops
  one.
- **`--test` implies its own object set**, so it must not silently reuse a
  cached non-test build.

---

## 4. The binary's command line

    mytests                          run every test, human output
    mytests Json::roundTripsAstral   run exactly these (repeatable)
    mytests --filter 'Json::*'       run matching (glob, not regex — see below)
    mytests --list                   registry, one per line, with descriptions
    mytests --format human|json|junit
    mytests --output FILE            write the machine format to FILE

Arguments parse in YAFL via the existing `System::args()`, so this is stdlib
code, not runtime C.

Glob rather than regex for `--filter`: `Json::*` is what people type, and it
sidesteps the fact that `::` and most regex metacharacters collide badly in a
shell. `regex.yafl` exists if we later decide otherwise, but the default
should be the thing that does not need escaping.

**Exit code is 0 or 1. Never a count.** Exit codes are 8 bits, and a suite
with 256 failures that exits 0 is a green build that should have been red —
the trap already recorded in `HANDOVER.md` ("exit codes are 8-bit; println
totals over 255"). Totals go in the report; the exit code answers one
question.

Reserve `2` for "the runner itself failed" — bad arguments, an unknown test
name, a filter matching nothing. That last one matters: `--filter` typos
otherwise look identical to success, which is the silent-gap failure mode
again. A filter that selects zero tests must be an error, not a green run of
nothing.

---

## 5. Output: one event stream, two renderers

You asked whether the IDE format and the human format can be the same thing.
**They should not be the same output, but they must be the same *events*.**

The failure mode to design against is a runner whose pretty output and machine
output are produced by separate code paths and drift, so the IDE shows green
while the terminal shows a failure. So: the runner emits a single ordered
event stream internally, and a renderer turns it into one of the formats.
Human and machine cannot disagree, because there is one source of truth.

Events, in order: `run_start`, then per test `test_start` / `test_end`, then
`run_end`.

**`--format json` — JSON Lines, one object per event, flushed as it happens.**
Streaming, not a document assembled at the end. IDEs want to mark a test green
the moment it passes and show progress on a long run; a final blob makes the
UI dead until the run completes, and gives you nothing at all if the run is
killed. Line-oriented also means it stays greppable and survives `tail -f`.

    {"event":"run_start","count":128}
    {"event":"test_start","id":"Json::roundTripsAstral"}
    {"event":"test_end","id":"Json::roundTripsAstral","status":"pass","cpu_ns":412000}
    {"event":"test_end","id":"Json::roundTripsEmpty","status":"fail",
     "message":"content","detail":"expected \"\" got \"\\u0000\"",
     "file":"tests/json.yafl","line":51,"cpu_ns":88000}
    {"event":"run_end","passed":127,"failed":1,"cpu_ns":9310000}

`file` and `line` come from the `line_ref` the compiler already has on every
statement, and are what let an IDE turn a failure into a clickable location.
That is most of the integration value and it is nearly free — the information
exists at synthesis time.

**`--format human` — the default.** One line per test, failures with detail
and location, a summary at the end. Same events, different renderer.

    Json::roundTripsEmpty                          FAIL
        content: expected "" got "\u0000"
        at tests/json.yafl:51
    Json::roundTripsAstral                         ok      0.4ms

    127 passed, 1 failed

**`--format junit`** — a final XML document for CI systems that only speak
JUnit. Not streaming, by nature. Worth having, not worth designing around.

**`--list`** follows the same split: human by default, and
`--list --format json` emits the registry as JSONL (`id`, `description`,
`file`, `line`) so an IDE can populate a test tree without running anything.
That is the "list the tests with descriptions" parameter, and sharing the
format machinery with the run output means it costs almost nothing.

---

## 6. Determinism and timing

The standing rule is no flaky tests, with CPU-time metering rather than wall
clock — this box is a shared Proxmox host under heavy co-load, so wall time is
not a stable number.

- **Deterministic order**, sorted by test id. No randomisation, no
  shuffle flag. Order-dependent tests are a real bug, but finding them is a
  separate tool, not a default that makes every run irreproducible.
- **Serial execution in v1.** Parallelism multiplies the runner's complexity
  and is the main source of flakiness in other frameworks. The compiler's own
  suite gets its parallelism from sharding *across processes*, which works the
  same way here — run several test binaries, or the same one with disjoint
  filters — without the runner needing to be concurrent at all.
- **`cpu_ns` per test**, from `CLOCK_PROCESS_CPUTIME_ID`. The runtime already
  calls `clock_gettime` at 17 sites across five files but exposes no clock to
  YAFL at all, so this needs one small foreign function. CPU time also makes a `--timeout` (§7)
  meaningful under co-load, where a wall-clock timeout would fire on a busy
  machine rather than a hung test.

---

## 7. Open, and deliberately not designed here

- **Rendering values for `assertEq` detail.** Needs a `String(T)`-shaped
  constraint alongside `BasicEquality<T>`, or the report says "not equal" and
  makes you rerun under a debugger. This is the weakest part of the sketch and
  probably the next thing to settle after §1.
- **Setup/teardown and fixtures.** Purity means most of what fixtures exist
  for is just a function call. Temporary files and processes are the real
  case, and interact with `[linear]` and drops. I would ship without and add
  it when a concrete need names its shape.
- **Expected failures.** The Python suite has one deliberate
  `expectedFailure` kept as a feature record, so the concept earns its place —
  `[test(expect: fail)]` or similar. Grammar already permits the argument.
- **Parameterised / table-driven tests.** A `[test]` returning many outcomes
  changes the registry from one id to many, and the id scheme has to stay
  stable for IDE re-run. Worth doing, not worth guessing at now.
- **`--timeout`.** Wants a watchdog and a way to kill a suspended task
  without corrupting the heap; a design question for the async model, not for
  the test framework.
- **Replacing the Python suite.** Not a goal of this proposal, and it should
  not become one implicitly. The compiler's suite is Python `unittest`
  comparing two compilers byte-for-byte; that is a different problem, and the
  byte-parity gates are the compiler's core contract. This framework is for
  YAFL programs — including, eventually, parts of the port, but that is a
  later conversation with its own evidence.

---

## 8. Staging

Each step is independently useful and independently reviewable:

1. **Reject unknown attributes.** Independent of everything else, and a
   prerequisite for trusting `[test]` (§2).
2. **`System::Test`**: `TestFailure`, `TestCase`, the assertions, `run`, the
   renderers — ordinary YAFL in its own library, reached by `import`. Testable
   by hand with a written-by-hand registry before the compiler synthesises
   anything, and it perturbs no existing program.
3. **`[test]` recognition and its contract errors.** No codegen yet — the
   attribute is validated and otherwise inert.
4. **`--test`**: collect the annotated functions, synthesise the registry and
   main, root it in `trim`. This is the only genuinely compiler-side step, and
   by this point the runner it calls is already working.
5. **`--format json` and `--list --format json`**, then an IDE integration
   against the event schema.

Step 2 is where most of the behaviour lives and needs no compiler change at
all, which is a good sign for the shape: the compiler's whole job is to write
down a list of functions it already knows about.

---

## 9. Status

§1 is settled and **verified by spike** (see the end of §1) — the assertion
model and `?>` short-circuiting work as described, compiled and run.

§3's placement question is settled by user ruling: a unique library, reached
by `import`, with no special loading machinery.

**Step 1 is DONE, in both compilers, with parity verified.** Unknown attributes
are now a CHECK error rather than a silent no-op: a `_KNOWN_ATTRIBUTES`
allowlist per statement kind plus `unknown_attribute_errors` on
`NamedStatement` in the Python compiler, and `unknownAttrErrs` with an
`isKnown*Attr` predicate per kind in the port's `check_stmt.yafl`.

The allowlist was derived by compiling the whole bootstrap port with the check
live — 104MB of C, zero false rejections — not from the probe alone, whose job
was only to say where to look. Both compilers were then run on the same typo
file and emit identical messages at identical positions:

    [4:5]   unknown attribute [tset] on a function
    [7:7]   unknown attribute [finl] on a class
    [9:6]   unknown attribute [hashd] on an enum
    [11:11] unknown attribute [linr] on a typealias
    [4:5]   unknown attribute [cnst] on a let

Python reports in SOURCE order rather than sorted, so a declaration carrying
two unknown attributes agrees with the port without either side needing a sort.

**All six statement kinds are checked, including trait instances.** The first
cut of this did NOT check instances: the port's `PsTraitInstance` kept only
`tiAmbient: Bool` and its parser discarded the attribute list, so I removed the
check from the Python side too and called the resulting agreement "parity".
That was wrong — levelling down leaves both compilers weaker than one of them
was and converts a port-side bug into a permanent language limitation. Fixed
in `ad56be7` by adding `tiAttrs` to the port node (second, no default, so the
four rebuild sites must each pass it through rather than silently defaulting
one to empty) and restoring the check on both sides. A second gap surfaced in
passing: the port's `eqStmt` did not compare `tiAttrs`, while Python's
dataclass equality compares `attributes` structurally.

Left as an open item, deliberately and stated rather than hidden: **neither**
compiler's `astdump` prints instance attributes, so the two dumps agree today.
Making both print them would improve the comparison instrument but changes
reference outputs, so it wants its own change.

**Steps 2, 3, 4 and 5 are DONE.**

- **2** — `System::Test` at `compiler/libs/system-test/`, validated first with a
  hand-written registry, which is exactly what step 4 went on to synthesise.
- **3** — `[test]` recognised and contract-checked in both compilers
  (`74fdac7`), verified by DIFFING their output on the same bad file rather
  than reading both. The control matters as much as the failures: a valid
  `[test("fine")]` produces no error, so this is not a check that rejects
  everything and happens to agree.
- **4** — `--test` in Python, `ctest`/`c1test`/`c2test`/`c3test` in the port
  (`a1beb4c`). **Byte-identical output: 402,855 bytes of C from both.**
- **5** — streaming JSONL, `--list --format json`, and the human renderer, both
  fed by one event stream.

Two traps worth keeping. The port's `parseSingle` hardcodes the filename `"x"`
while Python names the generated source `$test_main.yafl`; the filename feeds
`hash6`, which feeds the generated names, which feed the emitted C, so the two
would have disagreed byte-for-byte on identical input. And comparing the two
compilers requires feeding them the SAME FLAT SORTED file set, the way
`bootstrap_c_base.py` does — Python's library-discovery order is
libraries-then-user while the port sorts every part by filename, and an earlier
comparison differed in inline counters and union discriminators purely because
of that. The honest read of that diff was "my harness is invalid", not "the
port is broken".

Remaining: JUnit XML (§5 calls it worth having, not worth designing around);
per-test `cpu_ns`, which needs a foreign clock since the runtime exposes none
to YAFL; and installing the library for released builds, since it is dev-tree
only today. The open items in §7 stand — `assertEq` value rendering is still
the weakest part, and there is no `assertEq<T>` because that wants a
`String(T)`-shaped constraint alongside `BasicEquality<T>`.

