# Array — growable values

## Array grows by appending (issue #95)

`Array<T>` is a value over a shared buffer, as a String is. Like List it is
empty or full, and an empty array holds no buffer, so making one allocates
nothing:

```yafl
class [final, pinnable] _ArrayBuf<T>(_used: Int32, [capacity] _cap: Int32, _items: T[_used])
enum Array<T>(_length: Int32)
  enum _EmptyArray()
  enum _FullArray(_buffer: _ArrayBuf<T>)
```

Two general class features carry it:

* **`[capacity]`** on an Int32 field of an array class sizes the storage
  past the length: the object is allocated for the larger of the two, the
  constructor fills `[0, length)`, and the vtable's `array_cap_offset`
  names the field. The collector traces and compaction copies only
  `length` elements, and compaction resets the capacity to the length on
  the copy, so a moved buffer never grows in place — the runtime has
  handled this since String's growable buffers.
* **`subject.items(i) := value`** writes an element of an array field of a
  `[pinnable]` or `[mutable]` object, under the pin, as `subject.field :=`
  writes a field. The index is checked against the capacity when the
  class has one.

Every field is internal. The public count is `size(a): Int`; only
`array.yafl` and its `System::Containers` companions (`rrbtree.yafl`) read
the Int32 `_length` directly. `arrayStream(a)` (the `Stream` instance) lives
beside the container, as List's does.

`append(a, x)` on a full array pins the buffer; if `a` owns its end
(`a._length == _used`) and there is room, it writes element `_used`, then
`_used := _used + 1`, and unpins. Otherwise it copies into a buffer of twice
the size. On an empty array it allocates the first buffer, with room for
two. The combinators match once and then walk the buffer. A value
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

Seq (`Segment<T>|None`, built with `SeqBuilder`) was removed in favour of
`Array<T>`; with it went the pinned construction primitives its segments
used (`array_builder_alloc`, `array_builder_store`, `array_builder_seal`)
and the list-builder runtime calls (`list_builder_link`, `list_builder_slot`,
`list_builder_seal`). The compiler's op lists (`CgFunction.fnOps`) are
Arrays: built once per pass by `push`, then walked in order or by index.

## Tests

`tests/test_builder_gc.py` exercises Array push and List append builds
across GC cycles (sync and async producers), including the snapshot barrier
for copied buffers.
`stdlib_tests/Containers/array_tests.yafl` covers tabulation, convenience
constructors, append/push growth, shared-prefix appends, `pushAll`, the
stream and the combinators.
