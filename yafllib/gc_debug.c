// GC debug tooling — diagnostics only, nothing here runs unless the
// corresponding env toggle is set.
#include "gc_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// --- Heap hunt (YAFL_GC_HUNT, diagnostics only) ------------------------------
//
// Post-mortem retention analysis, printed at exit alongside the stats when
// YAFL_GC_HUNT is set (requires YAFL_GC_STATS). Three stages:
//   1. CENSUS: every live object bucketed by vtable name with counts — the
//      first question is always "what IS all this?".
//   2. HEADS: for the bucket named by the env value (substring match; "1" =
//      biggest bucket), find members no same-type member points to — the
//      entry points of chains/lists, however long.
//   3. HOLDERS: one full-heap scan reporting each head's first heap referrer,
//      plus a conservative stack/register sweep. Caveat: the sweep also sees
//      the hunter's own frame — ignore pins within a few hundred bytes of
//      the reported hunter SP.
// Found on its first outing: completed tasks retaining dead capture graphs
// (fixed by deferred resumption) and per-construction unit-enum boxes (fixed
// by static promotion). Zero cost when the env var is unset.
static vtable_t* _hunt_vt(object_t* o) {
    vtable_t* vt = o->vtable;
    while (vt && vtable_is_forward(vt)) vt = ((object_t*)vt)->vtable;
    return vt;
}
static void _hunt_each_live(void (*fn)(object_t*, void*), void* arg) {
    extern char* _memory_heap_base;
    size_t wm = memory_watermark();
    for (size_t pi = 0; pi < wm; pi++) {
        gc_page_t* page = (gc_page_t*)(_memory_heap_base + pi * GC_PAGE_SIZE);
        if (!memory_pages_is_alloc_head(page) || page->head.tag != PAGE_MAGIC_NUMBER) continue;
        for (unsigned index = 0; index < sizeof(bitmap_t)/sizeof(mask_bits_t); ++index) {
            mask_bits_t starts = page->head.objects.a[index];
            unsigned offset = index * GC_MASK_SIZE;
            while (starts) {
                unsigned slot = __builtin_ctzll(starts) + offset;
                starts &= starts - 1;
                fn((object_t*)&page->slots[slot], arg);
            }
        }
        if (page->head.pages > 1) pi += page->head.pages - 1;
    }
}
struct _hunt_ref { object_t* target; object_t* referrer; const char* via; int count; };
static void _hunt_scan_fields(object_t* o, void* arg) {
    struct _hunt_ref* r = (struct _hunt_ref*)arg;
    vtable_t* vt = _hunt_vt(o);
    if (!vt || vtable_is_forward(o->vtable)) return;
    GC_FOR_EACH_PTR_WINDOW(vt, o, m, slots)
        while (m) {
            unsigned i = (unsigned)__builtin_ctzll(m);
            m &= m - 1;
            if (slots[i] == r->target) {
                r->count++;
                if (!r->referrer) {
                    r->referrer = o;
                    r->via = vt->name;
                }
            }
        }
    if (vt->array_el_pointer_locations) {
        uint32_t len = *(uint32_t*)&((char*)o)[vt->array_len_offset];
        char* arr = ((char*)o) + vt->object_size;
        for (; len-- > 0; arr += vt->array_el_size) {
            uint64_t am = vt->array_el_pointer_locations;
            while (am) {
                unsigned i = (unsigned)__builtin_ctzll(am);
                am &= am - 1;
                if (((object_t**)arr)[i] == r->target) {
                    r->count++;
                    if (!r->referrer) {
                        r->referrer = o;
                        r->via = vt->name;
                    }
                }
            }
        }
    }
}
static int _hunt_scan_pins(object_t* target) {
    int hits = 0;
    for (struct gc_thread_info* t = threads; t != NULL; t = t->next) {
        for (object_t** p = t->stack_lower_ptr; p && p < t->stack_upper_ptr; p++) {
            if (*p == target) {
                fprintf(stderr, "[HUNT]     PIN stack thread=%p at %p\n", (void*)t, (void*)p);
                hits++;
            }
        }
        object_t** rl = (object_t**)&t->saved_registers[0];
        object_t** rh = (object_t**)&t->saved_registers[1];
        for (object_t** p = rl; p < rh; p++) {
            if (*p == target) {
                fprintf(stderr, "[HUNT]     PIN register thread=%p slot=%ld\n", (void*)t, (long)(p - rl));
                hits++;
            }
        }
    }
    return hits;
}
static object_t** _hunt_members;
static char*      _hunt_pointed;
static size_t     _hunt_nmembers;
static const char* _hunt_member_name;
static int _hunt_cmp_ptr(const void* a, const void* b) {
    uintptr_t x = *(const uintptr_t*)a, y = *(const uintptr_t*)b;
    return x < y ? -1 : x > y ? 1 : 0;
}
static long _hunt_member_idx(object_t* o) {
    size_t lo = 0, hi = _hunt_nmembers;
    while (lo < hi) {
        size_t mid = (lo + hi) / 2;
        if ((uintptr_t)_hunt_members[mid] < (uintptr_t)o) lo = mid + 1;
        else hi = mid;
    }
    return (lo < _hunt_nmembers && _hunt_members[lo] == o) ? (long)lo : -1;
}
static void _hunt_collect_members(object_t* o, void* arg) {
    (void)arg;
    vtable_t* vt = _hunt_vt(o);
    if (vt && vt->name && vt->name == _hunt_member_name)
        _hunt_members[_hunt_nmembers++] = o;
}
static void _hunt_mark_pointed(object_t* o, void* arg) {
    (void)arg;
    vtable_t* vt = _hunt_vt(o);
    if (!vt || vtable_is_forward(o->vtable) || !vt->name || vt->name != _hunt_member_name) return;
    GC_FOR_EACH_PTR_WINDOW(vt, o, m, slots)
        while (m) {
            unsigned i = (unsigned)__builtin_ctzll(m);
            m &= m - 1;
            long idx = _hunt_member_idx(slots[i]);
            if (idx >= 0) _hunt_pointed[idx] = 1;
        }
}
struct _hunt_bkt { const char* name; size_t count; object_t* example; };
static struct _hunt_bkt _hunt_bkts[128];
static int _hunt_nbkts = 0;
static void _hunt_census_one(object_t* o, void* arg) {
    (void)arg;
    vtable_t* vt = _hunt_vt(o);
    const char* nm = (vt && !vtable_is_forward(o->vtable)) ? (vt->name ? vt->name : "?") : "(fwd)";
    int b;
    for (b = 0; b < _hunt_nbkts; b++)
        if (_hunt_bkts[b].name == nm) break;
    if (b == _hunt_nbkts && _hunt_nbkts < 128) {
        _hunt_bkts[_hunt_nbkts].name = nm;
        _hunt_bkts[_hunt_nbkts].count = 0;
        _hunt_bkts[_hunt_nbkts].example = o;
        _hunt_nbkts++;
    }
    if (b < 128) {
        _hunt_bkts[b].count++;
        _hunt_bkts[b].example = o;
    }
}
void gc_hunt_run(void) {
    if (!getenv("YAFL_GC_HUNT")) return;   // see the heap-hunt comment above
    _hunt_each_live(_hunt_census_one, NULL);
    fprintf(stderr, "[HUNT] census:\n");
    for (int b = 0; b < _hunt_nbkts; b++)
        fprintf(stderr, "[HUNT]   %-50s count=%zu example=%p\n", _hunt_bkts[b].name, _hunt_bkts[b].count, (void*)_hunt_bkts[b].example);
    // Find the chosen bucket (YAFL_GC_HUNT substring; "1" = biggest), then
    // locate its HEADS — members no other member points to — and report who
    // holds each head (heap referrer, or stack/register pin).
    const char* want = getenv("YAFL_GC_HUNT");
    struct _hunt_bkt* big = NULL;
    for (int b = 0; b < _hunt_nbkts; b++) {
        if (want && want[0] != '1' && (!_hunt_bkts[b].name || !strstr(_hunt_bkts[b].name, want))) continue;
        if (!big || _hunt_bkts[b].count > big->count) big = &_hunt_bkts[b];
    }
    if (!big) return;
    fprintf(stderr, "[HUNT] chasing bucket %s (count=%zu)\n", big->name, big->count);
    _hunt_members = malloc(big->count * sizeof(object_t*));
    _hunt_pointed = calloc(big->count, 1);
    _hunt_nmembers = 0;
    _hunt_member_name = big->name;
    _hunt_each_live(_hunt_collect_members, NULL);
    qsort(_hunt_members, _hunt_nmembers, sizeof(object_t*), _hunt_cmp_ptr);
    _hunt_each_live(_hunt_mark_pointed, NULL);
    size_t nheads = 0;
    object_t* heads[8];
    for (size_t i = 0; i < _hunt_nmembers; i++) {
        if (!_hunt_pointed[i]) {
            if (nheads < 8) heads[nheads] = _hunt_members[i];
            nheads++;
        }
    }
    fprintf(stderr, "[HUNT] members=%zu heads=%zu\n", _hunt_nmembers, nheads);
    {
        volatile char sp_marker = 0;
        fprintf(stderr, "[HUNT] hunter SP ~= %p\n", (void*)&sp_marker);
    }
    for (size_t h = 0; h < nheads && h < 8; h++) {
        struct _hunt_ref r = { heads[h], NULL, NULL, 0 };
        _hunt_each_live(_hunt_scan_fields, &r);
        vtable_t* rvt = r.referrer ? _hunt_vt(r.referrer) : NULL;
        fprintf(stderr, "[HUNT] head[%zu] %p: heap refs=%d holder=%p (%s) pins=%d\n",
                h, (void*)heads[h], r.count, (void*)r.referrer,
                rvt && rvt->name ? rvt->name : "-", _hunt_scan_pins(heads[h]));
    }
    free(_hunt_members);
    free(_hunt_pointed);
}


