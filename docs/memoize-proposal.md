# `memoize` — a function that wraps a function, same signature

Status: PROPOSAL for discussion. Nothing implemented.

    fun memoize<A,B>(f: (:A): B): (:A): B where BasicEquality<A>

Call it once, use the result exactly as you used `f`. No call site changes, no
threading a dictionary through twelve signatures.

**THE CONTRACT — two halves, and the second is the point:**

1. `f` MAY be called more than once for the same argument. No exactly-once
   guarantee; that would require blocking, which this language forbids.
2. **Every caller receives the SAME answer for the same argument.** The first
   value published wins; a thread that loses the race discards the value it
   computed and returns the winner's.

(2) is what makes `memoize` useful for a function that is not quite pure — the
database read that *should* be stable but that no type system can vouch for.
Wrapping it does not just make it faster, it makes it *consistent*: the wrapped
function answers a given argument the same way for as long as the cache lives.
Without (2) a memoize is only a performance tool; with it, it is also a
purifier. An earlier draft of this document stated (1) and omitted (2), which
made the wrapper useless for exactly the case that motivates it.

---

## 1. The thing to settle first: this needs hidden mutable state

A memo cache must survive between calls to the returned function. YAFL has no
mutable containers, by an explicit standing decision. So the honest framing is
not "how do I write this in YAFL" but "is this an acceptable exception, and
where does the mutation live".

I think it is acceptable, for one reason: **memoising a pure function is
observationally pure.** `f` returns the same `B` for the same `A` by
construction, so a cache cannot change any answer — only how long it takes.
Nothing in the program can distinguish `memoize(f)` from `f`. That is a
stronger guarantee than "mutation the user cannot reach"; it is "mutation with
no observable consequence at all".

The language already relies on exactly this argument twice:

- **`[lazy]` lets** compute once and reuse. That IS memoisation — of a
  zero-argument function, with a one-entry cache and a `lazy_init_flag` to say
  whether it has run. `memoize` is the same idea keyed by an argument.
- **the string hash cache** — a lazily-computed FNV int32 written into an
  otherwise immutable string header on first use.

So the precedent is not "YAFL allows mutation"; it is "YAFL allows caching
where the cache is unobservable". `memoize` is the general case of a special
case the language already ships.

**Where the mutation lives: in C, not in YAFL.** No `Cell<T>`, no mutable
container in the language, nothing new a user can reach for. The cache is a
runtime object behind an opaque handle, like a log span's token.

## 2. Signature and arity

No varargs, so one overload per arity, as with `System::format` and
`System::Log`:

    fun memoize<A,B>    (f: (:A): B):        (:A): B        where BasicEquality<A>
    fun memoize<A,B,C>  (f: (:A, :B): C):    (:A, :B): C    where BasicEquality<A>, BasicEquality<B>
    fun memoize<A,B,C,D>(f: (:A, :B, :C): D): (:A, :B, :C): D  where …

