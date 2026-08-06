# Inlining policy around async — a design note

Status: thinking, not scheduled. (User, 2026-08-06: "Inlining non async
functions to async callers might be counter productive. I do wonder if the
only beneficial inlining is very small functions and larger (but not large)
async functions.")

## Sync callee, async caller

A sync call from an async function is a plain C call — the win from inlining
is small. The risk is state-frame growth: standalone, the callee runs
atomically inside one resume segment and its locals never touch the frame;
inlined, argument-lifting (the AST inliner hoists arguments into outer lets)
and live-range extension can move values across a park, and every value live
across a park is a frame field — heap traffic on every suspension and GC scan
surface (`scan_within` was 36% of the O3 incident).

Policy direction: tiny bodies stay in (the AST inliner's 10-node threshold is
already this); bulk sync-into-async should be restricted or demonstrated
harmless. Note the AST inliner cannot currently see asyncness — it runs
before sync_inference — so enforcement lands in the IR inliner or needs an
early asyncness estimate.

## Async callee, async caller

Potentially the MOST profitable inlining: an async call site pays the full
maybe-suspends protocol (tag check, continuation registration, frame
allocation, resume hop). Merging a mid-size async callee deletes a frame and
a hop from every await chain.

The O3 regression (137-field frames from the single-caller fold merging
suspending helpers) is not evidence against this — it is evidence against
doing it UNBUDGETED. The current blanket sync-only gate over-corrects.
Refinement: re-open the fold for async callees under a MERGED-FRAME BUDGET —
inline iff the resulting state-field count stays under N — so "larger but not
large" falls out of the budget rather than a size heuristic, and the 137-field
case is impossible by construction.

## Measurement

Back-end territory: the findstr proxy is front-end-bound and cannot see any
of this. Measure on the bootstrap self-compile; the O3 investigation already
instrumented state-frame field distributions and scan_within, and task
allocation counts complete the picture. Compare policies A/B on frame-size
distribution, task allocations, and wall.
