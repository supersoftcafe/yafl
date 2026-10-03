# List — claimable segments

`List<T>` is an ordered, persistent sequence with O(1) append, O(1) prepend
and allocation-free iteration, and NO builder. It replaces the cons-chain List
and its `[linear]` `ListBuilder`. Implementation: `stdlib/System/list.yafl`;
runtime primitives: `yafllib/object.c`, "List segments".

## Opaque by contract

User code cannot see how a List is stored. There is no `Chain`, no
`ChainLink` to match, no `chain()`: a List is a set of functions —

* build: `List()`, `append`, `prepend`, `concat`
* take apart: `isEmpty`, `first`, `head`, `tail`, `uncons`, `last`, `size`
* walk: `fold`, `map`, `filter`, `any`, `all`, … or as a `Stream` (a
  `List<T>` is its own stream state: `next` is `first` + `tail`)

`first` is the unchecked head (test `isEmpty` first; on an empty list it
aborts). `head` is the checked one (`T|None`). The idiom that replaced
matching `ChainEnd`/`ChainLink` is

```yafl
fun [tail] walk(xs: List<T>, acc) => isEmpty(xs)
  ? acc
  : walk(tail(xs), step(acc, first(xs)))
```

## Representation

```yafl
class [final] ListSeg<T>(lsClaim: Int64, lsOrd: Int32, lsNext: ListSeg<T>|None,
                         length: Int32, array: T[length])

class [final] List<T>(_first: ListSeg<T>|None, _last: ListSeg<T>|None,
                      _start: Int32, _end: Int32)
```

A List value is four fields — it flattens to a by-value struct — onto a
forward chain of segments, each one heap object of up to 16 elements inline
(capacities ramp 2, 3, 5, 8, 13, 16). The value sees `_first[_start..]`,
every interior segment in full, and `_last[..._end)`. Interior segments are
always full: a segment is only linked behind one whose capacity is used up.

A segment's live range `[lo, hi)` (the claim word) only ever grows — `hi`
up by append, `lo` down by prepend. A segment built by `prepend` fills from
its back, so later prepends claim downwards.

`lsOrd` is a segment's identity within a list (appended segments number one
up, prepended one down). A walk knows it has reached the last segment when
the ordinals agree — pointer identity would not do, because the GC may hand
the walk a different copy of the same segment.

## The claim: why there is no builder

`append(l, x)` writes slot `l._end` of the last segment IN PLACE if nobody
has claimed it: the runtime takes the segment's late pin (the mutex the
compactor also takes), checks `hi == l._end`, bumps `hi`, and the element
store and release follow. If another list value got there first — the
same list was appended to twice — the claim fails and the append COPIES the
list. A full segment links a fresh one the same way (`next` is write-once,
claimed like a slot).

What `[linear]` used to prove (no other holder can see the write), the
claim now establishes at run time, one append at a time:

* every slot is written at most once, over the allocator's zero fill;
* a list value only ever reads slots written before it existed;

so no program can observe which of two forks won, and List is a pure value.
Builder-style code (an accumulator threaded through a loop) never forks and
always takes the in-place path. Code that does fork pays what the old
`append` always paid — a copy — and stays correct.

Costs: `append`/`prepend` O(1) (a fork copies — at the back the whole list,
at the front at most one segment); `head`/`first`/`tail`/`last` O(1) and
allocation-free; `concat(a, b)` O(|b|), appending onto `a` in place, so a
`flatMap`-style fold of concats is linear rather than quadratic; `size`
O(segments).

## GC soundness

* **Relocation.** A late store must land on the copy the world reads, so the
  claim resolves forwarding and holds the pin across the store
  (`object_pin_resolve`). A list value's own segment pointers are always
  good for its own elements — every one was taken at or after the writes
  the value depends on. A `next` pointer is not: it is written once, when
  its target is brand new, and later appends land on whatever copy is
  current then. So a walk resolves each segment it ENTERS (`list_seg_resolve`
  in `tail`'s hop) — once per ≤ 16 elements, never per element read. This is
  the difference from `[pinnable]`, which resolves every field access.
* **Generations.** A late store can put a young pointer into a segment on an
  old page; `gc_note_late_write` runs before every claimed store, exactly as
  `once.c` does for Memoize.
* **Snapshot barrier.** None needed: the old value of every written slot and
  `next` is the allocator's zero fill.

## Measurements

See the commit introducing this design for the before/after O3 self-compile
timings (best-of-three, `full_protocol.py` `o3_timed`).
