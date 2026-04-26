# Review: Event loop & thread handling (`thread.c`)

Focused audit of the worker pool, work queues, and wake-up mechanism in
`yafllib/thread.c`. Findings only — no fixes applied. Line numbers reference
the file as of this review.

## Summary

The worker pool implements a fixed-size thread-per-core model with two queues
per worker: a single-producer-multiple-consumer **local** queue (owner enqueues,
any thread can steal) and a multi-producer-single-consumer **sideload** queue
(any IO/interrupt context enqueues, the owner alone consumes). There is one
real correctness bug (a lost-wakeup race against sideload producers), one
likely GC correctness bug (write barrier on the wrong end of the sideload hop),
a couple of minor latent correctness issues, and several efficiency
opportunities.

## Correctness

### B1 — Lost-wakeup race against sideload producers (HIGH)

`_thread_wait` (lines 76–88) re-checks `local_queue_head->next` under the
mutex, but **not** the sideload queue. Because `thread_work_post_io` enqueues
to sideload and checks `consumer_waiting_flag` without synchronising against
that re-check, the standard Vyukov enqueue/flag dance is broken.

Concrete trace:

1. Worker A's main loop sees sideload empty at lines 165–166.
2. Producer thread B enqueues to A's sideload (line 253).
3. B reads `consumer_waiting_flag` → `false` (A has not set it yet). B does
   not wake.
4. A enters `_thread_wait`, sets flag `true`, takes lock.
5. A checks `local_queue_head->next` (empty, because the local queue is
   owner-only-produced and the owner is A, which is about to sleep). A calls
   `pthread_cond_wait`.
6. A sleeps indefinitely — the sideload item is not noticed until some
   unrelated producer posts further work.

Two things are wrong:

- The re-check is on the wrong queue. The local queue cannot have grown while
  A was about to sleep — A is its only producer.
- The sideload queue is the one that needs the re-check, and that check is
  missing.

Fix must be structural: the pre-wait re-check must cover
`_locals.sideload_queue_head->next`. The `"TODO: This is all a bit dodgy..."`
comment at line 193 is the concrete form of this suspicion.

### B2 — `GC_MARK_SEEN` on the wrong end of the sideload hop (MEDIUM)

`_thread_local_queue_try_steal` correctly marks the old head being unlinked
(lines 108–110):

```c
GC_MARK_SEEN(&head->parent);   // mark OLD head being unlinked
CAS(local_queue_head, head, node);
```

The sideload consumer in `_thread_main_loop` does the opposite (lines 165–170):

```c
worker_node_t* head = _locals.sideload_queue_head;
worker_node_t* node = head->next;
if (node) {
    GC_MARK_SEEN(&node->parent);            // marks NEW head
    _locals.sideload_queue_head = node;     // overwrites root, abandoning old head
    ...
```

The old `head` (the sentinel about to be abandoned) is what needs the
snapshot-at-the-beginning mark — not `node`. After the root assignment,
nothing holds a reference to `head`; if the collector is mid-scan and has
not yet reached it, it gets missed. `try_steal` does this correctly; the
sideload consumer does it backwards.

### B3 — `_thread_countdown_to_gc_start` depends on entrypoint returning (LOW)

`_thread_countdown_to_gc_start` is seeded to `thread_count` in `_thread_init`.
Thread 0 decrements only *after* `__entrypoint__` returns (line 157). If the
user's entrypoint calls its continuation synchronously, `__exit__` calls
`exit()` and thread 0 never reaches line 157. With `thread_count = 2`, the
non-0 thread decrements from 2 to 1 (non-zero branch, no `gc_start()`), and
`gc_start()` is never invoked.

Any non-trivial program saves us, but the dependency is latent. Consider
starting GC when the *first* thread reaches its event loop instead of the
last.

### B4 — Hardcoded thread count (LOW)

`intptr_t thread_count = 2;` (line 201) contradicts the architecture doc's
"exactly one thread per CPU thread." Obvious placeholder.

## Efficiency

### E1 — Blanket seq_cst on atomics

Every `atomic_load` / `atomic_store` / `atomic_exchange` / CAS uses default
ordering (seq_cst). On x86 it's cheap; on aarch64 (listed in
`CACHE_LINE_SIZE`) each seq_cst store emits a full barrier. Acquire/release
is enough for everything here:

