# Structured logging and runtime metrics — design

Status: DESIGN AGREED (§11), nothing implemented.

A YAFL-only facility, implemented mostly in `yafllib`, for measuring
performance and logging facts at runtime. The Python compiler is out of scope —
it already has what it needs.

Every line carries an accurate timestamp, a context, and a message. **YAFL code
never sees a date, a time, or a duration** — the runtime stamps and measures.

---

## 1. Why the no-clock rule shapes the whole design

Withholding the clock from YAFL decides how durations work. A YAFL program
cannot time anything itself, so **the runtime owns spans**: YAFL says "this span
started" / "this span ended", and C keeps the monotonic start, computes the
elapsed and prints it. The handle returned to YAFL is an opaque token, not a
time.

That is a feature:

- durations are always measured the same way (`CLOCK_MONOTONIC`), so they are
  comparable across subsystems and runs;
- no pass can acquire a dependency on wall-clock time, which would make
  compilation non-deterministic — the byte-identical C contract forbids it;
- no timestamp can leak into emitted output.

## 2. What the runtime already has (build on it)

| facility | where |
|---|---|
| `clock_gettime(CLOCK_MONOTONIC / CLOCK_PROCESS_CPUTIME_ID)` | `gc_stats.c`, `thread.c`, `object.c` |
| `[GC …]` line-per-record convention on stderr | `gc_stats.c` |
| `thread_local int32_t _my_thread_id` + accessor | `thread.c:54` |
| env-gated instrumentation (`YAFL_DURATION`, `YAFL_GC_STATS`) | `thread.c`, `object.c` |
| `string_to_cstr(obj, &local, &len)` — short strings use a caller buffer | `string.c` |
| `[foreign(...), impure, sync]` declaration form | `stdlib/console.yafl:3` |
| `{N}` 1-indexed slot syntax, per-arity overloads | `stdlib/format.yafl` |

## 3. Levels are `Int32`

A level is a plain `Int32`. The runtime maps the standard values to display
names; anything else prints as its number, so intermediate levels are usable
without touching the runtime.

| constant | value | printed |
|---|---|---|
| `logTrace` | 10 | `TRACE` |
| `logDebug` | 20 | `DEBUG` |
| `logInfo`  | 30 | `INFO`  |
| `logWarn`  | 40 | `WARN`  |
| `logError` | 50 | `ERROR` |

Declared as `let logDebug: Int32 = 20i32` in `System::Log`, following the
`let mask32: Int = …` convention. Named `logX` rather than bare `debug`
because `System::Log` will be imported widely and a bare `debug` would collide
with user code — and in this language ambiguity is an error, not a warning.

## 4. The API: format string plus 0–3 arguments

The level test lives **inside** the call. Arguments are values the caller
already has — an `Int` or a `String` — so a suppressed call costs one foreign
call and an integer compare, with no allocation. When the level passes, C
expands the format; still nothing is allocated on the YAFL heap.

Slots are `{1}`, `{2}`, `{3}`, exactly as `stdlib/format.yafl` — one slot
syntax in the language, not two.

```yafl
log(logDebug, "generics", "monomorphised {1} functions in {2}", n, passName)
log(logInfo,  "async_lower", "fixpoint converged")
log(logWarn,  "gc", "page {1} pinned during compaction", pageIndex)
```

### Overload matrix — 15 in total

Arity 0–3, each argument `Int` or `String`. Each YAFL overload maps to one C
symbol, since C has no overloading; the suffix spells the signature.

| arity | YAFL signature (after `level: Int32, context: String, fmt: String`) | C symbol |
|---|---|---|
| 0 | — | `yafl_log` |
| 1 | `Int` | `yafl_log_i` |
| 1 | `String` | `yafl_log_s` |
| 2 | `Int, Int` | `yafl_log_ii` |
| 2 | `Int, String` | `yafl_log_is` |
| 2 | `String, Int` | `yafl_log_si` |
| 2 | `String, String` | `yafl_log_ss` |
| 3 | `Int, Int, Int` | `yafl_log_iii` |
| 3 | `Int, Int, String` | `yafl_log_iis` |
| 3 | `Int, String, Int` | `yafl_log_isi` |
| 3 | `Int, String, String` | `yafl_log_iss` |
| 3 | `String, Int, Int` | `yafl_log_sii` |
| 3 | `String, Int, String` | `yafl_log_sis` |
| 3 | `String, String, Int` | `yafl_log_ssi` |
| 3 | `String, String, String` | `yafl_log_sss` |

```yafl
fun [foreign("yafl_log"),     impure, sync] log(level: Int32, context: String, fmt: String): Int
fun [foreign("yafl_log_i"),   impure, sync] log(level: Int32, context: String, fmt: String, a: Int): Int
fun [foreign("yafl_log_s"),   impure, sync] log(level: Int32, context: String, fmt: String, a: String): Int
fun [foreign("yafl_log_ii"),  impure, sync] log(level: Int32, context: String, fmt: String, a: Int, b: Int): Int
…
```

`sync` is load-bearing: logging must never suspend, so it stays callable from
inside the async machinery it is measuring. Returns `Int` because that is the
existing foreign convention (`print_string`); the result is discarded.

**Arity stops at 3** (decided). Beyond that, format two values into one string
at the call site and accept the cost, or emit two lines. The matrix can grow to
4 later if evidence says it is needed; adding an arity is purely additive —
16 more overloads and 16 more C symbols, no change to anything already written.

## 5. Metrics: counters and spans

Neither takes a format, so neither needs the matrix.

```yafl
fun [foreign("yafl_log_span_begin"), impure, sync] spanBegin(context: String, name: String): Int
fun [foreign("yafl_log_span_end"),   impure, sync] spanEnd(span: Int): Int
fun [foreign("yafl_log_count"),      impure, sync] count(context: String, name: String, n: Int): Int
```

