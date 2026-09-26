// 16-byte fat string, two modes told apart by word 0:
//
//   INLINE (length <= 15): word 0's low byte is `len << 3 | PTR_TAG_STRING`
//     — the packed-short-string tag, which the GC already treats as a
//     non-pointer — and bytes 1..15 of the value are the content.
//   HEAP (length >= 16): word 0 is a clean fat_buf_vt buffer pointer; word 1
//     is `meta` (head_len in the low 29 bits, tail_len in the top 3) plus a
//     4-byte tail. The tail length cannot live in the pointer's spare low bits:
//     any tag bit there makes the GC read the word as a non-pointer.
//
//   content = inline bytes, or head[0 .. head_len) ++ tail[0 .. tail_len)
//
// Canonical by length (inline exactly when length <= 15; padding always zero),
// so two short strings are equal iff their 16 bytes are.
#ifndef FATSTR_H
#define FATSTR_H

#include "fatbuf.h"

#define FAT_INLINE 15
#define FAT_TAIL 4
#define FAT_NAME "fat16"
#define META_LEN_BITS 29
#define META_LEN_MASK ((1u << META_LEN_BITS) - 1)

typedef struct {
    object_t* head;        // tagged inline word, or a fat_buf_vt buffer
    uint32_t  meta;        // heap mode: head_len | tail_len << 29
    uint8_t   tail[FAT_TAIL];
} fstr_t;
_Static_assert(sizeof(fstr_t) == 16, "fat16 layout");

static inline bool fstr_is_inline(fstr_t s) {
    return ((uintptr_t)s.head & PTR_TAG_MASK) == PTR_TAG_STRING;
}
static inline uint8_t* fstr_inline_bytes(fstr_t* s) { return (uint8_t*)s + 1; }
static inline uint32_t fstr_inline_len(fstr_t s) { return (uint32_t)((uintptr_t)s.head & 0xff) >> 3; }

static inline fstr_t fstr_empty(void) {
    fstr_t s; memset(&s, 0, sizeof s);
    s.head = (object_t*)(uintptr_t)PTR_TAG_STRING;
    return s;
}
static inline object_t* fstr_heap(fstr_t s) { return fstr_is_inline(s) ? NULL : s.head; }
static inline uint32_t fstr_head_len(fstr_t s) { return fstr_is_inline(s) ? 0 : (s.meta & META_LEN_MASK); }
static inline uint32_t fstr_tail_len(fstr_t s) { return s.meta >> META_LEN_BITS; }
static inline uint32_t fstr_length(fstr_t s) {
    return fstr_is_inline(s) ? fstr_inline_len(s) : (s.meta & META_LEN_MASK) + fstr_tail_len(s);
}

static inline fstr_t fstr_append_bytes(fstr_t s, const uint8_t* p, uint32_t n) {
    if (fstr_is_inline(s)) {
        uint32_t len = fstr_inline_len(s);
        if (len + n <= FAT_INLINE) {
            memcpy(fstr_inline_bytes(&s) + len, p, n);
            *(uint8_t*)&s = (uint8_t)(((len + n) << 3) | PTR_TAG_STRING);
            return s;
        }
        fstr_t out; memset(&out, 0, sizeof out);
        out.head = buf_append(NULL, 0, fstr_inline_bytes(&s), len, p, n);
        out.meta = len + n;
        return out;
    }
    uint32_t hl = s.meta & META_LEN_MASK, tl = fstr_tail_len(s);
    if (tl + n <= FAT_TAIL) {
        memcpy(s.tail + tl, p, n);
        s.meta = hl | ((tl + n) << META_LEN_BITS);
        return s;
    }
    uint64_t total = (uint64_t)hl + tl + n;
    if (total > META_LEN_MASK) __abort_on_overflow();
    fstr_t out; memset(&out, 0, sizeof out);
    out.head = buf_append(s.head, hl, s.tail, tl, p, n);
    out.meta = (uint32_t)total;
    return out;
}

static inline fstr_t fstr_append(fstr_t a, fstr_t b) {
    if (fstr_length(a) == 0) return b;
    if (fstr_is_inline(b)) return fstr_append_bytes(a, fstr_inline_bytes(&b), fstr_inline_len(b));
    a = fstr_append_bytes(a, BUF_BYTES(b.head), b.meta & META_LEN_MASK);
    uint32_t tl = fstr_tail_len(b);
    return tl ? fstr_append_bytes(a, b.tail, tl) : a;
}

static inline void fstr_append_bytes_into(fstr_t* s, const uint8_t* p, uint32_t n) {
    *s = fstr_append_bytes(*s, p, n);
}
static inline void fstr_append_into(fstr_t* a, const fstr_t* b) {
    *a = fstr_append(*a, *b);
}

static inline int32_t fstr_byte_at(fstr_t s, uint32_t i) {
    if (fstr_is_inline(s)) return i < fstr_inline_len(s) ? fstr_inline_bytes(&s)[i] : -1;
    uint32_t hl = s.meta & META_LEN_MASK;
    if (i < hl) return BUF_BYTES(s.head)[i];
    i -= hl;
    return i < fstr_tail_len(s) ? s.tail[i] : -1;
}

static inline uint32_t fstr_hash(fstr_t s) {
    uint32_t h = 2166136261u;
    if (fstr_is_inline(s)) return fnv_bytes(h, fstr_inline_bytes(&s), fstr_inline_len(s));
    h = fnv_bytes(h, BUF_BYTES(s.head), s.meta & META_LEN_MASK);
    return fnv_bytes(h, s.tail, fstr_tail_len(s));
}

static inline bool fstr_eq(fstr_t a, fstr_t b) {
    if (fstr_is_inline(a) || fstr_is_inline(b))    // short: canonical bytes
        return memcmp(&a, &b, sizeof a) == 0;
    if (fstr_length(a) != fstr_length(b)) return false;
    for (uint32_t i = 0; i < fstr_length(a); i++)  // long: rare in the tests
        if (fstr_byte_at(a, i) != fstr_byte_at(b, i)) return false;
    return true;
}

#endif
