// Helpers shared by the legacy string_t layer (string.c) and the str_t value
// layer (str.c): one strict UTF-8 decoder, one codepoint-set.
#ifndef STR_INTERNAL_H
#define STR_INTERNAL_H

#include "yafl.h"

// Strict decode of the codepoint at p[off]; returns its width (1..4) or 0.
HIDDEN int _utf8_decode(const unsigned char* p, int32_t len, int32_t off, int32_t* out_cp);

// Codepoint membership set built from `accept` (itself UTF-8). ASCII members
// go in an O(1) bitset; non-ASCII members are probed linearly.
typedef struct {
    unsigned char ascii[128];   // ascii[cp] == 1 iff codepoint cp (<0x80) is in accept
    int has_non_ascii;          // does accept contain any codepoint >= 0x80?
    const char* accept;         // accept bytes, for the non-ASCII linear probe
    int32_t accept_len;
} codepoint_set;

HIDDEN void _build_codepoint_set(const char* accept, int32_t accept_len, codepoint_set* set);
HIDDEN int  _codepoint_in_set(int32_t cp, const codepoint_set* set);

#endif
