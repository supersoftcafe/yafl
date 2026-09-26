// 32-byte fat string: { head, head_len, tail_len, tail[19] }.
//
//   content = head[0 .. head_len) ++ tail[0 .. tail_len)
//
// Canonical by length: head == NULL exactly when length <= 19 (a head only
// appears when the tail overflows), and unused tail bytes are always zero, so
// two short strings are equal iff their 32 bytes are.
#ifndef FATSTR_H
#define FATSTR_H

#include "fatbuf.h"

#define FAT_TAIL 19
#define FAT_NAME "fat32"

typedef struct {
    object_t* head;        // NULL, or a fat_buf_vt buffer
    uint32_t  head_len;
    uint8_t   tail_len;
    uint8_t   tail[FAT_TAIL];
} fstr_t;
_Static_assert(sizeof(fstr_t) == 32, "fat32 layout");

static inline fstr_t fstr_empty(void) { fstr_t s; memset(&s, 0, sizeof s); return s; }
static inline object_t* fstr_heap(fstr_t s) { return s.head; }
static inline uint32_t fstr_head_len(fstr_t s) { return s.head_len; }
static inline uint32_t fstr_length(fstr_t s) { return s.head_len + s.tail_len; }

static inline fstr_t fstr_append_bytes(fstr_t s, const uint8_t* p, uint32_t n) {
    if ((uint32_t)s.tail_len + n <= FAT_TAIL) {
        memcpy(s.tail + s.tail_len, p, n);
        s.tail_len += n;
        return s;
    }
    uint64_t total = (uint64_t)s.head_len + s.tail_len + n;
    if (total > INT32_MAX) __abort_on_overflow();
    fstr_t out = fstr_empty();
    out.head = buf_append(s.head, s.head_len, s.tail, s.tail_len, p, n);
    out.head_len = (uint32_t)total;
    return out;
}

static inline fstr_t fstr_append(fstr_t a, fstr_t b) {
    if (fstr_length(a) == 0) return b;
    if (b.head_len) a = fstr_append_bytes(a, BUF_BYTES(b.head), b.head_len);
    if (b.tail_len) a = fstr_append_bytes(a, b.tail, b.tail_len);
    return a;
}

// In-place forms: *s is updated, nothing is returned by value.
static inline void fstr_append_bytes_into(fstr_t* s, const uint8_t* p, uint32_t n) {
    if ((uint32_t)s->tail_len + n <= FAT_TAIL) {
        memcpy(s->tail + s->tail_len, p, n);
        s->tail_len += n;
        return;
    }
    *s = fstr_append_bytes(*s, p, n);
}
static inline void fstr_append_into(fstr_t* a, const fstr_t* b) {
    if (fstr_length(*a) == 0) { *a = *b; return; }
    if (b->head_len) fstr_append_bytes_into(a, BUF_BYTES(b->head), b->head_len);
    if (b->tail_len) fstr_append_bytes_into(a, b->tail, b->tail_len);
}

static inline int32_t fstr_byte_at(fstr_t s, uint32_t i) {
    if (i < s.head_len) return BUF_BYTES(s.head)[i];
    i -= s.head_len;
    return i < s.tail_len ? s.tail[i] : -1;
}

static inline uint32_t fstr_hash(fstr_t s) {
    uint32_t h = 2166136261u;
    if (s.head_len) h = fnv_bytes(h, BUF_BYTES(s.head), s.head_len);
    return fnv_bytes(h, s.tail, s.tail_len);
}

static inline bool fstr_eq(fstr_t a, fstr_t b) {
    if (a.head == NULL || b.head == NULL)          // short: canonical bytes
        return memcmp(&a, &b, sizeof a) == 0;
    if (fstr_length(a) != fstr_length(b)) return false;
    for (uint32_t i = 0; i < fstr_length(a); i++)  // long: rare in the tests
        if (fstr_byte_at(a, i) != fstr_byte_at(b, i)) return false;
    return true;
}

#endif
