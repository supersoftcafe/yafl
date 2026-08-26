# Container design — ordered vs unordered

## The rule

**No iteration on unordered containers.**

"Iteration" means any operation that lets a caller observe element ORDER: a
chain/cursor walk, or a conversion to an ordered container that does not name
an ordering. If a container has no defined order, exposing one is a lie — the
order is an artefact of the implementation (hash-tree shape, insertion
history), and callers come to depend on it.

Permitted on an unordered container:

* bulk transforms whose result is also unordered — `map`, `filter`
* order-independent questions — `isEmpty`, `size`, `contains`, `any`, `all`,
  `singleOrNone`, `isMoreThanOne`
* an EXPLICIT ordering — `sort`, which is the only way out to a `List`

## The six containers

| type | ordered? | built by | for |
|---|---|---|---|
| `Dict<K,V>` | no | `put` | keyed lookup |
| `Set<T>` | no | `add` | membership; a `Dict<T,()>` behind a wrapper |
| `Bag<T>` | no | `add` | accumulation when order does not matter |
| `List<T>` | YES | `ListBuilder` / `prepend` | sequences whose order is meaningful |
| `Array<T>` | YES | ctor init fn / `ArrayBuilder` | O(1) indexed reads; ONE heap object per sequence |
| `Seq<T>` | YES | `SeqBuilder` | build-then-walk sequences; one SMALL heap object per ≤16 elements |

Pick the SIMPLEST container that does the job. A loop that reads its own
accumulator wants a `Set`. Plain accumulation wants a `Bag`, or a
`ListBuilder` when the result must be an ordered `List`. `ListBuilder` is an
optimisation, not the default to reach for.

### Bag

The original banker's pair (`front`, `rear`) with the reversal deleted. The
reversal only ever existed to restore ORDER when draining the rear; a `Bag`
has no order to restore, so both chains are walked as they lie. `add` is O(1),
and keeping two chains leaves room for a cheap `merge` later.

### List

Ordered, so a cursor walk (`chain`) is legitimate — that is what "ordered"
buys. Built ONLY front-normal, so there is no rear and nothing to reverse:

* `ListBuilder` — in-order construction, O(1) push
* `prepend` — the cons; O(1), yields reverse-of-insertion order

`append` is REMOVED. It is the sole reason the rear chain existed, and the
rear is the sole reason `_chainReverse` existed.

`reverse` is REMOVED. On a front-normal list it can only be implemented by
building a reversed copy — `_chainReverse` under a new name, which is exactly
what must not reappear. Order changes come from `sort`.

### Array

Ordered with O(1) indexed reads (`a[i]`), stored as ONE heap object: a
`length: Int32` plus the elements inline. Where a `List<T>` is a heap cell
per element (~85B for a ~60B payload, one GC mark per element per cycle),
an `Array<T>` is a header plus `n × sizeof(element)` — the container of
choice for large, build-once-read-many sequences. Two ways in:

* `Array<T>(n, initFn)` — tabulate `initFn` over `0..n-1`
* `arrayBuilder<T>(estimate)` … `push` … `build` — linear incremental
  construction when the final count isn't known up front
  (see [ArrayBuilder design](array-builder-design.md))

There is no update, no slice, no cursor: read by index, or walk `0..length`.
A sequence that grows or is consumed element-at-a-time is a `List`; a
sequence built once and then indexed is an `Array`.

### Seq

Ordered, stored as a chain of SEGMENTS: each segment is one heap object
holding up to 16 elements inline plus the link to the next segment. The
midway point between `List` and `Array` — far fewer heap objects (and GC
marks) than a cell per element, without the multi-page single objects that
broke the collector's cycle economics when hot lists were migrated to
arrays wholesale.

There is no wrapper enum: a Seq IS `Segment<T>|None`, and `None` is the
empty sequence — the union collapses to one nullable pointer word, so
emptiness is encoded once and consumers match once. (List's
`ListEmpty`/`ListFull` facade is a banker's-queue leftover; Seq does not
repeat it.)

Build with `seqBuilder<T>()` … `push` … `build`. Segment capacities ramp
along the Fibonacci sequence — 1, 1, 2, 3, 5, 8, 13 — then stay at the 16
cap, so tiny sequences stay tiny and long ones settle at the largest
allocation unit that is still GC-friendly. Segments are LINKED as they
fill; elements are never copied. The open tail is pinned from allocation
to link/seal — the same construction contract as `ArrayBuilder` (see
[ArrayBuilder design](array-builder-design.md)).

Consume with `seqStream` (the `Stream` instance) or `fold`/`map`/`filter`/
`any`. There is no indexed access and no prepend/uncons: a sequence read
by position wants an `Array`, element-at-a-time front manipulation wants a
`List`. The sweet spot is build-once-walk-many sequences whose per-element
cells would otherwise dominate the heap.

## Removed, and what replaces it

| removed | why | replacement |
|---|---|---|
| `_chainReverse` | the whole point | nothing; no rear to drain |
| `List.append` | requires the rear | `ListBuilder.push`, or `Bag.add` |
| `List.reverse` | a disguised chain reversal | `sort` with the ordering you mean |
| `Dict.keys(): List<K>` | leaks hash-tree order | `keys(): Set<K>` (keys are unique) |
| `Dict.values(): List<V>` | leaks hash-tree order | `values(): Bag<V>` (values may repeat) |

## Added

On `Bag` and `Set` (and `List` where meaningful):

* `isEmpty`, `size`
* `singleOrNone` — the element of a one-element container, else `None`
* `isMoreThanOne` — more than one element
* `map`, `filter`, `any`, `all`
* `sort` — `Bag`/`Set`/`List` -> `List`, natural order via `BasicCompare`
* `sortBy` — the same taking a comparison function, for types with no natural
  order

`merge`/`concat` of two containers is done the slow way for now: there is no
good answer yet and it is deliberately future work.

## Why this kills `_chainReverse`

Every one of its 13 call sites drains a rear chain. The rear exists only to
make `append` O(1) on an ordered list. Remove `append`, and:

* `List` is front-normal by construction — `chain()` is free
* `sort` no longer reverses the rear before seeding runs
* `Bag` keeps two chains but never needs order, so never reverses

No hidden replacement: there is no function anywhere whose job is "produce the
elements of X in the opposite order".
