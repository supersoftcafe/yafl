// yafllib/once.c — see once.h.
#include "once.h"

EXPORT object_t* yafl_cas_once(object_t* self, object_t* obj, int32_t slot,
                               int32_t nslots, object_t* value) {
    (void)self;
    if (obj == NULL || nslots <= 0 || slot < 0 || slot >= nslots)
        return integer_from_int32_noalloc(0);

    // Take the pin on the CURRENT copy. This does two jobs at once: it
    // excludes every other writer, and it stops the compactor relocating the
    // object out from under the store — the failure that used to force the
    // whole class to be declared [mutable], and with it a lifetime in the
    // young rotation.
    object_t* owner = object_pin_resolve(obj);

    // The page may have aged into the old generation. Say so BEFORE writing:
    // a cycle that opens between here and the store then already treats the
    // page as dirty, rather than skipping it and losing the young referent.
    gc_note_late_write(owner);

    // Highest set bit = the LAST pointer field = the last child slot. The
    // slots are declared consecutively, so slot i sits nslots-1-i words below
    // it. Deriving this from the mask rather than from object_size is what
    // makes it immune to the struct's trailing alignment padding.
    vtable_t* vt = vtable_untag(owner->vtable);
    ptr_mask_t mask = vt->object_pointer_locations;
    int hi = 63;
    while (hi >= 0 && !((mask >> hi) & UINT64_C(1))) hi--;
    if (hi < nslots - 1) {
        object_unpin(owner);
        return integer_from_int32_noalloc(0);   // malformed layout: refuse
    }

    object_t** field = (object_t**)owner + (hi - (nslots - 1) + slot);

    // Write-once: NULL -> value, never value -> value. The PIN is now the
    // mutual exclusion, so a plain read and a plain store replace the
    // compare-and-swap this needed when any thread could be writing at any
    // time. The store keeps RELEASE order: it pairs with the reader's acquire
    // so whoever sees the pointer also sees the node behind it fully built,
    // and readers deliberately do not take the pin.
    bool ok = (*field == NULL);
    if (ok)
        __atomic_store_n((uintptr_t*)field, (uintptr_t)value, __ATOMIC_RELEASE);
    object_unpin(owner);
    return integer_from_int32_noalloc(ok ? 1 : 0);
}
