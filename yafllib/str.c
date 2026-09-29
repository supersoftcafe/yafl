// String values (str_t) — the 16-byte String representation. Layout and the
// canonical-by-length rule are documented at str_t in yafl.h.
//
// Every byte access goes through a SEGMENTS view: the inline bytes, or the
// head buffer's [0, head_len) followed by the tail bytes. Operations are
// written once against that view, so neither mode needs a flattening copy —
// in particular the offset scanners (byteAt, findByte, indexOf, findAny,
// skipAny, codepointAt) stay O(1)/O(scan) when a heap string has tail bytes.
//
// Growth: a value extends its head IN PLACE only when it holds the head's pin
// and owns the end of it (head_len == used) with room to spare. Otherwise it
// copies — exactly sized for a fresh copy, 2x only when an owner has run out
// of room (the accumulation case). Strings built once carry no slack.

#include "yafl.h"
#include "str_internal.h"
#include <string.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

VTABLE_DECLARE_STRUCT(str_head_vtable, 16);

// Read-only heads (static literals): `length` = byte length + 1, never
// extended. Also the pseudo-vtable an inline String's tagged word 0 answers
// to (object_is_instance), so it is THE String type test.
EXPORT struct str_head_vtable STR_HEAD_VTABLE = {
    .object_size = offsetof(str_head_t, array[0]),
    .array_el_size = sizeof(uint8_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = offsetof(str_head_t, length),
    .name = "string",
    .implements_array = VTABLE_IMPLEMENTS(0),
};

// Growable head buffers: `length` = used + 1, `capacity` = capacity + 1, and
// array_cap_offset makes compaction reset capacity to length on the copy (a
// moved buffer never extends in place). Implements STR_HEAD_VTABLE, so a head
// in word 0 dispatches as a String.
EXPORT struct str_head_vtable STR_BUF_VTABLE = {
    .object_size = offsetof(str_head_t, array[0]),
    .array_el_size = sizeof(uint8_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = offsetof(str_head_t, length),
    .array_cap_offset = offsetof(str_head_t, capacity),
    .name = "string_buffer",
    .implements_array = VTABLE_IMPLEMENTS(1, (vtable_t*)&STR_HEAD_VTABLE),
};


// ── Views ─────────────────────────────────────────────────────────────────

// The bytes of a value: a[0, na) ++ b[0, nb). Points INTO the str_t it was
// taken from (inline bytes, tail bytes), so that value must outlive it.
typedef struct { const uint8_t* a; int32_t na; const uint8_t* b; int32_t nb; } segs_t;

static inline uint32_t head_len_of(str_t s) { return s.meta & STR_META_LEN_MASK; }
static inline uint32_t tail_len_of(str_t s) { return s.meta >> STR_META_LEN_BITS; }
// A head's bytes. Through offsetof, not `->array`: str_head_t declares a
// nominal array[16], and the compiler would bound-check indexes against it.
static inline uint8_t* head_bytes(object_t* h) { return (uint8_t*)h + offsetof(str_head_t, array); }

static inline segs_t segs_of(str_t* s) {
    if (str_is_inline(*s))
        return (segs_t){ str_inline_bytes(s), str_length(*s), NULL, 0 };
    return (segs_t){ head_bytes(s->head), (int32_t)head_len_of(*s),
                     str_tail_bytes(s), (int32_t)tail_len_of(*s) };
}
static inline int32_t segs_len(segs_t g) { return g.na + g.nb; }
static inline int seg_at(segs_t g, int32_t i) { return i < g.na ? g.a[i] : g.b[i - g.na]; }

// The contiguous run starting at byte i (i < segs_len), and its length.
static inline int32_t seg_run(segs_t g, int32_t i, const uint8_t** p) {
    if (i < g.na) { *p = g.a + i; return g.na - i; }
    *p = g.b + (i - g.na);
    return g.nb - (i - g.na);
}

static void segs_copy(segs_t g, int32_t from, int32_t n, uint8_t* dst) {
    while (n > 0) {
        const uint8_t* p;
        int32_t r = seg_run(g, from, &p);
        if (r > n) r = n;
        memcpy(dst, p, (size_t)r);
        dst += r; from += r; n -= r;
    }
}

// Strict UTF-8 decode at byte i, across the segment boundary if need be:
// 0 when the bytes there are not a valid sequence (or i is out of range).
static int decode_at(segs_t g, int32_t i, int32_t* cp) {
    int32_t len = segs_len(g);
    if (i < 0 || i >= len) return 0;
    if (i + 4 <= g.na) return _utf8_decode(g.a, g.na, i, cp);
    uint8_t w[4];
    int32_t n = len - i < 4 ? len - i : 4;
    for (int32_t k = 0; k < n; k++) w[k] = (uint8_t)seg_at(g, i + k);
    return _utf8_decode(w, n, 0, cp);
}

// The lossy decode (str_internal.h) at byte i: U+FFFD one byte wide where
// decode_at finds no valid sequence; 0 only when i is out of range.
static int decode_lossy_at(segs_t g, int32_t i, int32_t* cp) {
    if (i < 0 || i >= segs_len(g)) return 0;
    int w = decode_at(g, i, cp);
    if (w == 0) { *cp = UTF8_REPLACEMENT; return 1; }
    return w;
}

static int32_t int32_arg(object_t* o, int* overflow) {
    return int32_from_integer_with_overflow(o, overflow);
}


// ── Construction ──────────────────────────────────────────────────────────

typedef struct { const uint8_t* p; int32_t n; } piece_t;

static str_t inline_value(int32_t len) {
    str_t s;
    memset(&s, 0, sizeof s);
    s.head = (object_t*)(uintptr_t)(len * (PTR_TAG_MASK + 1) + PTR_TAG_STRING);
    return s;
}

static str_t heap_value(object_t* head, uint32_t head_len) {
    str_t s;
    memset(&s, 0, sizeof s);
    s.head = head;
    s.meta = head_len;
    return s;
}

// A head buffer holding `used` bytes, capacity perfect-filled to the
// allocator granule: exact for a fresh copy, 2x for an owner's growth.
static object_t* buf_alloc(int64_t used, bool grow) {
    if (used > (int64_t)STR_META_LEN_MASK) { __abort_on_overflow(); __builtin_unreachable(); }
    int64_t overhead = (int64_t)offsetof(str_head_t, array) + 1;
    int64_t total = (grow ? used * 2 : used) + overhead;   // 2x: 1.5x and a lower large-object factor measured no better
    total = (total + GC_ALLOC_GRANULE - 1) / GC_ALLOC_GRANULE * GC_ALLOC_GRANULE;
    int64_t cap = total - overhead;
    if (cap > (int64_t)STR_META_LEN_MASK) cap = STR_META_LEN_MASK;
    str_head_t* b = (str_head_t*)array_create((vtable_t*)&STR_BUF_VTABLE, (int32_t)cap + 1);
    b->capacity = (uint32_t)cap + 1;      // array_cap_offset
    atomic_store_explicit(&b->hash, 0, memory_order_relaxed);
    b->length = (uint32_t)used + 1;       // used: the GC's view of the object
    head_bytes((object_t*)b)[used] = 0;
    return (object_t*)b;
}

// A new value holding the concatenation of `pieces` (total bytes).
static str_t from_pieces(const piece_t* pieces, int np, int64_t total, bool grow) {
    if (total <= STR_INLINE_MAX) {
        str_t s = inline_value((int32_t)total);
        uint8_t* d = str_inline_bytes(&s);
        for (int i = 0; i < np; i++) { memcpy(d, pieces[i].p, (size_t)pieces[i].n); d += pieces[i].n; }
        return s;
    }
    object_t* b = buf_alloc(total, grow);
    uint8_t* d = head_bytes(b);
    for (int i = 0; i < np; i++) { memcpy(d, pieces[i].p, (size_t)pieces[i].n); d += pieces[i].n; }
    return heap_value(b, (uint32_t)total);
}

static bool in_heap(object_t* o) {
    return (size_t)((char*)o - _memory_heap_base) < _memory_heap_bytes;
}

// `a` followed by `pieces` (extra bytes in all). The one growth path.
static str_t extend(str_t a, const piece_t* pieces, int np, int64_t extra) {
    if (extra == 0) return a;
    int64_t la = str_length(a);
    int64_t total = la + extra;
    if (total > (int64_t)STR_META_LEN_MASK) { __abort_on_overflow(); __builtin_unreachable(); }

    if (str_is_inline(a) && total <= STR_INLINE_MAX) {   // stays inline: no pieces array
        str_t r = a;
        uint8_t* d = str_inline_bytes(&r);
        uint32_t at = (uint32_t)la;
        for (int i = 0; i < np; i++)
            for (int32_t k = 0; k < pieces[i].n && at < STR_INLINE_MAX; k++)
                d[at++] = pieces[i].p[k];
        *(uint8_t*)&r = (uint8_t)(total * (PTR_TAG_MASK + 1) + PTR_TAG_STRING);
        return r;
    }
    if (str_is_inline(a)) {
        piece_t all[40];
        all[0] = (piece_t){ str_inline_bytes(&a), (int32_t)la };
        for (int i = 0; i < np; i++) all[i + 1] = pieces[i];
        return from_pieces(all, np + 1, total, false);   // fresh: exact
    }

    uint32_t hl = head_len_of(a), tl = tail_len_of(a);
    // The tail only pays when the head can later grow in place: on a
    // read-only head (a static literal) it would just postpone the
    // copy — and a tailed value can never use the hash cache. So appends to a
    // read-only head copy straight into a fresh, exact, tail-less buffer.
    object_t* h = a.head;
    bool growable = in_heap(h) && object_get_vtable(h) == (vtable_t*)&STR_BUF_VTABLE;
    if (growable && tl + extra <= STR_TAIL_MAX) {
        uint8_t* d = str_tail_bytes(&a) + tl;
        for (int i = 0; i < np; i++) { memcpy(d, pieces[i].p, (size_t)pieces[i].n); d += pieces[i].n; }
        a.meta = hl | (uint32_t)((tl + extra) << STR_META_LEN_BITS);
        return a;
    }

    // Flush the tail and the pieces into the head. Pin FIRST, then read
    // used/capacity: the pin is the mutex both for competing appenders and
    // for the compactor (which re-reads the size under it).
    bool grow = false;
    if (growable && object_try_pin(h)) {
        str_head_t* b = (str_head_t*)h;
        if (vtable_untag(b->vtable) == (vtable_t*)&STR_BUF_VTABLE && b->length - 1 == hl) {
            if ((b->capacity - 1) - hl >= tl + extra) {
                uint8_t* d = head_bytes(h) + hl;
                memcpy(d, str_tail_bytes(&a), tl); d += tl;
                for (int i = 0; i < np; i++) { memcpy(d, pieces[i].p, (size_t)pieces[i].n); d += pieces[i].n; }
                head_bytes(h)[total] = 0;
                b->length = (uint32_t)total + 1;   // plain store: we hold the pin
                object_unpin(h);                    // release: bytes + length visible
                return heap_value(h, (uint32_t)total);
            }
            grow = true;                            // the owner is out of room
        }
        object_unpin(h);
    }
    // Copy. A forwarded `h` is a stale but byte-identical copy of [0, hl).
    piece_t all[42];
    all[0] = (piece_t){ head_bytes(h), (int32_t)hl };
    all[1] = (piece_t){ str_tail_bytes(&a), (int32_t)tl };
    for (int i = 0; i < np; i++) all[i + 2] = pieces[i];
    return from_pieces(all, np + 2, total, grow);
}

static int pieces_of(str_t* s, piece_t* out) {
    segs_t g = segs_of(s);
    int n = 0;
    if (g.na) out[n++] = (piece_t){ g.a, g.na };
    if (g.nb) out[n++] = (piece_t){ g.b, g.nb };
    return n;
}

EXPORT str_t str_from_bytes(const uint8_t* data, int32_t length) {
    if (length <= 0) return inline_value(0);   // `data` may be NULL here
    piece_t p = { data, length };
    return from_pieces(&p, 1, length, false);
}

EXPORT str_t str_append_slow(str_t a, str_t b) {
    int32_t lb = str_length(b);
    if (lb == 0) return a;
    if (str_length(a) == 0) return b;
    piece_t p[2];
    int np = pieces_of(&b, p);
    return extend(a, p, np, lb);
}

// `a + b + c + …` in one step: the first operand extends (in place when it
// owns its head — so `acc = acc + x + y` in a loop stays amortised O(1)), the
// rest are its pieces. Operand count is capped at 16 by the compiler.
EXPORT str_t str_concat_n(int32_t count, ...) {
    str_t ops[16];
    va_list ap;
    va_start(ap, count);
    for (int32_t i = 0; i < count; i++) ops[i] = va_arg(ap, str_t);
    va_end(ap);
    int32_t first = 0;
    while (first < count - 1 && str_length(ops[first]) == 0) first++;
    piece_t pieces[32];
    int np = 0;
    int64_t extra = 0;
    for (int32_t i = first + 1; i < count; i++) {
        np += pieces_of(&ops[i], pieces + np);
        extra += str_length(ops[i]);
    }
    return extend(ops[first], pieces, np, extra);
}


// ── The C boundary ────────────────────────────────────────────────────────

EXPORT str_t str_from_cstr(const char* cstr) {
    return str_from_bytes((const uint8_t*)cstr, (int32_t)strlen(cstr));
}

EXPORT void str_copy_range(str_t s, int32_t from, int32_t n, uint8_t* dst) {
    segs_copy(segs_of(&s), from, n, dst);
}

EXPORT void str_copy_bytes(str_t s, uint8_t* dst) {
    str_copy_range(s, 0, str_length(s), dst);
}

EXPORT char* str_cstr(str_t s, char* buf, int32_t size, char** heap) {
    int32_t len = str_length(s);
    *heap = NULL;
    char* out = len < size ? buf : (*heap = malloc((size_t)len + 1));
    str_copy_bytes(s, (uint8_t*)out);
    out[len] = 0;
    return out;
}

EXPORT int32_t str_copy_cstr(str_t s, char* buf, int32_t size) {
    if (size <= 0) return 0;
    segs_t g = segs_of(&s);
    int32_t n = segs_len(g);
    if (n > size - 1) n = size - 1;
    segs_copy(g, 0, n, (uint8_t*)buf);
    buf[n] = 0;
    return n;
}

EXPORT object_t* print_string(object_t* self, str_t s) {
    (void)self;   // ABI receiver, unused here
    segs_t g = segs_of(&s);
    int32_t n = (int32_t)fwrite(g.a, 1, (size_t)g.na, stdout);
    if (g.nb) n += (int32_t)fwrite(g.b, 1, (size_t)g.nb, stdout);
    return integer_from_int32(n);
}


// ── Comparison and hashing ────────────────────────────────────────────────

EXPORT int str_compare(str_t a, str_t b) {
    segs_t ga = segs_of(&a), gb = segs_of(&b);
    int32_t la = segs_len(ga), lb = segs_len(gb);
    int32_t n = la < lb ? la : lb;
    for (int32_t i = 0; i < n; ) {
        const uint8_t *pa, *pb;
        int32_t ra = seg_run(ga, i, &pa), rb = seg_run(gb, i, &pb);
        int32_t k = ra < rb ? ra : rb;
        if (k > n - i) k = n - i;
        int r = memcmp(pa, pb, (size_t)k);
        if (r != 0) return r;
        i += k;
    }
    return la < lb ? -1 : la > lb ? 1 : 0;
}

// Hashing (yafl.h has the fast paths: inline strings, and a heap value whose
// head caches the final hash of exactly its length). This is the rest: the
// byte stream 8 bytes per multiply, across the head/tail join (a partial word
// carries over), so the result depends only on the bytes, never on the split.
// A tail-less value then caches (length << 32) | hash in its head.
//
// No synchronisation: the length and the hash are ONE aligned 64-bit word,
// stored and loaded with single relaxed atomics, so no reader sees a length
// from one writer paired with a hash from another; and a hash is a pure
// function of immutable bytes, so nothing else needs publishing. The one
// assumption outside this file: the compactor's object copy (a memcpy) moves
// an aligned 8-byte field whole — true of the word-or-wider copies memcpy
// makes on our targets. A copy loop that split it could tear the word.
EXPORT int32_t str_hash_heap(str_t s) {
    str_head_t* cached = NULL;
    uint32_t covered = 0;
    if (tail_len_of(s) == 0) {
        cached = (str_head_t*)s.head;
        covered = head_len_of(s);
    }
    segs_t g = segs_of(&s);
    uint64_t h = STR_HASH_SEED ^ (uint64_t)segs_len(g);
    uint64_t acc = 0;
    int k = 0;                                  // bytes pending in acc
    const uint8_t* ps[2] = { g.a, g.b };
    int32_t ns[2] = { g.na, g.nb };
    for (int seg = 0; seg < 2; seg++) {
        const uint8_t* p = ps[seg];
        int32_t n = ns[seg], i = 0;
        if (k) {                                // finish the carried word
            while (k < 8 && i < n) acc |= (uint64_t)p[i++] << (8 * k++);
            if (k < 8) continue;
            h = str_hash_mix(h, acc); acc = 0; k = 0;
        }
        for (; i + 8 <= n; i += 8) h = str_hash_mix(h, str_load_le64(p + i));
        while (i < n) acc |= (uint64_t)p[i++] << (8 * k++);
    }
    if (k) h = str_hash_mix(h, acc);
    int32_t result = str_hash_finish(h);
    if (cached)
        atomic_store_explicit(&cached->hash, ((uint64_t)covered << 32) | (uint32_t)result,
                              memory_order_relaxed);
    return result;
}


// ── Slicing and byte access ───────────────────────────────────────────────

EXPORT str_t str_slice(str_t s, object_t* o_start, object_t* o_end) {
    int32_t start = int32_from_integer(o_start), end = int32_from_integer(o_end);
    segs_t g = segs_of(&s);
    int32_t len = segs_len(g);
    if (start < 0) start = 0; else if (start > len) start = len;
    if (end < 0) end = 0; else if (end > len) end = len;
    if (end <= start) return inline_value(0);
    if (start == 0 && end == len) return s;
    piece_t p[2];
    int np = 0;
    for (int32_t i = start; i < end; ) {
        const uint8_t* q;
        int32_t r = seg_run(g, i, &q);
        if (r > end - i) r = end - i;
        p[np++] = (piece_t){ q, r };
        i += r;
    }
    return from_pieces(p, np, end - start, false);
}


EXPORT object_t* str_find_byte(str_t s, int32_t byte, object_t* o_from) {
    if (byte < 0 || byte > 255) return integer_from_int32(-1);
    int overflow = 0;
    int32_t from = int32_arg(o_from, &overflow);
    if (overflow) return integer_from_int32(-1);
    if (from < 0) from = 0;
    segs_t g = segs_of(&s);
    int32_t len = segs_len(g);
    while (from < len) {
        const uint8_t* p;
        int32_t r = seg_run(g, from, &p);
        const uint8_t* hit = memchr(p, byte, (size_t)r);
        if (hit) return integer_from_int32(from + (int32_t)(hit - p));
        from += r;
    }
    return integer_from_int32(-1);
}

EXPORT object_t* str_index_of(str_t s, str_t needle, object_t* o_from) {
    int overflow = 0;
    int32_t from = int32_arg(o_from, &overflow);
    if (overflow) return integer_from_int32(-1);
    if (from < 0) from = 0;
    segs_t g = segs_of(&s), gn = segs_of(&needle);
    int32_t sl = segs_len(g), nl = segs_len(gn);
    if (nl == 0) return integer_from_int32(from <= sl ? from : sl);
    if (from > sl || sl - from < nl) return integer_from_int32(-1);

    // The needle, contiguous (it is almost always inline or tail-less).
    uint8_t local[64];
    uint8_t* nbuf = nl <= (int32_t)sizeof local ? local : malloc((size_t)nl);
    segs_copy(gn, 0, nl, nbuf);

    int32_t found = -1;
    // Matches wholly inside the first segment: memchr for the first byte.
    int32_t last_a = g.na - nl;
    for (int32_t i = from; i <= last_a; ) {
        const uint8_t* hit = memchr(g.a + i, nbuf[0], (size_t)(last_a - i + 1));
        if (hit == NULL) break;
        i = (int32_t)(hit - g.a);
        if (memcmp(g.a + i, nbuf, (size_t)nl) == 0) { found = i; break; }
        ++i;
    }
    // Matches reaching into the tail (at most nl + tail candidates).
    if (found < 0) {
        int32_t lo = from > last_a + 1 ? from : last_a + 1;
        if (lo < 0) lo = 0;
        for (int32_t i = lo; i <= sl - nl && found < 0; i++) {
            int32_t k = 0;
            while (k < nl && seg_at(g, i + k) == nbuf[k]) k++;
            if (k == nl) found = i;
        }
    }
    if (nbuf != local) free(nbuf);
    return integer_from_int32(found);
}


// ── Codepoints ────────────────────────────────────────────────────────────

// ASCII members go in the bitmap; the presence of any non-ASCII member is
// flagged so the (rare) non-ASCII input path knows whether to probe. `accept`
// is itself UTF-8: a set of CHARACTERS, not bytes.
HIDDEN void _build_codepoint_set(const char* accept, int32_t accept_len,
                                 codepoint_set* set) {
    set->ascii[0] = set->ascii[1] = 0;
    set->has_non_ascii = 0;
    set->accept = accept;
    set->accept_len = accept_len;
    int32_t cp;
    for (int32_t i = 0; i < accept_len; ) {
        i += _utf8_decode_lossy((const unsigned char*)accept, accept_len, i, &cp);
        if (cp < 0x80) set->ascii[cp >> 6] |= (uint64_t)1 << (cp & 63);
        else set->has_non_ascii = 1;
    }
}

// The set over `accept`'s bytes, read in place when they are one run (an
// inline value, or a head with no tail) — the set keeps pointing at them for
// its non-ASCII probe, and `*accept` outlives the scan. Only a tailed value is
// gathered, into `scratch` or a heap copy left in `*owned` for the caller.
static void build_set(str_t* accept, codepoint_set* set, uint8_t* scratch, int32_t cap, uint8_t** owned) {
    segs_t ga = segs_of(accept);
    int32_t al = segs_len(ga);
    const uint8_t* bytes = ga.a;
    if (ga.nb != 0) {
        uint8_t* buf = al <= cap ? scratch : (*owned = malloc((size_t)al));
        segs_copy(ga, 0, al, buf);
        bytes = buf;
    }
    _build_codepoint_set((const char*)bytes, al, set);
}

static object_t* scan_any(str_t s, str_t accept, object_t* o_from, bool want_member) {
    segs_t g = segs_of(&s);
    int32_t len = segs_len(g);
    int overflow = 0;
    int32_t from = int32_arg(o_from, &overflow);
    if (overflow) return integer_from_int32(len);
    if (from < 0) from = 0;
    if (from >= len) return integer_from_int32(len);

    uint8_t scratch[64], *owned = NULL;
    codepoint_set set;
    build_set(&accept, &set, scratch, sizeof scratch, &owned);

    int32_t result = len, cp;
    int want = want_member ? 1 : 0;
    for (int32_t i = from; i < len; ) {
        int c = i < g.na ? g.a[i] : g.b[i - g.na];
        if (c < 0x80) {                            // ASCII: its own codepoint
            if (_ascii_in_set(c, &set) == want) { result = i; break; }
            ++i; continue;
        }
        int w = decode_lossy_at(g, i, &cp);         // a malformed byte is U+FFFD
        if (_codepoint_in_set(cp, &set) == want) { result = i; break; }
        i += w;
    }
    if (owned) free(owned);
    return integer_from_int32(result);
}

EXPORT object_t* str_find_any(str_t s, str_t accept, object_t* from) { return scan_any(s, accept, from, true); }
EXPORT object_t* str_skip_any(str_t s, str_t accept, object_t* from) { return scan_any(s, accept, from, false); }

// The codepoint at byte offset `from` (U+FFFD for a malformed byte), or -1
// past the end.
EXPORT int32_t str_codepoint_at(str_t s, object_t* o_from) {
    int overflow = 0;
    int32_t from = int32_arg(o_from, &overflow);
    if (overflow) return -1;
    int32_t cp;
    return decode_lossy_at(segs_of(&s), from, &cp) ? cp : -1;
}

// The bytes the codepoint at `from` occupies: 1..4, 1 for a malformed byte
// (read as U+FFFD), 0 past the end. The width cannot be derived from the
// codepoint: a real U+FFFD is 3 bytes, a substituted one 1.
EXPORT int32_t str_codepoint_width(str_t s, object_t* o_from) {
    int overflow = 0;
    int32_t from = int32_arg(o_from, &overflow);
    if (overflow) return 0;
    int32_t cp;
    return decode_lossy_at(segs_of(&s), from, &cp);
}

// The number of steps a walk takes: the codepoints, malformed bytes counting
// one U+FFFD each.
EXPORT object_t* str_codepoint_count(str_t s) {
    segs_t g = segs_of(&s);
    int32_t count = 0, cp;
    for (int32_t i = 0, w; (w = decode_lossy_at(g, i, &cp)) > 0; i += w) count++;
    return integer_from_int32(count);
}

EXPORT bool str_valid_utf8(str_t s) {
    segs_t g = segs_of(&s);
    int32_t len = segs_len(g), cp;
    for (int32_t i = 0; i < len; ) {
        int w = decode_at(g, i, &cp);
        if (w == 0) return false;
        i += w;
    }
    return true;
}

EXPORT str_t str_ascii(int32_t byte) {
    str_t s = inline_value(1);
    str_inline_bytes(&s)[0] = (uint8_t)byte;
    return s;
}

EXPORT str_t str_wchar(int32_t codepoint) {
    uint8_t u[4];
    int32_t n;
    if (codepoint < 0) { __abort_on_overflow(); __builtin_unreachable(); }
    if (codepoint <= 0x7F) { u[0] = (uint8_t)codepoint; n = 1; }
    else if (codepoint <= 0x7FF) {
        u[0] = 0xC0 | (uint8_t)(codepoint >> 6);  u[1] = 0x80 | (uint8_t)(codepoint & 0x3F); n = 2;
    } else if (codepoint <= 0xFFFF) {
        u[0] = 0xE0 | (uint8_t)(codepoint >> 12); u[1] = 0x80 | (uint8_t)((codepoint >> 6) & 0x3F);
        u[2] = 0x80 | (uint8_t)(codepoint & 0x3F); n = 3;
    } else if (codepoint <= 0x10FFFF) {
        u[0] = 0xF0 | (uint8_t)(codepoint >> 18); u[1] = 0x80 | (uint8_t)((codepoint >> 12) & 0x3F);
        u[2] = 0x80 | (uint8_t)((codepoint >> 6) & 0x3F); u[3] = 0x80 | (uint8_t)(codepoint & 0x3F); n = 4;
    } else { __abort_on_overflow(); __builtin_unreachable(); }
    return str_from_bytes(u, n);
}


// ── Parsing and formatting ────────────────────────────────────────────────

EXPORT object_t* str_parse_int(str_t s) {
    segs_t g = segs_of(&s);
    int32_t len = segs_len(g);
    int32_t i = 0;
    int neg = 0;
    if (i < len && (seg_at(g, i) == '-' || seg_at(g, i) == '+')) { neg = seg_at(g, i) == '-'; i++; }
    if (i >= len) return NULL;
    object_t* acc = integer_from_int32(0);
    object_t* ten = integer_from_int32(10);
    while (i < len) {
        int c = seg_at(g, i++);
        if (c < '0' || c > '9') return NULL;
        acc = integer_mul(acc, ten);
        acc = integer_add_full(acc, integer_from_int32(c - '0'));
    }
    if (neg) acc = integer_sub_full(integer_from_int32(0), acc);
    return acc;
}

// ── Numbers ───────────────────────────────────────────────────────────────

// snprintf into a stack buffer; every format here fits in 32 bytes.
static str_t formatted(const char* fmt, ...) {
    char buf[32];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (n < 0) n = 0;
    if (n > (int)sizeof buf - 1) n = (int)sizeof buf - 1;
    return str_from_bytes((const uint8_t*)buf, n);
}

EXPORT str_t str_from_int8(int8_t v)     { return formatted("%d", (int)v); }
EXPORT str_t str_from_int16(int16_t v)   { return formatted("%d", (int)v); }
EXPORT str_t str_from_int32(int32_t v)   { return formatted("%d", (int)v); }
EXPORT str_t str_from_int64(int64_t v)   { return formatted("%lld", (long long)v); }
// Round-trip-safe forms: %.9g for binary32, %.17g for binary64.
EXPORT str_t str_from_float32(float v)   { return formatted("%.9g", (double)v); }
EXPORT str_t str_from_float64(double v)  { return formatted("%.17g", v); }

// NaN on any failure (empty, leftover characters) — callers wrap the result
// into Float|None by testing for NaN.
EXPORT double str_parse_float64(str_t s) {
    int32_t len = str_length(s);
    if (len <= 0) return NAN;
    char buf[64], *heap;
    char* src = str_cstr(s, buf, (int32_t)sizeof buf, &heap);
    char* end = NULL;
    double v = strtod(src, &end);
    bool whole = end == src + len;
    free(heap);
    return whole ? v : NAN;
}

EXPORT float str_parse_float32(str_t s) {
    int32_t len = str_length(s);
    if (len <= 0) return NAN;
    char buf[64], *heap;
    char* src = str_cstr(s, buf, (int32_t)sizeof buf, &heap);
    char* end = NULL;
    float v = strtof(src, &end);
    bool whole = end == src + len;
    free(heap);
    return whole ? v : NAN;
}
