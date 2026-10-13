# GC races on aarch64: investigation log and handover

Branch `aarch64-gc` (from `main` at 226a4bc). Work done on a Raspberry Pi 4 (Cortex-A72, 4 cores,
no LSE atomics, Debian 13) from 2026-10-10 to 2026-10-13. Nothing is merged to `main`.

This file is the handover: what was found, what was fixed and on what evidence, what is still open,
and how to reproduce it. Each fix's commit message has the full reasoning and numbers.

## Background you need

- The collector is concurrent snapshot-at-the-beginning (SATB) with **ragged root scans**: each
  thread's stack is scanned at its own safe point, one thread at a time, after the cycle opens
  (`gc_fsa_start` raises `gc_write_barrier_requested`). Marking proper (MARK_SWEEP) starts only after
  every thread's root scan.
- Objects allocated after a thread's root scan land on fresh, **birth-protected** pages that the
  current cycle never scans. Objects allocated between cycle open and the thread's own scan are
  born marked (the "snapshot-smear guard" in `object_alloc_fast_raw`).
- The thread-local nursery (`YAFL_LOCAL_GC`, on by default) and generations (`YAFL_GC_GEN`) sit on
  top. Old pages are skipped by minor cycles.
- The user's sharing contract: shared mutable objects are only touched under their pin (or by CAS);
  immutable fields change only NULL -> value under the pin (`yafl_cas_once`) and are read lock-free.
- Design preference (from the user): fix the collector's broken invariant, not with ad-hoc
  mutator marking; protect the nursery's cost model; put each repeated barrier pattern behind one
  helper; A/B every change on the Pi, including at -O3 (the shipped runtime is -O3).

## Fixed on the branch (oldest first)

| Commit | What | Evidence |
|---|---|---|
| 0c11181 | `test_gc_min2`: holder slots published with release/acquire (test bug). | failed every -O2 run on ARM before |
| e977cd8 | New `test_gc_mesh` (C, sharing-contract-correct shared graph) and `tests/gc_soak.py`. | tooling |
| 3f60663 | aarch64 callee-saved register capture via asm `stp` (clang could not build `object.c`). | clang builds |
| 9f10c36 | Nursery escape barrier: slot load ordered before `gc_local_live` load (`gc_local_live_now`, acquire fence) + full fence after the count RMW. | A72 litmus reordered 22 in 75.5M |
| 5f54bc8 | `YAFL_GC_TRACE` per-page event ring; OOM report. | tooling |
| bc3815c | Mark scanner: full fence after `processed_by_epoch = epoch` (store->load race with markers; marked-but-unscanned objects). | 6/1000 -> 0/1000 |
| d57d32f | Lazy chains: runner decided from the CAS result (was a re-read -> second run through a cleared closure); drain primitives shade removed values. | gc_stress segfaults gone; 11/40 -> 0/40 (nursery off) |
| bf04c5e | `tests/gc_stress.yafl`: compiled-YAFL stress (builders, futures, memoize, shared list); gc_soak builds it. | tooling |
| 7517111 | Lazy chains shade BEFORE deleting (a thread whose scan is done can be preempted between delete and shade). | traced |
| d8f5019 | Late writes to `old` pages also demoted at the end of SCAN_ROOTS (`gc_demote_redirtied`), not just next START. | 8/600 -> 2/600 |
| 16e17cd | `GC_PUBLISH_IN(obj, field, mask)`: insertion barrier AFTER a publishing store (heap twin of `gc_root_publish`). Used by `_queue_push`, `task_on_complete`. | queue move 6/2525 -> 1/2712 |
| 9cdff7d | gc_soak `-O3` variants (opt-in `--builds`). | tooling |
| 9c64e6b | `GC_ROOT_PUBLISH_IN` publishes heap lazy stubs too. | reasoning only |
| 0e1755f | Mark executors keep claimed pages unlinked until they publish them (executor-local lists were spliced by `page_needs_scan` -> `pages_to_scan` corruption, `[DOUBLE-CLAIM]`). | 3/~1660 -> 0/1314 at gcc -O3 |
| ae1c529 | **Hybrid write barrier**: while a thread is unscanned, `GC_WRITE_BARRIER_IN` also shades the NEW value (Go design 17503), read back later via `gc_thread_info.grey_slot`. Generated code unchanged. | gc_stress 2/2000 -> 0/2000 |

Last full results on the branch head (ae1c529): -O3 soak (gcc-O3, clang-O3, gcc-O3-ndebug; every
C GC test + gc_stress; 7 profiles; 10 runs) 0 of 3570. CTest 52/52.

## Open

