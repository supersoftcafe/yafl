# GC bookkeeping at pin and unpin, not per store (design, not implemented)

Status: proposal, 2026-10-16. Nothing here is built. The thread-local nursery (rule 4 below,
and the nursery passages after it) was removed on 2026-10-30, so those parts no longer apply.

## The idea

A pin is a lock, like Java's `synchronized`: between `object_pin` and `object_unpin` the
owner may make several stores into the object. Today each of those stores carries its own GC
bookkeeping. The proposal is to make stores inside a pin **plain**, and do the bookkeeping once per
pinned region, at the pin and at the unpin.

## "The unpin is the barrier" — half true

The word barrier means two different things here.

- **Memory ordering.** `object_unpin` is a release store; the next owner's pin is an acquire CAS. So
  everything the owner wrote is visible, in order, to the next owner. For lock-holders, the unpin
  is all the barrier they need.
- **The collector's bookkeeping.** These are not about ordering between mutators, and they matter
  even on one thread. The unpin cannot know any of them:
  1. **Snapshot (SATB).** While a cycle marks, a value overwritten must be shaded first.
  2. **Ragged snapshot.** A thread whose root scan is still to come must shade what it stores into
     an object the cycle may not trace (the hybrid barrier).
  3. **Generations.** An object on an `old` page that gains a young pointer must return its page to
     the rotation, or minor cycles never trace the young object. `object_pin` does this itself for
     an object carrying the OLD stamp (it marks the page and the thread; the thread's next root scan
     demotes the page).
  4. **Nursery.** A young value from this thread's nursery stored into an object other threads can
     reach must escape (`gc_local_note_slot`), or the next nursery collection frees it.
  5. **Publication order.** The markers read fields without the pin. They must not see a pointer
     before the object it points to (`GC_PUBLISH_FENCE`).

So the bookkeeping does not disappear. The question is whether it can be done per region instead of
per store.

## Two kinds of pin

| | Early pin | Late pin |
|---|---|---|
| Taken by | `object_new(..., pinned)`, `array_create` | `object_pin`; `object_try_pin` for writers of no references |
| Used for | array tabulation, array and list builders | `object_pin_set` (`__builtin_pin_set__`: memoize, write-once fields), the growable-string append, the compactor's claim |
| Object | fresh, not yet published | already shared |
| Region | spans safe points and nursery collections | short: no safe point, no allocation (`object_pin`'s contract) |
| Stores today | `GC_FILL_STORE_IN` per element; `GC_STORE_IN` in `list_builder_link` | one store (`object_pin_set`), byte copies (`str.c`) |

**Early pins cannot move their bookkeeping to the unpin.** The region crosses nursery collections.
A nursery collection in the middle of a build can promote the array off the nursery. After that,
values stored into it are traced by nothing in the nursery, so each one must escape when it is
stored, not at the seal. The per-store fill barrier has to stay.

**Late pins can.** No safe point falls inside the region, so neither this thread's root scan nor a
nursery collection can run between the pin and the unpin. That is what makes "once at each end"
sound.

## The design, for late pins

At the **pin**, after the CAS succeeds:

- Make the CAS acquire-release, not acquire. Its release half orders every store the thread made
  before the pin (the initialisation of the values about to be stored) before every store inside
  the region. That covers publication order (5) for all of them at once, so the stores need no
  fence. Late pins allocate nothing inside, so no value is initialised inside the region.
- Generations (3): already done, once, by `object_pin` — a stamped object marks its page and
  thread, and an unstamped one owes nothing, its pin's CAS being ordered against promotion's stamp
  on the same word.
- While a cycle marks (`gc_write_barrier_requested`): shade every pointer field the object holds
  now (1). This is object-granular SATB. Every value the region can overwrite is in the object at
  the pin. A value the region stores and then overwrites again came from this thread, which holds
  it or has dropped it as garbage.
- While any nursery is active: escape every pointer value the object holds now. This is the
  overwritten-value rule of the nursery barrier (4).

Inside the region, the stores are plain assignments.

At the **unpin**:

- If this thread has an active nursery and the object is not private: escape every pointer value
  the object holds now (4, the stored values).
- If a cycle marks and this thread's root scan is still to come: a seq_cst fence, then shade every
  pointer field (2). This is `gc_publish_slots` over the whole object. It runs after the stores, so
  the flag read cannot be satisfied before them. This is the same reason `GC_PUBLISH_IN` runs after
  its store. A static object publishes here too, as the object store macros do.
- The release store that clears the pin bit, as today.

The fast path, with no cycle marking and no nursery active, is unchanged except for the CAS: a flag
test or two at each end, and plain stores between.

## What it would gain, and what it would cost

- **A simpler rule.** Inside a pin you write fields; the GC's obligations live in two calls. That
  matches how pins are meant to be used.
- **It pays off only with several stores per region.** Today's late pins make one pointer store
  (`object_pin_set`) or none (`str.c` copies bytes). For them the walk at each end is a little
  dearer than one store's barrier: two passes over the object's pointer mask, each done only when
  its condition holds. Generated code's late pins make one store too (`__builtin_pin_set__`, or
  `:=` between `pin` and `unpin`). The benefit is for future code
  that holds the pin across several updates of a shared mutable object, which is the sharing
  contract's model for shared mutable state.
- **The walk is proportional to the object's pointer fields.** It is fine for small objects. A
  large array taken under a late pin would want card-granular bookkeeping instead, or the
  per-store macros. No such case exists today.

## What has to be checked before building it

1. **The ordering argument for an acquire-release pin.** A marker reads a field stored inside the
   region with no lock. The claim: on aarch64, a store before an acquire-release RMW, the RMW, and
   a store after it become visible in that order, so a reader that sees the field and follows it
   by address dependency sees the initialisation. This needs the same N2 soak treatment the
   publication fence had, with `test_gc_min2`'s holder written under a late pin.
2. **Object-granular SATB against the per-slot argument.** A stepped test: pin during marking,
   overwrite a field whose old value is reachable only through it, unpin, and check that the old
   value survives the cycle.
3. **The unpin shade against an unscanned thread.** A stepped test like `test_gc_static_store`: an
   object the cycle will not trace, written under a pin by a thread whose scan is pending, the
   value dropped before the scan.
4. **The nursery escape at unpin.** A stepped test: a young value stored under a late pin into a
   shared object, then a nursery collection; the value must survive.
5. **Compaction.** The compactor's claim is itself a late pin. Its copy must not run the region
   bookkeeping, or it would shade and escape everything it moves.

Each of these would be an A/B test, run with the change and without it.

## Recommendation

Build it when there is a user of it: generated code, or runtime code, that makes several stores
into a shared object under one pin. Until then, the per-store macros are no slower for the late
pins that exist, and they are already tested.

When it is built, do it for late pins only, behind the two calls (`object_pin` and
`object_unpin`), so the region rule ("plain stores inside") holds without exceptions. Early pins
keep their fill barriers.
