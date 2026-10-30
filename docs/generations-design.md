# Generations: old stays old, with a card per object

Status: implemented, 2026-10-30 (`yafllib/object.c`, "OLD STAYS OLD"). It
replaces demotion and dirty-old pages. The thread-local nursery was removed
the same day: a dwell between global cycles took most of what it gave
([local-nursery-prototype.md](local-nursery-prototype.md), status note).

## The shape

A page is YOUNG until it promotes, then OLD for good. Old pages leave the
scan/prune rotation, and every mark source skips them, so a MINOR cycle traces
the young pages, the mutable set, and the carded old objects (below). A MAJOR
traces everything and returns every surviving old page to old.

**Promotion** is by volume: an immutable single page that stays stable (no
deaths at any prune) across the promotion volume of allocation. Mutable pages,
multi-page objects and compacted pages never promote.

## The invariant, and the card

> An old object points only at old objects, or within its own page, unless its
> CARD bit is set.

The card is one bit per object start, in the page header beside `objects`
(`page_head.cards`, 64 bytes a page). The object is carded, not a region of it:
YAFL objects are small, and the bit lines up with the bitmaps the collector
already keeps.

Most referents of an immutable object are allocated before it and promote
first, so most old objects need no card. The exceptions:

- a referent that never promotes: a mutable object, or a copy compaction made;
- a referent younger than its page's cohort when the page promotes;
- a late write: a write-once slot filled under a late pin (`object_pin`).

**Promotion cards.** Promotion stamps each object (`VTABLE_OLD_BIT`, below) and
then reads its references; an object holding anything young is carded. The page
promotes either way. Pages with cards go on `carded_pages`, the rest on
`old_pages`.

**A late pin cards.** A late pin into a stamped object sets the object's card,
flags its page (`carded`) and its thread (`old_writes`), all under the pin and
before the store. The thread's next root scan raises the collector's request;
the end of that SCAN_ROOTS moves the flagged pages onto `carded_pages`. Without
the request, nothing walks `old_pages`.

**Minors trace cards.** At the end of SCAN_ROOTS, after every thread's scan,
every carded object's fields are marked through the fields
(`atomic_gc_object_seen_by_field`): a referent that compaction moved is
followed, and the field rewritten to the copy. A card is cleared once every
referent is old; a page left with none goes back to `old_pages`. Write-once
slots mean a card only ever goes clean, never flips back.

That timing is the ragged snapshot's: a late write made before its writer's
root scan is traced by the cycle in flight; one made after needs nothing this
cycle (the writer held the value at its scan, or it was born marked).

### Clearing a card without losing one

The collector clears a card, then re-checks the object, and re-sets the card if
the object is pinned or holds anything young. The late pin sets the card under
the pin and before its store. So either the pin's card lands after the clear,
or the re-check reads the pin, or — past the unpin's release — the store.

## The stamp

Promotion ORs `VTABLE_OLD_BIT` into each object's header word: the very word a
late pin CASes, so the two are ordered.

- A pin that won before the stamp is still held — the page is refused — or has
  released, and the stamp's acquire makes its write visible to the reference
  check, which cards the object.
- A pin after the stamp sees it and cards the object itself.

The stamp means "old". Nothing clears it: an old page never stops being old. A
refused promotion leaves stamps on a young page; a late pin on one of those
objects sets a needless card, which the next promotion attempt resets before it
re-reads the page.

## What still holds a page back: a pin

A page with a pinned object does not promote. A builder's array or tail is
pinned from allocation to seal and filled across safe points by FILL stores,
which owe no card. Promoting under it would hide the elements stored after
promotion. A later prune tries again.

## Majors

A major runs once the old generation has grown to 125% of its size after the
last major (`GC_MAJOR_GROWTH_PERCENT`, `YAFL_GC_MAJOR_GROWTH`), under heap
pressure, or on request. It takes `old_pages` and `carded_pages` into its
rotation and traces everything. At its prune each old page gives up its dead objects (and their
cards) and goes straight back to old, to the list its cards decide. Deaths on
an old page count as a promotion MISTAKE: the page promoted while still
churning, and the mistakes steer the promotion volume.

**A sparse old page compacts into a page BORN OLD** (`gc_old_copy_alloc`).
Its objects' referrers are old, and no minor traces them, so:

- the copies must not be young: each prune executor bumps through a page of
  its own that joins `old_pages` as it is taken (a fresh one every cycle);
- a copy keeps the OLD stamp, and a carded object's card goes with it (the
  copy's page is flagged for the next minor, as a late pin's would be);
- the STUB keeps its card too. A reader that follows an old referrer to the
  stub reads the stub's own body — the object as it was when it moved — and
  no minor scans an old page. Without the card, the body's young referent
  could move, its forwarder die, and the body point at a reclaimed slot (the
  -O3 compile of `gc_stress`, before the fix: 3 runs in 4). The card walk
  traces a stub's body through its copy's vtable, as the scanner does a
  young stub's (`test_gc_old_stub_card`);
