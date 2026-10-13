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
| 960c34d | **`page_needs_scan` does nothing once marking has ended.** Mark executors pumped the reprocess ring after the tail retired the stage to PRUNE, pulling a page off `pages_to_prune`: it skipped that prune, kept stale `seen`/`scanned` bits, and the next cycle's page pass (`seen & ~scanned`) skipped its objects, whose children were freed. This was the nursery-off `test_gc_mesh` corruption. Not aarch64-specific. | diag build, Pi: 3 corruptions / 300 -> 0 / 300; x86: 6 / 1000 -> 0 / 1000 |
| 3f95ab1 | `test_gc_mesh` reads mailbox slots through `object_resolve`, as generated code does for write-once fields. | test fidelity |

Last full results on the branch head (ae1c529): -O3 soak (gcc-O3, clang-O3, gcc-O3-ndebug; every
C GC test + gc_stress; 7 profiles; 10 runs) 0 of 3570. CTest 52/52.

## Open

1. **Resolved by 960c34d:** the nursery-off `test_gc_mesh` corruption (about 1 in 1500 plain runs).
   How it was found, for reuse: the end-of-mark check (see the patch) flags the state in the cycle
   it occurs; per-child "mailbox scanned" events showed a mailbox marked `scanned=1` that was never
   scanned that cycle, and its page's history showed it had skipped the previous prune. The x86
   session reproduced it with the diagnostic build (plain x86 builds never showed it in 16,000
   runs), so it is a timing-dependent race, not an ARM ordering issue. Still worth a long A/B of
   the PLAIN test (no diag build) on the Pi, where it failed about 1 in 1500.
5. **x86 oversub OOMs** (from the x86 session): `test_gc_mesh` under gc_soak's `oversub`
   (`YAFL_THREADS=8 YAFL_LOCAL_GC_PAGES=4`) aborts with `[GC OOM] heap pages used 4096 of 4096`
   about 2 s in (cycles 7-18, stage prune, no old pages), 4 in the first 2250 runs on x86. Seen
   once in 1000 on the Pi (main, gcc -O2). Looks like garbage outrunning the collector, or the
   allocator stall (`gc_page_alloc_impl`) not holding; not investigated.
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

`docs/aarch64-gc/diag-hooks.patch` applies to the branch head with `git apply`. Its `once.c` part also
carries the experimental `yafl_cas_once` barrier change (see Open item 1). It adds:

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
- **The end-of-mark check** (`diag_check_end_of_mark`, called in `gc_fsa_mark_sweep_tail` just
  before the stage becomes PRUNE): walks `pages_to_prune`, and for every marked object checks that
  each child on a page collected this cycle is marked. It prints every violation with the parent's
  `page-pass scanned` bit, and aborts only when that bit is 0 (shape A above). Validated as
  described under Open.
- A dropped-ring-entry event at the START ring reset (`RING ENTRY DROPPED`, on the page).
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
