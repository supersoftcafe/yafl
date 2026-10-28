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

    // Highest set bit = the LAST pointer field = the last child slot. The
    // slots are declared consecutively, so slot i sits nslots-1-i words below
    // it. Deriving this from the mask rather than from object_size is what
    // makes it immune to the struct's trailing alignment padding.
    vtable_t* vt = vtable_untag(owner->vtable);
    ptr_mask_t mask = vt->object_pointer_locations;
    int hi = mask ? 63 - __builtin_clzll(mask) : -1;
    if (hi < nslots - 1) {
        object_unpin(owner);
        return integer_from_int32_noalloc(0);   // malformed layout: refuse
    }

    object_t** field = (object_t**)owner + (hi - (nslots - 1) + slot);

    // Write-once: NULL -> value, never value -> value. The PIN is the mutual
    // exclusion, so a plain read and an ordinary object store replace the
    // compare-and-swap this needed when any thread could be writing at any
    // time. Readers deliberately do not take the pin; the store macro's
    // publication fence orders the value's initialisation before the pointer
    // to it, and they read through the pointer.
    bool ok = (*field == NULL);
    if (ok)
        GC_STORE_IN(owner, *field, 1, value);
    object_unpin(owner);
    return integer_from_int32_noalloc(ok ? 1 : 0);
}