- `local_queue_head`: acquire on consumer load, release on CAS, release on
  producer store to `->next`.
- `sideload_queue_tail`: seq_cst on the exchange **is** needed for the
  flag race to be water-tight — that is the one genuine exception.
- `consumer_waiting_flag`: seq_cst on the store and load is what makes the
  fence pattern work — keep seq_cst here if we adopt the Vyukov fix.

Net: most loads can drop to acquire, most stores to release; only the flag
+ exchange pair needs seq_cst.

### E2 — Cache-line layout of `worker_queue_t`

The struct is padded externally to `CACHE_LINE_SIZE * 2`, but internally the
producer-hot fields (`sideload_queue_tail`, `consumer_waiting_flag`) and the
consumer-hot fields (`local_queue_head`, `lock`, `cond`) share a line at the
struct's head. Every IO post from a remote core bounces
`sideload_queue_tail`'s line, which drags `local_queue_head` with it —
precisely the line stealers on other cores are trying to read. Splitting
into two sub-cache-lines inside the struct would remove that false sharing.

### E3 — `_io_post_counter` contention

Single global `atomic_fetch_add` on every IO post (line 251). Fine with one
reactor thread, painful under many producers. Easy to make per-producer
(e.g., a `thread_local` counter seeded with thread id) and lose nothing.

### E4 — `_thread_wake` always takes the mutex

POSIX allows `pthread_cond_signal` without holding the lock if the flag/check
is ordered correctly. Taking the mutex per wake costs a syscall on
contention. Once B1 is fixed with a proper memory barrier, the lock can come
off the wake path — the consumer still needs it around `cond_wait`, but the
producer does not.

### E5 — All threads prefer the same direction when stealing

The loop at lines 184–186 always starts at `(thread_id + 1) % length`. Each
thread has a different `+1` neighbour, so cache contention on the first
steal target is distributed, but every thread walks in the same direction,
so a single busy queue gets piled on if the first target is empty. A
randomised or XOR-with-id start would smooth this. Low priority at 2
threads.

## Design

### D1 — The local-queue check in `_thread_wait` is vestigial

The local queue's only producer is the owner thread, via
`thread_work_post_fast`, which runs only inside a dispatched event on that
thread. A thread entering `_thread_wait` is demonstrably not inside an event
on its own work. The re-check at line 81 therefore can **never** be
satisfied by a new item. It is dead code that happens to be harmless only
because the real race is on the *other* queue. Replacing it with the
sideload check is both the fix for B1 and the removal of D1.

### D2 — The two queues are different data structures in the same uniform

`sideload_queue_*` is an MPSC (many IO producers, single consumer = the
owning worker). `local_queue_*` is SPMC (single producer = owner, many
consumers = stealers). They are both `_Atomic(worker_node_t*)` with
similar-looking enqueue/dequeue sites, which makes it easy to conflate
their rules. B2 looks like exactly that conflation. Pulling them into two
clearly-named types with separate invariants would make the file much
easier to audit.

## Smaller notes

- `assert(queue->local_queue_head)` (line 162) runs every iteration in
  release builds; move under `#ifndef NDEBUG`.
- `cond_wait` wrapped in `if`, not `while` (line 82). Spurious wakeups are
  harmless because the outer loop retries, but the `while` convention is
  safer.
- `declare_local_roots_thread` roots `_locals.local_queue_tail` "for
  bug-hilighting" (line 64). Reasonable temporarily, worth pulling out
  before shipping.
- `object_pointer_locations` on `_worker_node_vt` (lines 9) includes both
  `next` and `action.o` — correct, but relies on `fun_t`'s layout. Worth a
  comment.

## Priority ordering for fixes

1. **B1** — real deadlock risk, especially once true async IO lands and
   sideload post rates climb.
2. **B2** — latent GC correctness. Low chance of firing today; easy to
   align with `try_steal`.
3. **E2** — layout of `worker_queue_t`. Measurable under load; cheap change.
4. **D1** — folded into B1.
5. **B3/B4** — clean up as part of any broader init-path overhaul.
6. **E1, E3, E4, E5** — tune when profiling shows them.