Three is probably enough to start (it covers the compiler's memo sites); more
is additive. Multi-argument keys are the tuple of arguments, which needs
`BasicEquality` on each — the same constraint `Dict` already requires.

## 3. The structure: a hash tree grown in place, zero-to-value

Not a persistent Dict swapped behind a holder — that concentrates every insert
on one word. Instead the cache IS a tree, and it grows by filling slots that
start at zero:

    class MemoNode<A,B>
      key      : A          # set at construction, never changes
      value    : B          # set at construction, never changes
      hash     : Int32
      children : [k]        # WRITE-ONCE slots, NULL until filled

`memoize` allocates the root node and the returned closure captures it. **The
captured pointer never changes** — there is no mutable holder anywhere. The
only mutation in the whole design is a child slot going NULL -> node, exactly
once, by CAS.

    fun memoize<A,B>(f: (:A): B): (:A): B where BasicEquality<A>
      let root = _memoRoot<A,B>()
      ret (a: A) => _memoGetOrCall(root, a, f)

Lookup walks the tree by successive bits of `hashOf(a)`, comparing keys on a
hash match. Insert walks the same path and CASes a freshly-built node into the
first NULL slot it finds.

### Why zero-to-value is the whole trick

A slot only ever goes from zero to a value, never value to value. That buys:

- **No ABA**, so a plain CAS is sufficient — no versioning, no hazard pointers.
- **Readers need no synchronisation**: a slot reads as either NULL (not there
  yet — keep looking, or miss) or a fully-constructed node. There is no
  intermediate state to observe, because the node is built before it is
  published.
- **Nodes stay classified immutable, so they still compact.** This is the
  property that makes the design viable: a `Lazy<T>`-per-entry cache would mark
  every node mutable and leave an uncompactable hole per entry, fragmenting the
  heap in proportion to how well the cache works. Here the contents only ever
  gain, never change — the same argument that lets the string header cache its
  hash in place.

### Node layout — and why it cannot be a HAMT

The classic Bagwell HAMT node is a 32-bit bitmap plus a DENSELY PACKED array
holding only the children that exist; the child index is
`popcount(bitmap & (bit - 1))`. Memory-efficient and O(1).

**It is incompatible with zero-to-value.** Inserting sets a bitmap bit and
grows the packed array — the node is REPLACED, not filled. That is a
value-to-value change, which is exactly what we cannot do, and it is why Ctries
CAS a parent's indirection node instead of a slot. Compression and write-once
are mutually exclusive; we must give up the compression.

So: **fixed-size slot arrays, and a node carries its own key and value.**

    class MemoNode<A,B>
      key      : A            # set at construction
      value    : B            # set at construction
      hash     : Int32        # set at construction
      children : [1 << BITS]  # write-once slots, NULL until filled

The second half matters as much as the first. If a slot could hold a *leaf*
that later had to become a *branch* on collision, that is a slot rewrite and
the rule breaks. Giving every node its own key/value means a slot only ever
goes NULL -> node, once, for the life of the cache. Nothing is ever replaced,
resized, or deleted — which is also precisely the condition (§4a) that lets us
CAS a slot directly and skip Ctrie I-nodes.

This is the shape Areias & Rocha describe for tabling: fixed size structures,
and "persistent memory references" — references that never change once written.

### Lookup

A plain walk. No CAS, no locks, no retry; slots read as either NULL or a
fully-constructed node.

    h    = hashOf(a)
    node = root
    d    = 0
    loop:
      if node == NULL:                    ret MISS
      if node.hash == h && node.key == a: ret node.value      # HIT
      slot = (h >> (d * BITS)) & ((1 << BITS) - 1)
      node = load(node.children[slot])    # acquire load
      d    = d + 1

The acquire load is what pairs with the release edge the inserting CAS
provides; together they guarantee a reader that sees a node also sees its fully
initialised key and value (§4a — this is the part a plain store would get wrong
on a weakly-ordered target).

Beyond `32 / BITS` levels the hash is exhausted; keys colliding that far share
a chain through one designated slot, compared by full key equality. Rare enough
that the linear walk is irrelevant.

### Choosing BITS — a memory trade, not a speed one

Because every node carries `1 << BITS` slots whether or not it uses them, the
branching factor sets the per-entry cost:

    BITS=2  ->  4 slots   ~7 words/entry   depth <=16    (~56 bytes)
    BITS=4  -> 16 slots  ~19 words/entry   depth <= 8    (~152 bytes)
    BITS=5  -> 32 slots  ~35 words/entry   depth <= 6    (~280 bytes)

A HAMT can afford BITS=5 because its arrays are compressed; we cannot. Given
that allocation is the dominant cost at self-host scale (~150-200k instructions
of GC per 16KB page against a large live heap), **BITS=2 is the right default**
— a depth of at most 16 pointer hops is nothing next to allocating 280 bytes
per entry. This is the one parameter worth measuring rather than assuming.

### Insert protocol

    v    = f(a)                        # may allocate
    h    = hashOf(a)
    node = root
    depth = 0
    loop:
      slot  = (h >> (depth * BITS)) & MASK
      child = load(node.children[slot])
      if child != NULL:
        if child.hash == h && child.key == a: ret child.value   # someone won
        node = child; depth = depth + 1; continue
      fresh = MemoNode(a, v, h)        # allocate BEFORE the window below
      ── resolve `node` and `fresh` to their forwarding TAILS ──
      ── NO ALLOCATION from here to the CAS ──
      if CAS(node.children[slot], NULL, fresh)
        ret v                          # installed
      # LOST THE RACE. Re-read and continue from whatever the winner installed.
      # The value `v` we just computed is DISCARDED — we return the winner's,
      # which is what makes every caller see one answer (contract half 2).
      continue

Contention is naturally distributed: two threads conflict only when they touch
the *same slot*, which is why this needs no sharding. **Fail and retry** —
on a lost CAS we re-read that slot and carry on down the winner's node, so the
loser's work is not thrown away and the tree keeps growing. `f` may be called
more than once for the same argument; that is accepted (§4.4).

## 4. Lifetime, purity, and the GC obligations

### 4.1 The cache is an ordinary object, not a root — so it needs no limit

Reachable only from the closure `memoize` returned; when that goes out of
scope, so does the tree. No root registration, no eviction, no capacity.
**Each memoize cache is short-lived by construction.**

(An earlier draft proposed mandatory LRU capacity. That was wrong — it treated
the cache as a process-lifetime structure.)

### 4.2 Impure `f` is the programmer's risk

Rejecting impure functions is attractive and unenforceable — a function reading
a database *should* be pure in the sense that matters, and no type system here
can know it. Document the contract; memoising something that genuinely varies
gives a stale answer, and that is the caller's call.

### 4.3 Lost entries are fine; a cache that stops caching is not

`f` may run more than once for the same argument, and an entry may occasionally
be lost. What is not acceptable is behaviour that degrades to *no cache* under
parallelism. The retry-on-lost-CAS above is what guarantees the floor is a
small loss rather than the whole benefit: a thread that loses a race descends
into the winner's subtree and installs there, so the tree still grows.

### 4.4 Nodes are MUTABLE — the only design that keeps the contract

RULED. Memo nodes are mutable objects.

The reasoning is forced. Contract half 2 says every caller sees the same
answer. That requires a published entry to be durable: if a store can be lost,
one caller returns `v1`, a later lookup misses, recomputes, and returns `v2` —
and for a not-quite-pure `f` those differ. The contract dies exactly where it
was supposed to earn its keep.

So "accept the loss", borrowed from the string hash cache, does NOT transfer.
That cache tolerates loss because recomputation yields the SAME bits; our whole
premise is that it may not. (An earlier draft made this mistake — it imported a
mechanism from a case where loss is harmless into one where it is fatal.)

Nor does read-back verification close it: the mover can copy the object, the
mutator can then write to the source AND read it back successfully, and only
then does the mover install forwarding. The window narrows and never shuts.

Mutable objects are not moved, so writes cannot be lost. That is the whole
argument, and it is why the earlier fragmentation objection has to yield.

**What it costs, and the part that is not obvious.**

Fragmentation is milder than feared: mutable objects already allocate onto
their own pages (`object.c`, `page->head.mutable`, separate bump pointers), so
the holes never perforate the immutable heap. A cache allocated together and
dropped together tends to empty its pages wholesale — the good case for a
non-compacting allocator.

The real cost is GC throughput. From the generational design note:

    minor cycles trace only young pages plus the (small) mutable set

Old IMMUTABLE pages promote out of the rotation and are skipped entirely.
Mutable pages never leave it. So **a memo cache is re-traced on every GC cycle
for as long as it lives**, and the "(small)" in that comment stops being true.
Measured context: a self-compile runs ~1.4M cycles and marking dominates GC
cost, so a large or long-lived cache would be expensive in a way no memory
metric reports.

This makes "each cache should itself be short-lived" load-bearing rather than
stylistic — it is what keeps the mutable set small. A cache held for the
duration of a compile is a different proposition from one scoped to a pass, and
the difference will not show up as memory.

**Natural follow-up (not now).** A write-once node whose slots are all filled
can never change again — it is immutable in fact, just not in classification.
`[once]` fields give the collector enough information to notice that and let
such a node promote or compact like any other. That would recover most of the
cost above, and it is a property only the write-once discipline makes
available.

**Still required:** the CAS (racing writers store DIFFERENT pointers, so a
single winner must be chosen — that is what delivers one answer), and
release-on-publish paired with acquire-on-read so a reader that sees a node
also sees its initialised contents.

### 4.5 What still needs deciding

- Branching factor and max depth before chaining on hash collision.
- Whether a store lost to a compaction copy should be COUNTED. Losing it is
  correct and cheap; a silent loss rate nobody can see is how a cache quietly
  stops working. One `count("memo", "store.lost", 1)` would answer it, and
  System::Log now exists to carry it.
- Whether the CAS needs an explicit release, or the platform primitive already
  provides one — and the matching acquire on the read path.
- Whether the memo sites this replaces are worth the machinery at all. Measure
  first: `complex_enums` threads a memo Dict through ~8 signatures, but nobody
  has ever measured what those sites cost. Today's lesson was that three of
  four confident optimisation instincts were wrong.

## 4a. Prior art (researched 2026-08-02)

**The contract above is a known, named design.** Rust's `once_cell::race` is
"a thread-safe, non-blocking, *first one wins* flavor of OnceCell", and
`OnceBox::get_or_init` documents precisely both halves: **"all threads will
return the same value, produced by some `f`"** and **"more than one `f` can be
called"**. Threads "don't block, execute initialization function together, but
only one of them stores the result". That is this proposal's contract verbatim,
in a widely-used library — good evidence the trade is the right one and not a
compromise.

**The zero-to-value rule is the "racy single-check idiom"** (Effective Java,
Item 83) — and its canonical use is `String.hashCode`, the same precedent YAFL
already relies on for its own string hash cache.

  IMPORTANT CAVEAT the literature is explicit about: for a REFERENCE field the
  idiom needs the published object to be immutable, or the field to be
  volatile, so a reader cannot observe a partially-constructed object. A plain
  store would appear to work on x86 (stores are already release-ordered) and
  break on a weakly-ordered target. **Using CAS rather than a plain store gives
  the release edge for free** — `once_cell::race` uses Acquire/Release
  throughout and notes the overhead is very small. So CAS is not only about
  not losing updates; it is what makes publication safe.

**The structure is a lock-free hash trie** (Prokopec's Ctries, 2011). The
research turns up one subtlety worth knowing: Ctries do NOT CAS directly into a
node's child array — they introduce *indirection nodes* (I-nodes) that persist
while nodes above and below change, because a direct CAS is unsound once you
support removal and compression.

  We support neither. Slots are write-once and nothing is ever deleted or
  resized, which is exactly the condition that makes the direct CAS sound and
  lets us skip I-nodes entirely. There is published work on precisely this
  simplification — a lock-free hash trie designed for *tabling* in logic
  programming, which is memoisation by another name.

**The exactly-once alternatives are all blocking.** Goetz's `Memoizer` caches
`Future`s in a `ConcurrentHashMap` so latecomers wait on the in-flight
computation; `computeIfAbsent` locks the bin. Both give exactly-once at the
cost of a thread waiting — ruled out here by "YAFL never does synchronous
await". So redundant computation is not a compromise we are settling for; it
is the only option consistent with the language, and the literature says it is
a good one.

## 4b. Where should this live, and does it need a language feature?

### T's representation never reaches the CAS

Worth stating plainly, because it looks like a problem and is not: **the
write-once slots are always child NODE pointers — never a `T`.** A slot is
`MemoNode<A,B>|None`, so the CAS is always single-word on a reference, whatever
`A` and `B` turn out to be.

`A` and `B` appear only as the node's `key` and `value`, which are set at
construction and never mutated. So an unboxed `Int32` key, a two-word tuple
value, a tagged small-Int, and a heap `String` are all handled by the ordinary
machinery: monomorphisation gives each instantiation a concrete layout, and the
vtable's pointer mask tells the GC which of those fields are references. No
special casing, no boxing.

That also settles the "0 is a legitimate Int32" objection to zero-to-value: we
never use zero as an empty marker for a `T`. Only reference slots are written
after construction, and for those NULL is unambiguous.

### Therefore: the structure belongs in YAFL, not C

Writing it in C means one of two bad options. Either it is generic over
`object_t*` only — which boxes primitive keys and values, allocating exactly
where the cache is supposed to save — or it needs a distinct node layout and
GC pointer mask per instantiation, which is hand-reimplementing
monomorphisation. The compiler already does that job correctly.

So: the trie in YAFL, and from C only the one primitive YAFL cannot express.

### The one language feature worth adding: a write-once reference field

    class [final] MemoNode<A,B>(key: A, value: B, hash: Int32,
                                c0: [once] MemoNode<A,B>|None,
                                c1: [once] MemoNode<A,B>|None,
                                c2: [once] MemoNode<A,B>|None,
                                c3: [once] MemoNode<A,B>|None)

`[once]` on a REFERENCE field means: starts NULL, may be published exactly once
by a CAS intrinsic, never plain-assigned. **A class with any `[once]` field is
mutable** — the compiler sets `is_mutable` in its vtable, so the collector does
not move it and the publication cannot be lost (§4.4). That link should be
automatic; requiring the author to remember both is how the invariant breaks. (With BITS=2 these are four named
fields, which also sidesteps the separate question of whether `Array<T>`
elements could be individually publishable.)

This is not a new concept in the language, it is the general case of two that
already exist:

- a **`[lazy]` let** is a `[once]` field with compute-on-read and a
  `lazy_init_flag`;
- the **string hash cache** is a `[once]` primitive field, published racily.

What the compiler buys us by knowing about `[once]` is the part that is
otherwise a comment and a code review:

1. **Enforce zero-to-value.** Reject any plain assignment to the field, so the
   invariant the whole design rests on cannot be broken by a later edit.
2. ~~Enforce a no-allocation window~~ — WITHDRAWN. That rule was based on a
   false model of when compaction runs (§4.4); there is no window to enforce.
3. **Emit the right barrier and ordering** — release on publish, acquire on
   read — rather than trusting each hand-written site. Cheap on x86 and
   load-bearing on anything weakly ordered.

I would scope the CAS intrinsic to the stdlib rather than exposing raw CAS to
user code. "YAFL stays pure" is a design position, and handing out unsynchronised
publication is how a pure language acquires an unsound-lock-free-structure
problem.

## 4c. How other collectors resolve late-init vs compaction (researched 2026-08-02)

The ruling in §4.4 is right for the collector as it stands. But the cost it
buys — nodes permanently unmovable and permanently re-traced — is **not
inherent to mutation**. It follows from one specific choice: in YAFL,
`is_mutable` is a bit in the VTABLE, so mutability is a property of the TYPE.
Every instance is mutable forever, therefore traced forever, therefore
unmovable forever. No other system surveyed makes it a type-level property.

### 1. Dirty/clean is a per-object STATE, not a classification (GHC, card marking)

GHC keeps mutable arrays on a mutable list with a header flag, `MUT_ARR_DIRTY`
or `MUT_ARR_CLEAN`. A write sets DIRTY; **the GC turns DIRTY back into CLEAN
once everything the object points to is in the same generation or older.** Only
the mutable list is traversed, and a clean object costs nothing.

Card marking (HotSpot and friends) is the same idea at page granularity: the
write barrier marks a card, only dirty cards are rescanned, and **the object is
still compacted**. Nothing about having been written exiles an object from
relocation.

Applied here: a memo node is written once, traced on the next cycle, and — its
children being nodes of the same cache, allocated together — would go CLEAN and
drop out of the scan set. Exactly the property §4.4 says we cannot have.

Note YAFL already relies on this invariant, just statically: "an old immutable
page can never reference a young object". GHC's rule is the dynamic per-object
form of the same reasoning.

### 2. Writes are never lost during a copy — barriers, not immutability (ZGC, Shenandoah, C4)

The reason §4.4 had to rule out compaction is that a write can land in a copy
the collector then abandons. Concurrent collectors solve this directly.
Shenandoah gives every object a Brooks forwarding pointer; ZGC and C4 use a
loaded-value barrier. All maintain the **to-space invariant**: a mutator never
holds a from-space pointer, because the load barrier redirects it — "possibly
including performing the relocation, in competition with GC threads".

So the write always lands in the live copy and cannot be lost. The cost is a
barrier on every reference load, which is a large commitment — but it shows the
loss is a consequence of this collector's relocation protocol, not a law.

### 3. A pure language already mutates constantly: GHC thunks

Worth stating because it undermines the intuition that purity implies immutable
objects. GHC cannot update a thunk in place (the result may be larger), so it
overwrites the thunk with an INDIRECTION to the value, and the copying collector
short-circuits indirections while copying. Laziness IS late initialisation, it
happens on every thunk in the program, and a copying generational GC copes.

### 4. Write-once is a named, first-class concept: HotSpot `@Stable`

`@Stable` marks a field "whose component variables change value at most once":
the VM may "read the field once and, if it is no longer its default value
(zero), trust the field never changes again". That is the zero-to-value rule
verbatim, and JDK 25 previews a `StableValue` API for lazy constants built on
it. Notably HotSpot uses the property for OPTIMISATION — constant-folding the
loaded value — not merely for GC bookkeeping.

### What this suggests for YAFL (not proposing, just what the research says)

The `[once]` attribute of §4b would give the collector information it currently
lacks: which fields may be late-initialised, and therefore which objects are
mutable *for a while* rather than *by type*. Two futures that would recover the
§4.4 cost, in increasing order of ambition:

- **Sealing.** A write-once object whose slots are all filled can never change
  again. `@Stable`'s "no longer default ⇒ trust forever" is the same reasoning,
  and it would let such a node promote and compact like any other.
- **Dirty/clean state** (GHC's model). More general and proven at scale in a
  pure functional language with a generational copying collector: trace an
  object while it is dirty, drop it from the scan set when its referents are
  old enough. This subsumes sealing and would apply to every mutable object in
  the runtime, not just memo nodes.

Neither is needed to ship `memoize`. Both would remove the reason §4.4 had to
choose between a durable cache and a compactable heap.

## 5. Alternative: a `[memo]` attribute

    fun [memo] expandSpec(s: Spec): Spec

Reads better, no closure allocation, and the compiler can key on the
monomorphised function identity. But it is a language feature, it cannot
express a capacity, and it hides an unbounded cache behind an innocuous
attribute. Memory records that a language-level `[memo]` needs a design
discussion — this document is meant to be part of it, and my view is that the
function form should come first: it is a library, it is explicit about cost,
and if it proves itself the attribute becomes sugar over it.

## 6. What it would replace

`complex_enums.yafl` alone threads `memo: Dict<String, Spec>` through about
eight signatures, each returning `(spec, memo)` pairs purely to carry the cache
back out. That is the pattern `memoize` deletes. It is also worth measuring
first: with spans now available, we can see what those memo sites actually
cost before deciding how much this buys.

## 7. Recommendation

Ship `memoize<A,B>(f)`: a hash tree grown in place, child slots going
zero-to-value by CAS with retry, no locks, no shards, no holder, no capacity —
the object graph bounds the lifetime and the zero-to-value rule keeps every
node compactable. Arities 1-3, `where BasicEquality` on the key types. `f` may
be called more than once for an argument; that is the accepted trade for never
degrading to no cache.

The load-bearing detail is the GC contract in 4.4: resolve to the forwarding
tail, and do not allocate between that resolve and the CAS.
