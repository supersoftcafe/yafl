// String internals (str.c): the strict UTF-8 decoder and the codepoint set.
#ifndef STR_INTERNAL_H
#define STR_INTERNAL_H

#include "yafl.h"

// Strict decode of the codepoint at p[off]; returns its width (1..4) or 0.
// Inline: the scanners call it per character.
static inline int _utf8_decode(const unsigned char* p, int32_t len, int32_t off, int32_t* out_cp) {
    if (off < 0 || off >= len) return 0;
    unsigned char b0 = p[off];
    if (b0 < 0x80) { *out_cp = b0; return 1; }
    if (b0 < 0xC0) return 0;                              // continuation byte as lead
    if (b0 < 0xE0) {                                      // 2-byte: 110xxxxx
        if (off + 1 >= len) return 0;
        unsigned char b1 = p[off + 1];
        if ((b1 & 0xC0) != 0x80) return 0;
        int32_t cp = ((b0 & 0x1F) << 6) | (b1 & 0x3F);
        if (cp < 0x80) return 0;                          // overlong
        *out_cp = cp; return 2;
    }
    if (b0 < 0xF0) {                                      // 3-byte: 1110xxxx
        if (off + 2 >= len) return 0;
        unsigned char b1 = p[off + 1], b2 = p[off + 2];
        if ((b1 & 0xC0) != 0x80 || (b2 & 0xC0) != 0x80) return 0;
        int32_t cp = ((b0 & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F);
        if (cp < 0x800) return 0;                         // overlong
        if (cp >= 0xD800 && cp <= 0xDFFF) return 0;       // UTF-16 surrogate
        *out_cp = cp; return 3;
    }
    if (b0 < 0xF8) {                                      // 4-byte: 11110xxx
        if (off + 3 >= len) return 0;
        unsigned char b1 = p[off + 1], b2 = p[off + 2], b3 = p[off + 3];
        if ((b1 & 0xC0) != 0x80 || (b2 & 0xC0) != 0x80 || (b3 & 0xC0) != 0x80) return 0;
        int32_t cp = ((b0 & 0x07) << 18) | ((b1 & 0x3F) << 12)
                   | ((b2 & 0x3F) << 6) | (b3 & 0x3F);
        if (cp < 0x10000) return 0;                       // overlong
        if (cp > 0x10FFFF) return 0;                      // beyond Unicode range
        *out_cp = cp; return 4;
    }
    return 0;                                             // 0xF8..0xFF: invalid lead
}

// Decoding for everything that WALKS a string: a byte that does not start a
// valid, minimally-encoded sequence is U+FFFD, one byte wide — so a walk
// always makes progress and covers every byte, and a binary blob read as a
// String counts, iterates and scans consistently. 0 only past the end. Only
// validity checks use the strict decoder above.
#define UTF8_REPLACEMENT 0xFFFD
static inline int _utf8_decode_lossy(const unsigned char* p, int32_t len, int32_t off, int32_t* out_cp) {
    if (off < 0 || off >= len) return 0;
    int w = _utf8_decode(p, len, off, out_cp);
    if (w == 0) { *out_cp = UTF8_REPLACEMENT; return 1; }
    return w;
}

// Codepoint membership set built from `accept` (itself UTF-8, decoded the
// same lossy way: a malformed accept byte means U+FFFD). ASCII members
// go in an O(1) bitmap — 16 bytes, so building a set per scan stays cheap;
// non-ASCII members are probed linearly.
typedef struct {
    uint64_t ascii[2];          // bit cp set iff codepoint cp (<0x80) is in accept
    int has_non_ascii;          // does accept contain any codepoint >= 0x80?
    const char* accept;         // accept bytes, for the non-ASCII linear probe
    int32_t accept_len;
} codepoint_set;

HIDDEN void _build_codepoint_set(const char* accept, int32_t accept_len, codepoint_set* set);

// Is ASCII codepoint `c` (< 0x80) a member? Inline: tested per byte.
static inline int _ascii_in_set(int c, const codepoint_set* set) {
    return (int)((set->ascii[c >> 6] >> (c & 63)) & 1);
}

// Inline: tested per character by the scanners.
static inline int _codepoint_in_set(int32_t cp, const codepoint_set* set) {
    if (cp < 0x80) return _ascii_in_set(cp, set);
    if (!set->has_non_ascii) return 0;
    int32_t acp;
    for (int32_t i = 0; i < set->accept_len; ) {
        i += _utf8_decode_lossy((const unsigned char*)set->accept, set->accept_len, i, &acp);
        if (acp == cp) return 1;
    }
    return 0;
}

#endif
