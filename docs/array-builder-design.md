# ArrayBuilder — linear incremental construction of `Array<T>`

`Array<T>` is one heap object: `class [final] Array<T>(length: Int32,
array: T[length])`. The ctor form `Array<T>(n, initFn)` tabulates when the
count is known; `ArrayBuilder<T>` is the way in when it isn't:

```yafl
let a = build<Int>(push(push(arrayBuilder<Int>(estimate), x), y))
```

`class [linear,final] ArrayBuilder<T>(_arr, _at, _cap, _ok)` — every
operation consumes the builder (`push`, `build`, `discard`), `_ok` threads
the runtime results so no pass can discard the calls: both exactly as
`ListBuilder`, which is this design's precedent throughout.

## The construction window crosses safe points

The ctor's fill loop is straight-line codegen after `NewObject`: nothing can
observe the half-built array, and no GC boundary falls inside it. A
builder's fills are ordinary YAFL calls — and a producer may be ASYNC, so
between two pushes the program can suspend, allocate, and take any number of
GC cycles, with the half-built array live the whole time. Three decisions
make that sound:

**A MOMENTARY pin brackets each element store — the array is otherwise an
ordinary movable object.** Pinning is never a state the builder holds:
between pushes the compactor is free to relocate the array (references to
it, including the builder's `_arr` field, are fixed up like any others).
Each store runs the `once.c` write-once idiom: `array_builder_begin`
resolves forwarding, takes the pin (a mutex against the compactor claiming
the object), and notes the late write; the store lands through the returned
owner pointer; `array_builder_end` unpins. The bracketed section is bounded
and allocation-free — the operands are all evaluated before it opens —
which is what makes the pin's spin-lock discipline correct. `seal` does the
same around its one length write.

**`length` starts AT CAPACITY and seal SHORTENS it.** There is one length
field, and it never understates the traceable extent. `array_create`
zero-fills the payload, so the scanner — which walks `length × stride` slots
from birth — reads unwritten slots as NULLs. Each pushed element is
traceable the moment it lands. `build` writes the true count (`_at`) as the
LAST act: readers never see a length larger than what was pushed, and the
trim only discards never-written zeros.

**Stores are barrier-free (`fresh`).** Each slot is written at most once
over the allocator's zero fill, so there is no old edge for the snapshot
barrier to preserve; new edges are announced by `begin`'s redirty note
before the store lands.

Growth (`push` past `_cap`): fresh run at double capacity, `_copyInto`,
the abandoned run simply dropped (never published — builder-owned only —
so it dies as ordinary garbage), then the push retries. The `estimate`
parameter exists to make this path rare.

## Element representation: `T` never crosses the runtime boundary

A C function cannot take a `T` by value — its width varies per
instantiation (1 byte, a pointer, a multi-word struct). So the runtime
primitives are representation-BLIND:

* `array_builder_begin(arr)` — resolve forwarding, pin, note the late
  write; returns the owner pointer the store goes through
* `array_builder_end(arr)` — unpin
* `array_builder_seal(arr, len)` — writes an `int32` at
  `vtable->array_len_offset` under its own begin/end-style bracket

Everything element-typed is a COMPILER special form, inlined after
monomorphisation where the width is a static fact
(`pyast/expression/builtin_op.py`, port `codegen/generate_expr.yafl`):

* `array_builder_alloc` — the ctor's own sized-`NewObject` path
  (`array_create` with this instantiation's vtable). The vtable carries the
  representation: `array_el_size` (stride) and `array_el_pointer_locations`
  (per-ELEMENT pointer mask — a struct element with pointers at words 2 and
  5 has bits 2 and 5).
* `array_builder_store` — the begin/store/end bracket with a typed IR
  `Move` into the indexed trailing array member at its centre:
  `((Array_X_t*)owner)->array.a[i] = val`. Both sides carry the element C
  type from the same monomorphised copy, so a width disagreement is a clang
  error, not a silent smash. The store op itself is byte-for-byte the ctor
  fill's store (new.py:159) re-exposed at a builtin boundary.

Bounds are by construction, not by check: `push` tests `_at < _cap` in YAFL
and takes the growth path otherwise; linearity makes `_at` advance densely.
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

`instance [ambient]<T> Drop<ArrayBuilder<T>>` — an abandoned builder (a
failed parse alternative, an early exit) is consumed by the drops pass so
linearity balances; `discard` seals empty, severing the run's element
references so run and referents die at the next cycle. (Adding this SECOND
generic ambient Drop instance exposed a latent resolver bug — see
`_scope_filtered` in `pyast/expression/access.py`: `unify_generic` callers
must demand every instance placeholder bound, not merely a non-None
mapping.)

## Tests

`tests/test_array_class.py` — exact-estimate, growth, clamp, empty,
discard, implicit drop, pointer elements, linearity rejection, and two
GC-interaction fills (sync and async producer) that force a major cycle
before every push via `gc_debug_major_now`, exercising the scanner tracing
a half-built pointer array and the momentary store brackets interleaved
with compaction. Runtime pin/seal unit coverage rides the existing ctest
suite (object.c debug exports).
