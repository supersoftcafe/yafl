// yafllib/once.h — write-once publication for [mutable] objects.
//
// One primitive: CAS a child slot from NULL to a value, exactly once. It is
// what lets a lock-free structure grow in place while every reader sees either
// "not there yet" or a fully constructed node — never a half-built one.
//
// The containing class MUST be declared [mutable] in YAFL. That is not a
// style preference: a mutable object is never relocated by the collector, so
// the write cannot land in a copy that is then abandoned. Publishing into a
// compactable object would silently lose entries.
//
// See docs/memoize-proposal.md for the full argument.
#pragma once

#include "yafl.h"

// Publish `value` into child slot `slot` of `obj`, if that slot is still NULL.
// Returns 1 on success, 0 if another thread got there first (or on a bad
// argument). The caller re-reads the slot on failure and adopts the winner.
//
// SLOT ADDRESSING: the child slots are the last N pointer fields of the class,
// declared consecutively and last, so they occupy the top set bits of the
// vtable's pointer mask. Offsets cannot be derived from object_size because
// structs are GC_ALLOC_GRANULE-aligned and routinely carry trailing padding.
EXPORT object_t* yafl_cas_once(object_t* self, object_t* obj, int32_t slot,
                               int32_t nslots, object_t* value);
