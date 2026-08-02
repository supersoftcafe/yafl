// yafllib/once.c — see once.h.
#include "once.h"

EXPORT object_t* yafl_cas_once(object_t* self, object_t* obj, int32_t slot,
                               int32_t nslots, object_t* value) {
    (void)self;
    if (obj == NULL || nslots <= 0 || slot < 0 || slot >= nslots)
        return integer_from_int32_noalloc(0);

    // The object is [mutable], so it is never relocated and `obj` is current.
    vtable_t* vt = object_get_vtable(obj);
    ptr_mask_t mask = vt->object_pointer_locations;

    // Highest set bit = the LAST pointer field = the last child slot. The
    // slots are declared consecutively, so slot i sits nslots-1-i words below
    // it. Deriving this from the mask rather than from object_size is what
    // makes it immune to the struct's trailing alignment padding.
    int hi = 63;
    while (hi >= 0 && !((mask >> hi) & UINT64_C(1))) hi--;
    if (hi < nslots - 1)
        return integer_from_int32_noalloc(0);   // malformed layout: refuse

    object_t** field = (object_t**)obj + (hi - (nslots - 1) + slot);

    // Write-once: NULL -> value, never value -> value. That is what makes a
    // plain CAS sufficient (no ABA) and lets a reader treat a non-NULL slot as
    // a fully constructed node. RELEASE pairs with the reader's acquire so the
    // node's contents are visible to anyone who sees the pointer.
    object_t* expected = NULL;
    bool ok = __atomic_compare_exchange_n(field, &expected, value, false,
                                          __ATOMIC_RELEASE, __ATOMIC_RELAXED);
    return integer_from_int32_noalloc(ok ? 1 : 0);
}
