YAFL
====

High priority
-------------

* Reserve and use a bit to mark non-gc managed objects
* Command line to build with option to generate assembly
* Standard library

Medium priority
---------------

* Async
* Automatic insertion of forks into tuple generation
* IO using a standard thread based AIO library for simplicity
* Implement full parallel garbage collector

Low priority
------------

* Support for tagged unions at codegen level. 
  * Max 256 tags + 8 bit mask for pointer locations. This puts an upper bound on union size.
  * Nested tagged unions have their mask merged into the parent mask.
* Vtable pointer locations mask needs to be bigger and support location of tagged unions.

Garbage Collector Notes
-----------------------

* Bump pointers
* Generational
* Read or write barrier... not sure..  probably also use forwarding pointers
* GC work happens during block allocation calls.
* Works with threads to have sync points
  * Event loops set a flag on each iteration.
  * At the end of GC stage all flags are cleared.
  * Next GC stage cannot start until all flags are set.
  * This guarantees that all stacks have been emptied since completion of previous stage.
* Ideas
  * Notepad marking of older generation roots
  * Promotion of blocks from older generation back to new generation.
  * During copying, things that mutated since last GC are copied to a different page.
    * This should help to group immutable items together.
  * When updating pointer field, if old value is not null, mark that as seen. But only if we are in a scanning phase.  
    * This will be performant for async heap frames, if initialised to null. Compiler will be able to optimise away many checks.


**GC stages are**

1. Scan roots
   * Between start and end of scanning roots all event loops must have moved forwards
2. 


Background
----------

Yafl runtime is event driven with a thread per core for processing and
another group of threads for async IO, if required. Worker threads
don't block on IO.

The compiler will take care of ensuring that work never takes more than
a few hundred milliseconds per event.

Garbage collection depends upon this behaviour.


Object header
-------------

VTable pointer.
Masked &1 if this is not managed by GC.
Masked &2 if this is a forwarding pointer.


GC scanning
----------

There are two lists of 16KiB pages, the collection set and the new
set. The collection set

1. It is assumed that all mark bits are clear at the start.
2. All worker threads will have a mark set. They will clear the mark on their next iteration.
3. Set the global flag to tell all threads that scanning is in progress
4. Any worker that sees the flag whilst overwriting a pointer field that is not null
   must mark the removed pointer as seen immediately.
5. GC will mark all roots.
6. Set and wait for all workers to clear marks.
7. Start iteratively scanning.
   * After each walk around the collection set, set all markers and wait for them to clear.
   * An entire cycle of scanning results in no change, scanning is done.
8. Completion...  next step

Copying / compaction
--------------------

1. Identify pages that will benefit from copying/compaction.
2. Mark other pages as "target set" to avoid any copying from them.
3. Set global flag to show that we're in the copying phase.
4. Wait for all workers to reset flags.
5. 






GC Again
--------

A global atomic is used to control the stages of garbage collection.
On app start up the stage is 0. This is the only time it can be 0.
All threads work towards the GC goal by intercepting common functions.
A common action is to wait for all threads to progress in their event loops.
This will be denoted simply as WAIT. It is a guarantee that all activities
that are part way through during a stage change of GC is completed.
Sometimes an action needs to be performed on all threads during the WAIT.
This is denoted by "WAIT AND action description"

0. Start GC engine
1. Set a target page count to trigger GC
   * WAIT AND
      * Repeat waiting
2. Set the global _Bool to indicate that a scan is in progress.
   * WAIT AND
      * scan thread local roots
      * mark local pages that are a part of this scan (including bump pointer target)
      * reset the bump pointer to NULL 
3. Scan global roots
   * WAIT
4. Progressively scan all pages.
   * Intercepts the page allocator to scan 16 (suggested) pages per each page allocated.
   * This is only complete when a full walk of all pages results in no change.
   * Needs a global list of currently active pages for all threads to walk
   * Needs a per page atomic to mark as locked
      * Do we skip a locked page, or give up assuming that another thread is doing the work?
   * WAIT after each iteration of progressive scanning
5. Unset the global _Bool that scanning has ended
6. For each page
   * If the page is fully empty, put it on the free list
   * If the page is partially empty, leave it on the active list
      * Future enhancement 1, also re-use partially empty pages if there is enough contiguous space
      * Future enhancement 2, compaction,  but it needs read barriers
7. Goto 1