- the vacated page, all forwarders, stays old: old referrers reach the copies
  through it until the next major's trace rewrites them past the forwarders,
  and the major after that frees it.

A YOUNG page that carded old objects point into compacts like any other: the
card's trace rewrites the old field past the forwarder at the next minor
(`test_gc_card_compact`).

## What went

- **Demotion.** A late write into an old object used to send its page back to
  the young generation, where it had to re-earn promotion; a major demoted the
  whole old generation.
- **Dirty-old pages.** A page whose objects still pointed at young ones could
  not promote; it waited as dirty-old, force-marked as a root every cycle,
  re-walked every prune with a backoff, and excluded from compaction (the
  `9177f0f` fix). Promotion now cards those objects instead.
- **Stale stamps on demoted pages** costing a redundant report.

## Tests

- `test_gc_cards`: a page whose object points at a mutable object promotes
  carded; minors trace the card; a major keeps old pages old; unrooted, a
  major reclaims them.
- `test_gc_old_late_write`: a late write into an old object before its writer's
  scan is traced by the cycle in flight, and the page stays old.
- `test_gc_card_compact`: a young page a carded old object points into
  compacts, and the old field follows the move.
- `test_gc_old_compact`: a major compacts a sparse old page into a page born
  old; the copy keeps its stamp and card, an old referrer reaches it through
  the forwarder until the next major rewrites the field, and the major after
  frees the forwarder.
- `test_gc_late_pin_race`: a late pin landing between promotion's pin walk and
  its stamps, and between the stamps and the old-claim.
- `test_gc_old_stub_card`: through an old referrer, a stub's body still
  reaches its young referent after that referent moved and its forwarder
  died.
- `YAFL_GC_VALIDATE_OLD` builds check the invariant at every cycle start
  (forwarders are checked at their copies).

## Measurements

The -O3 self-compile on the pi (aarch64), two rounds each, interleaved, and the
generated C identical in every run. User CPU and peak RSS:

| Runtime | User CPU | Peak RSS |
|---|---|---|
| Before cards (demotion, dirty-old) | 672–677 s | 1.35–1.63 GB |
| Cards, old pages never compacted | 585 s | 2.07–2.60 GB |
| Cards, old pages compacted, major at 200% | 584 s | 1.82–1.85 GB |
| Cards, major at 150% | 588–592 s | 1.54–1.70 GB |
| **Cards, major at 125% (the default)** | 606–612 s | 1.39–1.51 GB |

**Why the major trigger is the knob.** The trigger compares the old generation
with its size just after the last major. Before cards, a major demoted the whole
old generation. Only pages that passed the re-promotion checks in that same
prune came straight back, so the recorded baseline was small. The old
generation then refilled with pages that had been old all along, each counting
as growth. Majors came round every ~40 cycles: 59 in an x86 self-compile, the
old generation dropping from ~15,600 pages to ~2,100 and back.

With cards a major returns every surviving old page to old at once. The
baseline is the real old generation, and only new promotions count: 20 majors
at doubling, ~140 cycles apart. Old garbage waits for a major, so the trigger
alone trades CPU for memory. At 125% the peak is back where it was before cards
and about 10% of the CPU saving remains.

The benchmark set (`ylisp`, `raytracer`, `yaflc`, `yspell`, `json_pretty`,
`pin_append` chain/mixed, `memo_bench` insert/parins/churn) was within
run-to-run noise of the runtime before cards, at every trigger setting; its
programs rarely run a major.

## Found on the way: where the current thread's scan starts

The current thread's conservative root scan used to start at the stack
pointer of the root scan itself, deep in the collector, so it read the
collector's own frames too. A step leaves addresses in slots the next step's
frames sit over without writing; found there, they pinned pages against
compaction and kept dead objects alive. Three stepped tests failed by turns
as the frames moved.

The scan now starts where the thread entered the collector: `gc_fsa`
captures the stack pointer and the callee-saved registers in its own frame,
which stays live for the step, when that step will scan this thread.
Everything above — the mutator, and runtime frames such as a string builder
holding a heap pointer across an allocation — is scanned as before; the
collector's frames below are not.

## Open

- [#69](https://github.com/supersoftcafe/yafl/issues/69): shorter-lived
  forwarders. Mark only the final copy when a slot was rewritten, and move
  compaction alone to the start of the next cycle (for old pages, the next
  major), leaving the prune at the end: the two were combined only because
  the collector used to run continuously.
- A `test_gc_ring` hang in one x86 soak run (clang-O2, no dwell: one of four
  chains stalled after 88 steps), not reproduced in 1,600 runs since on either
  this or the previous runtime.
