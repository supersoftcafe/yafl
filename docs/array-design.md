# Array — growable values and pinned construction

## Array grows by appending (issue #95)

`Array<T>` is a value over a shared buffer, as a String is:

```yafl
class [final, pinnable] _ArrayBuf<T>(_used: Int32, [capacity] _cap: Int32, _items: T[_used])
class [final] Array<T>(length: Int32, _buf: _ArrayBuf<T>)
```

Two general class features carry it:

* **`[capacity]`** on an Int32 field of an array class sizes the storage
  past the length: the object is allocated for the larger of the two, the
  constructor fills `[0, length)`, and the vtable's `array_cap_offset`
  names the field. The collector traces and compaction copies only
  `length` elements, rounded up to whole 32-byte slots. The copy's capacity
  is what that rounded size holds: a moved buffer grows in place into the
  rounding, and the spare capacity past it stays behind. The runtime has
  handled this since String's growable buffers.
* **`subject.items(i) := value`** writes an element of an array field of a
  `[pinnable]` or `[mutable]` object, under the pin, as `subject.field :=`
  writes a field. The index is checked against the capacity when the
  class has one.

`append(a, x)` pins the buffer; if `a` owns its end (`a.length == _used`)
and there is room, it writes element `_used`, then `_used := _used + 1`,
and unpins. Otherwise it copies into a buffer of twice the size. A value
reads only its own `[0, length)`, which never changes, so every value
keeps its own elements; one holding a stale copy of a moved buffer reads
the same ones.

`push(a, x)` is the builder-shaped spelling of `append`. There is no
`ArrayBuilder`: when the final count is not known up front, start from
`Array<T>()` and push. `arrayOf<T>(v1)`, `arrayOf<T>(v1, v2)` and
`arrayOf<T>(v1, v2, v3)` are convenience constructors for a known few values;
`Array<T>(n, initFn)` tabulates when the count is known.

An index past a value's length aborts, as before, by reading it from a
buffer with no elements. That is TEMPORARY: the API will answer that the
element is not there, as List's `head` does.

The rest of this document describes the pinned construction primitives
(`array_builder_alloc`, `array_builder_store`, `array_builder_seal`) that
`SeqBuilder`'s segments use.

## The pinned construction primitives

The tabulating form `Array<T>(n, initFn)` handles a known count; append/push
is the way in when it isn't:

```yafl
let a = push(push(Array<Int>(), x), y)
```

`SeqBuilder<T>` is the remaining linear builder in the stdlib. Every
operation consumes the builder (`push`, `build`, `discard`), and `_ok`
threads the runtime results so no pass can discard the calls — exactly as
`ListBuilder`, this design's precedent throughout.

## The construction window crosses safe points

The ctor's fill loop is straight-line codegen after `NewObject`: nothing can
observe the half-built array, and no GC boundary falls inside it. A
builder's fills are ordinary YAFL calls — and a producer may be ASYNC, so
between two pushes the program can suspend, allocate, and take any number of
GC cycles, with the half-built array live the whole time. Three decisions
make that sound:

**Pinned from allocation to seal.** `array_builder_alloc` allocates the run
born pinned (`array_create(…, pinned=true)`: the pin bit rides the store that
installs the vtable); until `build`/`discard` seals it, the array cannot be moved by compaction —
so every push is a plain generated store at a stable address, and NO READER
ANYWHERE pays a forwarding resolve. (The alternative — a momentary locking
bracket per store, the late-pin idiom (`object_pin_set` today) — makes the cells relocatable while
late-writable, which forces `[pinnable]`-style resolving reads onto the
hottest walks in the language; measured at ~+23% on a self-compile. Memoize
pays that price happily; construction must not. Ruling 2026-08-25.) The pin
also blocks page promotion, so element stores stay young-generation writes.

**`length` starts AT CAPACITY and seal SHORTENS it.** There is one length
field, and it never understates the traceable extent. `array_create`
zero-fills the payload, so the scanner — which walks `length × stride` slots
from birth — reads unwritten slots as NULLs. Each pushed element is
traceable the moment it lands. `build` writes the true count (`_at`) as the
LAST act: readers never see a length larger than what was pushed, and the
trim only discards never-written zeros.

