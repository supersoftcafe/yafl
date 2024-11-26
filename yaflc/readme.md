
# Enums

How to make it GC friendly?

# Lazy stubs

class Lazy<X>
  var value: X
  var has_value: Bool
  var to_notify: Fiber
  val init: ():X

  fun get_value(): X
    if has_value:
      return X
    else if atomic_cas(to_notify, NULL, SELF_FIBER):
      # It was NULL, but now points to our fiber. This means that we got the right to initialize it.
      value = init()
      has_value = true
        Loop and swap out 'to_notify' waking each fiber until reaches this fiber...   slight problem thinking about how to do this atomically
    else
      SELF_FIBER.next = to_notify
      if atomic_cas(to_notify, SELF_FIBER.next, SELF_FIBER):
        SELF_FIBER.suspend()
      return get_value()

Heap allocation is done in a local temporary context, just like we do with forks.
On completion, compaction is done, but into the original region of the Lazy object. This is known by looking it up.
The Lazy could have been constructed deep in some fork area, but used higher up. That's why we look up the owning context, we don't record it at construction time.

We atomically borrow the tail, and compact into it, then return the tail.
If we fail to borrow the tail, we compact into a new region.
Tangentially, regions should support two tails, and always try allocating from one with smaller remaining space first.

Need to detect circular requests. Since we register the calling fiber as the owner during construction, that can be checked by walking the 'to_notify' list. However, is walking that list thread safe?
Maybe let's have a separate 'owner' field instead.