// Debug (YAFL_GC_POISON): catch a use-after-free cleanly — a live object being
// scanned whose GC pointer field references a reclaimed (poisoned) object.
// Aborts with the offending edge instead of faulting deep in the scanner.
void gc_dbg_dangle_check(object_t* object) {
    // Follow forwarding to the real vtable; the field walk below still reads
    // the payload at `object` itself (a forwarder's old payload mirrors the
    // copy's layout until fixup rewrites it).
    vtable_t* vt = object->vtable;
    while (UNLIKELY(vtable_is_forward(vt)))
        vt = ((object_t*)vt)->vtable;
    GC_FOR_EACH_PTR_WINDOW(vt, object, m, slots)
        while (m) {
            unsigned i = (unsigned)__builtin_ctzll(m); m &= m-1;
            object_t* child = slots[i];
            uintptr_t a = (uintptr_t)child;
            if (!a || (a & (GC_SLOT_SIZE-1)) || (a & PTR_TAG_MASK)) continue;
            gc_page_t* cpg = (gc_page_t*)(a & ~(uintptr_t)(GC_PAGE_SIZE-1));
            if (!memory_pages_is_alloc_head(cpg) || cpg->head.tag != PAGE_MAGIC_NUMBER) continue;
            if (*(uint64_t*)child != 0x4242424242424242ULL) continue;
            fprintf(stderr, "\nDANGLE cycle=%llu: live %p (vt=%s) field#%u -> reclaimed %p\n",
                    (unsigned long long)atomic_load(&gc_cycle_count),
                    (void*)object, vt->name, _w * 64 + i, (void*)child);
            fflush(stderr);
            abort();
        }
}
