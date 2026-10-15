// GC debug tooling — diagnostics only, nothing here runs unless the
// corresponding env toggle is set.
#include "gc_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <pthread.h>

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
    extern size_t memory_run_floor(void);
    extern size_t memory_total_pages(void);
    // Allocations live in two bands: singles in [0, watermark), runs in
    // [run_floor, total). Hop the virgin middle.
    size_t wm = memory_watermark();
    size_t floor_ = memory_run_floor();
    size_t total_ = memory_total_pages();
    for (size_t pi = 0; pi < total_; pi++) {
        if (pi == wm && floor_ > wm) pi = floor_;
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
        for (int k = 0; k < 8; k++) {
            if ((object_t*)t->saved_callee_regs[k] == target) {
                fprintf(stderr, "[HUNT]     PIN callee-reg thread=%p slot=%d\n", (void*)t, k);
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
    vt = vtable_untag(vt);   // pinned objects carry the pin bit here
    GC_FOR_EACH_PTR_WINDOW(vt, object, m, slots)
        while (m) {
            unsigned i = (unsigned)__builtin_ctzll(m); m &= m-1;
            object_t* child = slots[i];
            uintptr_t a = (uintptr_t)child;
            if (!a || (a & (GC_SLOT_SIZE-1)) || (a & PTR_TAG_MASK)) continue;
            gc_page_t* cpg = (gc_page_t*)(a & ~(uintptr_t)(GC_PAGE_SIZE-1));
            if (!memory_pages_is_alloc_head(cpg) || cpg->head.tag != PAGE_MAGIC_NUMBER) continue;
            if (*(uint64_t*)child != 0x4242424242424242ULL) continue;
            gc_trace_report_begin();
            fprintf(stderr, "\nDANGLE cycle=%llu: live %p (vt=%s) field#%u -> reclaimed %p\n",
                    (unsigned long long)atomic_load(&gc_cycle_count),
                    (void*)object, vt->name, _w * 64 + i, (void*)child);
            gc_trace_explain("live", object);
            if (vtable_is_forward(object->vtable))
                gc_trace_explain("live's copy", object_resolve(object));
            gc_trace_explain("reclaimed", child);
            fflush(stderr);
            abort();
        }
}

// --- Page history (YAFL_GC_TRACE, diagnostics only) --------------------------
//
// A short ring of collector events per heap page — allocated, nursery-swept,
// promoted, pruned, evacuated, freed — each with the slots it concerned, so a
// test that finds a corrupt object can ask what the collector last did to it
// (gc_trace_explain). Rings are written racily by any thread; good enough to
// read after the fact. Off: one predictable branch per recorded event.
bool gc_trace_enabled = false;

enum { GC_TRACE_DEPTH = 32 };
struct gc_trace_event {
    uint64_t seq;
    uint32_t cycle;
    uint32_t aux;        // the page's local_epoch (alloc: its page count)
    uint16_t tid;
    uint8_t  kind;
    bitmap_t slots;      // the slots the event concerned (kind-specific)
};
struct gc_trace_page {
    _Atomic(uint32_t) n;
    struct gc_trace_event ev[GC_TRACE_DEPTH];
};
static struct gc_trace_page *gc_trace_pages;
static size_t                gc_trace_npages;
static _Atomic(uint64_t)     gc_trace_seq;
static _Atomic(uint16_t)     gc_trace_next_tid;
static thread_local uint16_t gc_trace_tid;

static int gc_trace_bit(const bitmap_t *b, size_t bit) {
    return (int)((b->a[bit / GC_MASK_SIZE] >> (bit % GC_MASK_SIZE)) & 1);
}

static const char *const gc_trace_names[] = {
    [GCT_ALLOC] = "alloc", [GCT_LOCAL_TAKE] = "nursery-take",
    [GCT_LOCAL_SWEEP] = "nursery-sweep", [GCT_LOCAL_PROMOTE] = "nursery-promote",
    [GCT_LOCAL_RELEASE] = "nursery-release", [GCT_PRUNE] = "prune",
    [GCT_EVACUATE] = "evacuate", [GCT_FREE] = "free",
};

// One failure report at a time: whoever reports first holds this until it
// aborts, so a second detector (the collector's DANGLE check racing a
// mutator's own) cannot cut the first report short with its abort.
static pthread_mutex_t gc_trace_report_mu = PTHREAD_MUTEX_INITIALIZER;
EXPORT void gc_trace_report_begin(void) {
    pthread_mutex_lock(&gc_trace_report_mu);   // never released: abort follows
}

// Called at env parse, before the heap exists: the rings are reserved on the
// first event, once the heap's size is known.
void gc_trace_init(void) {
    const char *e = getenv("YAFL_GC_TRACE");
    gc_trace_enabled = e && e[0] && e[0] != '0';
}
static pthread_once_t gc_trace_once = PTHREAD_ONCE_INIT;
static void gc_trace_reserve(void) {
    size_t n = _memory_heap_bytes / GC_PAGE_SIZE;
    // Virtual reservation: only the rings of pages actually used are touched.
    void *p = mmap(NULL, n * sizeof *gc_trace_pages, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (p == MAP_FAILED) { perror("YAFL_GC_TRACE"); gc_trace_enabled = false; return; }
    gc_trace_npages = n;
    gc_trace_pages = p;
}

void gc_trace_page_event(void *page_addr, enum gc_trace_kind kind, const bitmap_t *slots,
                         uint32_t aux) {
    pthread_once(&gc_trace_once, gc_trace_reserve);
    size_t pi = (size_t)((char*)page_addr - _memory_heap_base) / GC_PAGE_SIZE;
    if (!gc_trace_pages || pi >= gc_trace_npages) return;
    if (!gc_trace_tid) gc_trace_tid = (uint16_t)(atomic_fetch_add(&gc_trace_next_tid, 1) + 1);
    struct gc_trace_page *tp = &gc_trace_pages[pi];
    uint32_t k = atomic_fetch_add_explicit(&tp->n, 1, memory_order_relaxed) % GC_TRACE_DEPTH;
    struct gc_trace_event *ev = &tp->ev[k];
    ev->seq   = atomic_fetch_add_explicit(&gc_trace_seq, 1, memory_order_relaxed) + 1;
    ev->cycle = (uint32_t)atomic_load_explicit(&gc_cycle_count, memory_order_relaxed);
    ev->aux   = aux;
    ev->tid   = gc_trace_tid;
    ev->kind  = (uint8_t)kind;
    if (slots) ev->slots = *slots; else memset(&ev->slots, 0, sizeof ev->slots);
}

void gc_trace_page_dropped(gc_page_t *page, enum gc_trace_kind kind, const bitmap_t *kept) {
    bitmap_t dropped;
    for (unsigned i = 0; i < sizeof(bitmap_t) / sizeof(mask_bits_t); ++i)
        dropped.a[i] = page->head.objects.a[i] & ~kept->a[i];
    gc_trace_page_event(page, kind, &dropped, page->head.local_epoch);
}

// What the collector last did to the object at `p`: its page's header now,
// then the page's history, oldest first, marking the events that named its
// slot. Prints nothing useful without YAFL_GC_TRACE beyond the header.
EXPORT void gc_trace_explain(const char *label, const void *p) {
    uintptr_t a = (uintptr_t)p;
    if (!p || (size_t)((char*)p - _memory_heap_base) >= _memory_heap_bytes) {
        fprintf(stderr, "  [trace] %s %p: not in the heap\n", label, p);
        return;
    }
    gc_page_t *page = (gc_page_t*)(a & ~(uintptr_t)(GC_PAGE_SIZE - 1));
    long slot = (long)(((char*)p - (char*)page->slots) / GC_SLOT_SIZE);
    bool in_slots = (char*)p >= (char*)page->slots && slot < SLOTS_PER_PAGE;
    fprintf(stderr, "  [trace] %s %p: page %p slot %ld cycle-now %llu thread-tid %u\n",
            label, p, (void*)page, slot,
            (unsigned long long)atomic_load(&gc_cycle_count), (unsigned)gc_trace_tid);
    fprintf(stderr, "          head: tag=%s pages=%u mutable=%d compacted=%d(cycle %u) old=%d "
            "dirty_old=%d local_epoch=%u pinned=%d object-bit=%d escaped-bit=%d word0=%p\n",
            page->head.tag == PAGE_MAGIC_NUMBER ? "ok" : "BAD", page->head.pages,
            page->head.mutable, page->head.compacted, page->head.compacted_cycle,
            page->head.old, page->head.dirty_old, page->head.local_epoch,
            page->head.scanner.pinned,
            in_slots ? (int)gc_trace_bit(&page->head.objects, (size_t)slot) : -1,
            in_slots ? (int)gc_trace_bit(&page->head.local_escaped, (size_t)slot) : -1,
            *(void**)p);
    if (!gc_trace_pages) return;
    size_t pi = (size_t)((char*)page - _memory_heap_base) / GC_PAGE_SIZE;
    struct gc_trace_page *tp = &gc_trace_pages[pi];
    uint32_t n = atomic_load(&tp->n);
    uint32_t first = n > GC_TRACE_DEPTH ? n - GC_TRACE_DEPTH : 0;
    if (first) fprintf(stderr, "          (%u older events dropped)\n", first);
    for (uint32_t i = first; i < n; ++i) {
        struct gc_trace_event *ev = &tp->ev[i % GC_TRACE_DEPTH];
        unsigned kind = ev->kind;
        int hit = in_slots ? (int)gc_trace_bit(&ev->slots, (size_t)slot) : 0;
        fprintf(stderr, "          #%-10llu cycle %-5u tid %-3u %-16s aux %-6u%s\n",
                (unsigned long long)ev->seq, ev->cycle, ev->tid,
                kind < sizeof gc_trace_names / sizeof *gc_trace_names && gc_trace_names[kind]
                    ? gc_trace_names[kind] : "?",
                ev->aux, hit ? "  <-- this slot" : "");
    }
}

// Out of memory: say what the collector was doing, so a genuinely full heap
// (live data at the limit) can be told from a collector that stopped freeing.
void gc_oom_report(FILE *out) {
    fprintf(out, "[GC OOM] heap pages used %zu of %zu; cycle %llu, stage %s; "
            "old pages %zu, dirty-old %zu; this thread's nursery epoch %u\n",
            memory_count(), memory_total_pages(),
            (unsigned long long)atomic_load(&gc_cycle_count),
            gc_stage_name(atomic_load(&stage)),
            atomic_load(&gc_old_page_count), atomic_load(&gc_dirty_old_count),
            gc_thread_info.local_epoch);
    fflush(out);
}