**Stores are fill stores.** Each slot is written exactly once over the
allocator's zero fill, so the snapshot barrier has no old edge to keep. But a
build crosses safe points, so the store is not `fresh`: it is a FILL store
(`ObjectField.fill`, `GC_FILL_STORE_IN`), which keeps the publication fence
and owes nothing else. The pin keeps the run's page from promoting while it
fills. (Under the thread-local nursery, since removed, the fill store also
escaped the element once the run had left the nursery.)

**Sealing shorter owes the snapshot barrier.** Shortening `length` deletes
every reference past it. `build` trims only never-written zeros, but a grown
or discarded run is sealed to 0 with all its elements in it, so
`array_builder_seal` applies the deletion barrier to each element it cuts
off while a cycle is marking. Without it, an element reachable at the
snapshot only through the old run, and since copied into the new run
(allocated during the cycle, so not traced in it), was freed under the new
run (tests/test_builder_gc.py).

Growth (`append`/`push` past `_cap`): fresh run at double capacity (pinned),
`_copyInto`, the abandoned run sealed EMPTY — releasing its pin — then the
push retries.

## Element representation: `T` never crosses the runtime boundary

A C function cannot take a `T` by value — its width varies per
instantiation (1 byte, a pointer, a multi-word struct). So the runtime
primitives are representation-BLIND:

* `array_builder_seal(arr, len)` — barriers the references past `len`
  (during a cycle), writes an `int32` at `vtable->array_len_offset`, then
  unpins

Everything element-typed is a COMPILER special form, inlined after
monomorphisation where the width is a static fact
(`pyast/expression/builtin_op.py`, port `codegen/generate_expr.yafl`):

* `array_builder_alloc` — the ctor's own sized-`NewObject` path
  (`array_create` with this instantiation's vtable, born pinned). The vtable carries the
  representation: `array_el_size` (stride) and `array_el_pointer_locations`
  (per-ELEMENT pointer mask — a struct element with pointers at words 2 and
  5 has bits 2 and 5).
* `array_builder_store` — a typed IR `Move` into the indexed trailing
  array member: `((Array_X_t*)arr)->array.a[i] = val`. Both sides carry the
  element C type from the same monomorphised copy, so a width disagreement
  is a clang error, not a silent smash. This is byte-for-byte the ctor
  fill's store (new.py:159) re-exposed at a builtin boundary.

Bounds are by construction, not by check: `SeqBuilder.push` tests
`_at < _cap` in YAFL and takes the growth path otherwise; Array's `append`
makes the same test on its buffer's `_used`. Linearity (for the builder) or
the buffer's ownership test (for `append`) keeps the written count dense.
(`__builtin_op__` remains the designated unsafe hatch — hand-written misuse
is the same exposure class as `list_builder_link` with a bogus slot.)

## Purity

YAFL has no assignment; construction does. Every ctor call already lowers
to `NewObject` + `Move`s of the fields — assignment-as-initialisation has
been in the IR since the first class compiled. The builder stretches that
initialisation window across calls, and the discipline that keeps it
unobservable is the API:

* linearity gives unique ownership — exactly one reference to the
  half-built array exists, held between "allocated" and "published";
* the array escapes only at `build()`, and nothing writes after seal.

No YAFL program can distinguish `build(push(push(b, x), y))` from an array
constructed atomically with those contents.

## Drop

`SeqBuilder<T>` has the remaining ambient `Drop` instance — an abandoned
builder (a failed parse alternative, an early exit) must still release its
pinned run (a leaked pin is a permanently unmovable object): `discard` seals
empty, unpinning, so run and referents die at the next cycle. (Adding this
generic ambient Drop instance exposed a latent resolver bug — see
`_scope_filtered` in `pyast/expression/access.py`: an instance lookup
must demand every instance placeholder bound, not merely a non-None
mapping.)

## Tests

`tests/test_builder_gc.py` exercises push/link builds across GC cycles
(sync and async producers), including the snapshot barrier for copied runs.
`stdlib_tests/Containers/array_tests.yafl` covers tabulation, convenience
constructors, append/push growth and the combinators. Runtime pin/seal unit
coverage rides the existing ctest suite (object.c debug exports).