Counters aggregate in C and dump once at exit, so they are safe in a hot loop —
the right tool for anything per-op or per-function, where even a suppressed log
call is too much.

## 6. C implementation — `yafllib/log.c` (+ `log.h`)

Rules the implementation must hold to:

1. **No YAFL-heap allocation, ever.** Format into a `thread_local char[4096]`.
   Strings arrive via `string_to_cstr` with a stack buffer. This also keeps the
   API safe to call from inside the GC later.
2. **`Int` is arbitrary precision.** DONE — `integer_to_cstr(obj, buf, size)`
   is in `integer.c`, declared in `yafl.h`, with 10 unit tests. The stdlib's
   `String(Int)` builds on the YAFL heap via StringBuilder, which a logger must
   never do; this renders into the caller's buffer and allocates nothing. It
   handles tagged literals and multi-limb magnitudes, and when the exact value
   does not fit it writes `<int:~N digits>` rather than a truncated numeral —
   a cut-off number reads as a genuine smaller one, which is the worst outcome
   in a log.
3. **One `write(2)` per fully-formatted line**, to a dedicated fd — never
   through the async IO path, since `io_t` is single-threaded with one task per
   handle and logging must work from GC workers and `__parallel__` tasks.
4. **Timestamp inside the emit**: `CLOCK_REALTIME` for the line; spans use
   `CLOCK_MONOTONIC` so they are immune to clock adjustment.
5. **Context resolution is cached** — a context string interns to a small id
   carrying its effective level, so the suppressed path is an array index and a
   compare.
6. **Truncate, never grow.** Over-long messages are cut with a `…` marker;
   logging must not be able to change allocation behaviour.

## 7. Line format

```
2026-08-01T18:31:51.123456Z INFO  t03 generics    monomorphised 4812 functions
2026-08-01T18:31:52.884210Z SPAN  t00 async_lower liveness 1.284s
2026-08-01T18:34:07.001991Z COUNT t00 staticinit  siReferencingFn.sweeps 12182
```

ISO-8601 UTC with microseconds, fixed-width level, thread id, fixed-width
context, then the message. Fixed columns so `sort`, `awk` and `grep` work
without a parser.

## 8. Destination: a file, derived by default

Logging goes to a FILE, not stderr — a build tool's stderr is already carrying
diagnostics, and metrics that interleave with them are hard to read and easy to
lose down a pipe.

The path is derived unless overridden:

    ${YAFL_LOG_DIR}/yafl-<program>-<YYYYMMDD-HHMMSS>-<pid>.log

- `<program>` is the basename of argv[0], so the file says what produced it.
- The timestamp and pid together make concurrent runs collision-free — several
  compiles in parallel is the normal case when measuring.
- `YAFL_LOG_DIR` defaults to `$TMPDIR`, else `/tmp`. Not the CWD: a compiler
  must not litter a source tree or a build directory.
- `YAFL_LOG_FILE` overrides the whole thing with an exact path, for when you
  want a known name to diff between runs.

When logging is enabled the runtime writes ONE line to stderr naming the file
it opened. A default destination you cannot find is a destination that does not
exist.

The file is opened lazily on the first record, so an enabled-but-silent context
creates nothing. On open failure the runtime falls back to stderr and says so —
logging must never take the program down.

| variable | effect |
|---|---|
| `YAFL_LOG` | global threshold, number or name; default off |
| `YAFL_LOG_<CONTEXT>` | per-context override, e.g. `YAFL_LOG_GENERICS=20` |
| `YAFL_LOG_DIR` | directory for the derived name; default `$TMPDIR` or `/tmp` |
| `YAFL_LOG_FILE` | exact path, overriding the derivation |
| `YAFL_LOG_METRICS` | dump counters/spans at exit even when lines are off |

Default-off for the LEVEL still matters: a released compiler must pay nothing
for logging nobody asked for, and with the level off no file is created.

## 9. What to instrument first (chosen from measured problems)

- **Per-pass spans** in `driver/main.yafl` around each pipeline stage. Nothing
  today can answer "which pass is the self-compile spending its time in" —
  every profile taken in the 2026-08-01 session was either a proxy too small to
  behave like the bootstrap, or a keyhole over 3 minutes of 36.
- **`Lower::Ir::staticinit`** — `siReferencingFn` re-sweeps every function in
  the program per candidate global, and was 28.4% of samples. A counter on
  sweeps plus a span on the pass would have made that obvious immediately.
- **`Lower::Ir::async_lower`** — fixpoint pass counts per function. The liveness
  bug (P growing with function length) needed an instrumented Python build to
  find; a counter would have surfaced it in any run.
- **GC** — fold the existing `[GC …]` output into this format, so runtime and
  compiler metrics share one stream and one clock.

## 10. Phasing

1. `log.c` + `log.h` + `stdlib/log.yafl`: levels, contexts, the 15 overloads.
   Gate: a corpus program that logs must still emit byte-identical C.
2. Counters and spans + exit dump.
3. Instrument the compiler pipeline (§9).
4. Migrate `[GC …]` onto it.

## 11. Decisions

| question | decision |
|---|---|
| namespace | **`System::Log`** |
| arity ceiling | **3** — 15 overloads; more can be added later, additively |
| level type | **`Int32`**, named constants mapping to display names in C |
| level check | **inside the call**, never an `if` at the call site |
| slot syntax | **`{N}`**, 1-indexed, identical to `stdlib/format.yafl` |
| level constant naming | **`logTrace` … `logError`** — safe to import bare |

The last two follow the recommendations in §3 and §4 and are the cheapest to
revisit later: the slot syntax is confined to one C scanner, and renaming the
constants touches only their declarations and call sites.