1. **`test_gc_mesh` with the nursery off fails about 1 in 1500-2000** (`CORRUPT bad checksum` or
   `DANGLE ... mesh_node field#1 -> reclaimed`): a live node whose `next` (or a cell's value) was
   freed. Seen on both sides of every recent change, so it predates them. Not root-caused.
   Reproduce: `YAFL_GC_POISON=1 YAFL_LOCAL_GC=0 MESH_STEPS=50000 ./test_gc_mesh` in a loop (CTest's
   `test_gc_mesh_global` environment), ideally two loops side by side.
2. **Cost check before merging**: `GC_PUBLISH_IN` adds a seq_cst fence per queue push and per
   `task_on_complete`. Needs an x86 self-compile timing.
3. Barrier-free publishing stores left as they are, believed safe because the published object is
   allocated immediately before: `lazy_thunk_enqueue` (waiter CAS) and `list_builder_link`. Worth a
   comment or a check.
4. Hypothesis considered and NOT supported by a capture: the barrier flag is raised without a
   handshake (Go enables its barrier at a stop-the-world point with a fence), so an unscanned thread
   could read it as off and skip a deletion shade while an already-scanned thread holds the old
   value. A `DELETED-FLAG-OFF` probe never fired in a failing run. If it is ever confirmed, the fix
   is a "ragged barrier": every thread acknowledges the flag at a safe point before any stack scan.

## Tools

- `yafllib/tests/gc_soak.py`: builds the GC tests per variant (gcc/clang x -O0/-O2, opt-in -O3,
  -O3-ndebug) and runs them under 7 collector profiles. Also builds `tests/gc_stress.yafl` with the
  Python compiler (about 8 minutes per variant on the Pi). Example:
  `python3 tests/gc_soak.py --builds gcc-O3,clang-O3 --tests test_gc_mesh,gc_stress --profiles default,global -n 50`
- `YAFL_GC_TRACE=1`: per-page ring of collector events; `gc_trace_explain(label, p)` prints a page's
  history and flags events naming p's slot. DANGLE reports and test_gc_mesh's corruption report
  call it.
- Side-by-side A/B was the reliable way to measure: build "before" and "after" binaries and run
  them concurrently (so both see the same load), counting failures over 600-3000 runs each.

## Diagnostic hooks (not committed to the runtime): `diag-hooks.patch`

`docs/aarch64-gc/diag-hooks.patch` applies to ae1c529 with `git apply`. It adds:

- `gc_diag_bad(what, obj, via)`: prints the trace for obj and via, plus a raw backtrace and the
  executable's load address (decode with `addr2line -e <bin> -f -i -p` on `addr - base`).
- **The LATE MARK detector** in `atomic_gc_object_mark_as_seen`: aborts when a mutator barrier,
  during PRUNE, newly marks an object on a page that marking processed. Under SATB that should never
  happen: it means the trace missed a reachable object and a late barrier "rescued" it (prune keeps
  it via the residue merge but never scans it, so its children are freed).
  Its history matters: the first version produced false positives because prune resets `seen` and
  `atomic_seen` without changing `processed_by_epoch`. The patch now has prune stamp the page
  (`0xFFFFFFFE`) BEFORE resetting anything, with a release fence, and the detector re-reads the
  stamp after the bitmaps behind an acquire fence. The late-mark captures taken before that fix (all
  on 2026-10-13) should be treated as unreliable.
- Extra trace events: page joins the pool at a root scan (`alloc` with aux 0xA5A5 = 42405),
  hybrid-barrier record/flush, `yafl_cas_once` fills, mesh cell stores (with the storing thread's
  grey bit, the barrier flag, and the stage packed into aux), `DELETED-FLAG-OFF`, and mailbox mark
  events.
- Trace timestamps from `cntvct_el0` instead of the global atomic sequence counter.

Build it like CTest does (all runtime sources compiled into the test):

```
git apply docs/aarch64-gc/diag-hooks.patch
cd yafllib
SRCS=$(sed -n '/set(TEST_SRC_FILES/,/)/p' CMakeLists.txt | grep -oE '[A-Za-z0-9_/]+\.c' | tr '\n' ' ')
gcc -std=gnu11 -O0 -g -I. -I.. -o mesh_diag tests/test_gc_mesh.c $SRCS -lm -lpthread -ldl
YAFL_GC_POISON=1 YAFL_GC_TRACE=1 YAFL_LOCAL_GC=0 MESH_STEPS=50000 ./mesh_diag
```

## Lessons that cost time

- **Tracing hides these races.** A global atomic event counter, or logging every scan, made failures
  disappear (thousands of clean runs). Keep instrumentation narrow; `cntvct_el0` timestamps helped.
- A diagnostic check that fires far more often than the real failure is suspect: check the
  detector before the collector.
- Most bugs here were check-then-act on a flag, a shade placed after the act it protects, or a
  hidden assumption that "this container is traced". x86 (TSO) hides most of them.
- Background "wait until" loops whose target was killed run forever; prefer one-shot notifications.

## References

- Go hybrid write barrier, design 17503: https://go.googlesource.com/proposal/+/refs/heads/master/design/17503-eliminate-rescan.md
- Go `runtime/mbarrier.go` header comment.
- Gammie, Hosking, Engelhardt, "Relaxing safely: verified on-the-fly garbage collection for x86-TSO" (PLDI 2015).
- Doligez and Gonthier, "Portable, unobtrusive garbage collection for multiprocessor systems" (POPL 1994).
