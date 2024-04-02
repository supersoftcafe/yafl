# YAFL-r

## Yet Another Functional Language - Runtime

This project implements the runtime required by YAFL, which includes:
* Fibers for massively parallel workloads. 
* Object basics for GC support and virtual method lookup.
* Garbage collection.

## Garbage collection

A really simple single threaded, compacting, mark-sweep garbage collector.
Safe points are implicitly any call to an allocation function or a call to the
compaction or safe-point functions, at which time a collection and compaction
may occur.

A shadow stack, if used, provides the mechanism for allowing stack based roots
to be scanned and updated after compaction. This is precise, not conservative.

The shadow stack approach leverages the C compilers built in escape analysis.
Basically, we require that the locally declared struct that is the local shadow
stack be linked to the previous shadow stack (provided by the caller) and the
current one be passed to all function calls as the first parameter. The compiler
will always assume that any member of that struct could be modified by any
function call, and so assume that it needs to re-read the value after any
function call.

This makes the collection and compaction mechanism totally safe.

The cost is that extra parameter that we must always pass around. Some
implementations get around this with a global that is updated on entry
and exit of each function. I believe that this is less optimal as it
requires extra store and load operations, and complicates the act of
writing any function as you must remember to unlink the shadow stack.
By passing it as the first parameter, it naturally unlinks on return.

One important thing to note is that an object pointer must always point
to the base of the object. Nothing else is acceptable, and will corrupt
the heap, so no pointer arithmetic, at least not on any pointer visible
to the garbage collector.

## Heap layout

Small to medium size objects are allocated out of 64K pages using a
bump pointer. It's very fast. Every page is 64K aligned.

At the start of the 64K page is a header, some bitmaps used by the 
garbage collector, next/prev list pointers and a pointer to the 
owning heap object. All pages belong to groups under a single heap 
object.

All of this makes garbage collection very easy, as any reference to
an object can be bit manipulated to find the start of page pointer.

Heaps can be merged, by walking the list of 64K pages, moving the to
the new heap, and changing the heap pointer.

During GC references that fall outside of the current heap are easily
detected, and those objects won't be marked.

Large objects are allocated directly from the system using mmap. The
start of the object will look like a 64K page header, and be 64K aligned,
but is marked to indicate that it is actually a large object.

## Virtual method invocation

All method signatures, a combination of name and parameters, are assigned
a globally unique identifier that is a 32-bit integer. A vtable is an
array of id/pointer pairs and a mask for the lookup function to use. To
find a function the caller requests it, providing the vtable pointer and
the id, and the lookup function uses the vtable mask on the id, then starts
scanning the vtable at that location.

All vtables must end with a 0 id and NULL. This is explicitly to either
cause a SEGFAULT or to be detected and reported by the runtime if a lookup
fails to find a function.

A naive vtable could have a mask of 0 and simply list all the functions.
This will work, the lookup function will start scanning at index 0 until
it finds the function with the given id. It won't be efficient.

YAFL will generate vtables with an optimised hash layout and the
appropriate mask to ensure that most lookups succeed on the first
attempt. This will be efficient.

## Fibers

Fibers in YAFL are inspired in part by GO, but don't go quite as far
in their implementation. GO fibers are amazing, and I strongly recommend
reading up on them.

A fiber is a 64K block of memory allocated using mmap, with options to
lazy allocate pages on first access. The final (bottom) page is protected
so that stack overflow will raise a signal that can be handled.

Fibers only support cooperative multitasking. IO libraries in the runtime
will use this and the native AIO capabilities of the OS to efficiently
yield and schedule fibers.

Parallel processing is through the method 'fiber_parallel' that will
schedule N fibers, starting them with the N provided functions and a
single pointer parameter. It is the callers responsibility to arrange
for that pointer to provide all required parameters and a place to
store results. The function returns when all the provided worker
functions complete.

All fibers are scheduled on a work queue local to the current thread.
The local thread will always take the most recently queued job to
work on. Other threads will try to steal the least recently queued job
to work on.

This gives us two emergent properties quite cheaply.
1. New work has priority. When writing some deeply nested tree of function
   calls this effectively manifests as a depth first search.
2. The older fibers tend to be the roots of vast trees of other worker
   fibers, so stealing them on to other threads rapidly spreads the
   work out over the multiple CPU cores.

The benefit of AIO and parallel workloads comes without the cost of
compiler support for async methods. Look at Kotlin and C#, and frankly
many other languages that support async semantics. The compiler output
is complex and clunky. It's memory efficient, but spreads through the
code base like a virus. Fibers are a good compromise, with reasonable
memory efficiency, but also avoiding the OS overhead of millions of
threads.

GO does this very well, with such low memory overhead as to not matter.
YAFL has its 64K per fiber overhead, but this is mitigated by the lazy
allocation of pages, so in reality it's lower. For now, I'd like to avoid
the complexity of stack re-allocations that GO has.

## AIO

I'd like to use io_uring, and maybe will. It's complicated though, by
the fact that it doesn't support file or block device IO. It's great
for network, but not much else.

POSIX asynchronous I/O works for files as well, and whilst not as
performant is a good place to start.

This is coming soon on the 'todo' list.

