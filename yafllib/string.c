
#include "yafl.h"
#include <string.h>


// Strict UTF-8 decoder, defined below — forward-declared so the codepoint-set
// scanners (string_find_any / string_skip_any) can use it ahead of its
// definition.
static int _utf8_decode(const unsigned char* p, int32_t len, int32_t off, int32_t* out_cp);


VTABLE_DECLARE_STRUCT(string_vtable, 16);
EXPORT struct string_vtable STRING_VTABLE = {
    .object_size = offsetof(string_t, array[0]),
    .array_el_size = sizeof(uint8_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = offsetof(string_t, length),
    .name = "string",
    .implements_array = VTABLE_IMPLEMENTS(0),
};


struct string_empty {
    vtable_t* vtable;
    uint32_t length;
    uint8_t array[1];
};


HIDDEN string_t* _string_allocate(int32_t length) {
    string_t* string = (string_t*)array_create((vtable_t*)&STRING_VTABLE, length+1);
    string->array[length] = 0; // Zero terminate all strings as a convenience for OS calls
    return string;
}


HIDDEN object_t* _string_create_from_bytes(uint8_t* data, int32_t length) {
    if (length < (int32_t)sizeof(uintptr_t)) {
        uintptr_t string = 0;
        memcpy(&string, data, length);
        uintptr_t test = 1;
        if (1 == *(uint8_t*)&test)
             string = (string << 8) | (length * (PTR_TAG_MASK+1) + PTR_TAG_STRING);
        else string |= (length * (PTR_TAG_MASK+1) + PTR_TAG_STRING);
        return (object_t*)string;
    } else {
        assert(length <= INT32_MAX);
        string_t* string = _string_allocate(length);
        memcpy(string->array, data, length);
        return (object_t*)string;
    }
}


HIDDEN object_t* _string_create_from_cstr(char* data) {
    return _string_create_from_bytes((uint8_t*)data, strlen(data));
}


HIDDEN object_t* _string_append2(char* cstr1, int32_t len1, char* cstr2, int32_t len2) {
    int64_t length = (int64_t)len1 + len2;
    string_t* string;
    uint8_t* ptr;

    if (length < sizeof(uintptr_t)) {
        uintptr_t test = 1;
        string = (string_t*)(uintptr_t)(length * (PTR_TAG_MASK+1) + PTR_TAG_STRING);
        ptr = (uint8_t*)&string + (1==*(uint8_t*)&test ? 1 : 0);
    } else {
        string = _string_allocate(length);
        ptr = string->array;
    }

    memcpy(ptr, cstr1, len1);
    memcpy(ptr+len1, cstr2, len2);
    return (object_t*)string;
}


EXPORT object_t* string_allocate(int32_t length) {
    return (object_t*)_string_allocate(length);
}


EXPORT object_t* string_from_bytes(uint8_t* data, int32_t length) {
    return _string_create_from_bytes(data, length);
}


EXPORT int32_t string_copy_cstr(object_t* self, char* buf, int32_t buf_size) {
    intptr_t local; int32_t len;
    char* src = string_to_cstr(self, &local, &len);
    int32_t copy = len < buf_size - 1 ? len : buf_size - 1;
    memcpy(buf, src, copy);
    buf[copy] = 0;
    return len;
}


EXPORT object_t* string_truncate(object_t* self, int32_t new_length) {
    string_t* s = (string_t*)self;
    if (new_length < (int32_t)sizeof(uintptr_t))
        return _string_create_from_bytes(s->array, new_length);
    s->array[new_length] = 0;
    s->length = new_length + 1;
    return self;
}


EXPORT object_t* string_append(object_t* self, object_t* data) {
    intptr_t buf1; int32_t len1;
    char* cstr1 = string_to_cstr(self, &buf1, &len1);
    if (len1 == 0)
        return data;

    intptr_t buf2; int32_t len2;
    char* cstr2 = string_to_cstr(data, &buf2, &len2);
    if (len2 == 0)
        return self;

    return _string_append2(cstr1, len1, cstr2, len2);
}


EXPORT object_t* string_slice_int32(object_t* self, int32_t start, int32_t end) {
    if (start <= 0 && end >= string_length(self))
        return self;

    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);

    if (start < 0)
        start = 0;
    else if (start > len)
        start = len;

    if (end < 0)
        end = 0;
    else if (end > len)
        end = len;

    if (end <= start)
        end = start;

    return _string_create_from_bytes((uint8_t*)(cstr + start), end - start);
}


EXPORT object_t* string_slice(object_t* self, object_t* start_int, object_t* end_int) {
    int32_t start_int32 = int32_from_integer(start_int);
    int32_t end_int32 = int32_from_integer(end_int);
    return string_slice_int32(self, start_int32, end_int32);
}


EXPORT int string_compare(object_t* self, object_t* data) {
    intptr_t buf_a, buf_b; int32_t len_a, len_b;
    char* cstr_a = string_to_cstr(self, &buf_a, &len_a);
    char* cstr_b = string_to_cstr(data, &buf_b, &len_b);

    int result = memcmp(cstr_a, cstr_b, len_a < len_b ? len_a : len_b);

    if (result != 0)
        return result;
    if (len_a < len_b)
        return -1;
    if (len_a > len_b)
        return 1;
    return 0;
}


// Return the index of the first byte equal to `byte_value` at or after `from`,
// or -1 if not found.  Linear scan in C — used by the JSON parser to find the
// next delimiter in a buffered chunk without recursing through YAFL once per
// byte (which blows the C stack on long string bodies).
EXPORT object_t* string_find_byte(object_t* self, int32_t needle, object_t* o_from) {
    if (needle < 0 || needle > 255) return integer_from_int32(-1);
    int overflow = 0;
    int32_t from = int32_from_integer_with_overflow(o_from, &overflow);
    if (overflow) return integer_from_int32(-1);
    if (from < 0) from = 0;

    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);
    if (from >= len) return integer_from_int32(-1);

    void* hit = memchr(cstr + from, needle, (size_t)(len - from));
    if (hit == NULL) return integer_from_int32(-1);
    return integer_from_int32((int32_t)((char*)hit - cstr));
}


// Codepoint membership set built from `accept`. ASCII members (cp < 0x80,
// one byte) go in an O(1) bitset; the presence of any non-ASCII member is
// flagged so the (rare) non-ASCII input path knows whether to bother
// re-scanning. `accept` is itself UTF-8, so it is decoded codepoint by
// codepoint — `accept` is a set of CHARACTERS, not bytes.
typedef struct {
    unsigned char ascii[128];   // ascii[cp] == 1 iff codepoint cp (<0x80) ∈ accept
    int has_non_ascii;          // does accept contain any codepoint ≥ 0x80?
    const char* accept;         // accept bytes, for the non-ASCII linear probe
    int32_t accept_len;
} codepoint_set;

static void _build_codepoint_set(const char* accept, int32_t accept_len,
                                 codepoint_set* set) {
    for (int i = 0; i < 128; ++i) set->ascii[i] = 0;
    set->has_non_ascii = 0;
    set->accept = accept;
    set->accept_len = accept_len;
    int32_t cp;
    for (int32_t i = 0; i < accept_len; ) {
        int w = _utf8_decode((const unsigned char*)accept, accept_len, i, &cp);
        if (w == 0) { ++i; continue; }            // skip a malformed accept byte
        if (cp < 0x80) set->ascii[cp] = 1; else set->has_non_ascii = 1;
        i += w;
    }
}

// O(1) for ASCII input; for a non-ASCII codepoint, linear-probe accept's
// codepoints only when accept actually has non-ASCII members.
static int _codepoint_in_set(int32_t cp, const codepoint_set* set) {
    if (cp < 0x80) return set->ascii[cp];
    if (!set->has_non_ascii) return 0;
    int32_t acp;
    for (int32_t i = 0; i < set->accept_len; ) {
        int w = _utf8_decode((const unsigned char*)set->accept, set->accept_len, i, &acp);
        if (w == 0) { ++i; continue; }
        if (acp == cp) return 1;
        i += w;
    }
    return 0;
}


// Return the byte offset of the first CODEPOINT at or after `from` whose value
// is a member of `accept`, or length(self) if no such codepoint exists (in
// particular when `from >= length`). Returning length-not-found rather than
// -1 is more convenient for parsers — the result is always a safe slice upper
// bound, and (like `from`) it is always a codepoint boundary.
EXPORT object_t* string_find_any(object_t* self, object_t* o_accept, object_t* o_from) {
    intptr_t s_buf; int32_t s_len;
    char* s = string_to_cstr(self, &s_buf, &s_len);

    int overflow = 0;
    int32_t from = int32_from_integer_with_overflow(o_from, &overflow);
    if (overflow) return integer_from_int32(s_len);
    if (from < 0) from = 0;
    if (from >= s_len) return integer_from_int32(s_len);

    intptr_t a_buf; int32_t a_len;
    char* accept = string_to_cstr(o_accept, &a_buf, &a_len);

    codepoint_set set;
    _build_codepoint_set(accept, a_len, &set);

    int32_t cp;
    for (int32_t i = from; i < s_len; ) {
        int w = _utf8_decode((const unsigned char*)s, s_len, i, &cp);
        if (w == 0) { ++i; continue; }            // malformed: not a member, skip
        if (_codepoint_in_set(cp, &set)) return integer_from_int32(i);
        i += w;
    }
    return integer_from_int32(s_len);
}


// Return the byte offset of the first CODEPOINT at or after `from` that is NOT
// in `accept`, or length(self) if every remaining codepoint is in `accept`.
// Counterpart of string_find_any; used to skip a fixed run of characters
// (whitespace, digit-set, etc.) in one C call rather than per-codepoint YAFL
// recursion. A malformed byte is treated as a non-member, so the scan stops
// there (and always on a codepoint boundary).
EXPORT object_t* string_skip_any(object_t* self, object_t* o_accept, object_t* o_from) {
    intptr_t s_buf; int32_t s_len;
    char* s = string_to_cstr(self, &s_buf, &s_len);

    int overflow = 0;
    int32_t from = int32_from_integer_with_overflow(o_from, &overflow);
    if (overflow) return integer_from_int32(s_len);
    if (from < 0) from = 0;
    if (from >= s_len) return integer_from_int32(s_len);

    intptr_t a_buf; int32_t a_len;
    char* accept = string_to_cstr(o_accept, &a_buf, &a_len);

    codepoint_set set;
    _build_codepoint_set(accept, a_len, &set);

    int32_t cp;
    for (int32_t i = from; i < s_len; ) {
        int w = _utf8_decode((const unsigned char*)s, s_len, i, &cp);
        if (w == 0) return integer_from_int32(i);  // malformed: not in accept, stop
        if (!_codepoint_in_set(cp, &set)) return integer_from_int32(i);
        i += w;
    }
    return integer_from_int32(s_len);
}


// Decimal Int parser. Optional leading '-' or '+', then 1+ digits.
// Returns NULL on parse failure (becomes None in YAFL Int|None).
EXPORT object_t* string_parse_int(object_t* self) {
    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);

    int32_t i = 0;
    int neg = 0;
    if (i < len && (cstr[i] == '-' || cstr[i] == '+')) {
        neg = cstr[i] == '-';
        i++;
    }
    if (i >= len) return NULL;

    object_t* acc = integer_from_int32(0);
    object_t* ten = integer_from_int32(10);
    while (i < len) {
        unsigned char c = (unsigned char)cstr[i++];
        if (c < '0' || c > '9') return NULL;
        acc = integer_mul(acc, ten);
        acc = integer_add_full(acc, integer_from_int32(c - '0'));
    }
    if (neg) acc = integer_sub_full(integer_from_int32(0), acc);
    return acc;
}


EXPORT object_t* print_string(object_t* self, object_t* data) {
    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(data, &buf, &len);
    int32_t result = (int32_t)fwrite(cstr, 1, len, stdout);
    return integer_from_int32(result);
}


EXPORT object_t* wchar_to_string(int32_t codepoint) {
    uint8_t utf8[4];
    if (codepoint >= 0) {
        if (codepoint <= 0x7F) {
            utf8[0] = (uint8_t)codepoint;
            return _string_create_from_bytes(utf8, 1);
        } else if (codepoint <= 0x7FF) {
            utf8[0] = 0xC0 | (uint8_t)(codepoint >> 6);
            utf8[1] = 0x80 | (uint8_t)(codepoint & 0x3F);
            return _string_create_from_bytes(utf8, 2);
        } else if (codepoint <= 0xFFFF) {
            utf8[0] = 0xE0 | (uint8_t)(codepoint >> 12);
            utf8[1] = 0x80 | (uint8_t)((codepoint >> 6) & 0x3F);
            utf8[2] = 0x80 | (uint8_t)(codepoint & 0x3F);
            return _string_create_from_bytes(utf8, 3);
        } else if (codepoint <= 0x10FFFF) {
            utf8[0] = 0xF0 | (uint8_t)(codepoint >> 18);
            utf8[1] = 0x80 | (uint8_t)((codepoint >> 12) & 0x3F);
            utf8[2] = 0x80 | (uint8_t)((codepoint >> 6) & 0x3F);
            utf8[3] = 0x80 | (uint8_t)(codepoint & 0x3F);
            return _string_create_from_bytes(utf8, 4);
        }
    }
    __abort_on_overflow();
    __builtin_unreachable();
}


// Strict UTF-8 decode of the codepoint beginning at byte offset `off`.
// On success writes the scalar to *out_cp and returns its byte width (1..4).
// Returns 0 when there is no valid, minimally-encoded scalar at `off`: the
// offset is out of range, lands on a continuation byte (i.e. inside a
// sequence), the lead byte is invalid, a continuation byte is missing or
// ill-formed, or the result is overlong, a surrogate (U+D800..U+DFFF), or
// greater than U+10FFFF. Because only minimal encodings are accepted, the
// returned width always equals _utf8Width(*out_cp) — the YAFL `decode`
// relies on this to advance to the next boundary without a second C call.
static int _utf8_decode(const unsigned char* p, int32_t len, int32_t off, int32_t* out_cp) {
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


// Strict decode of the codepoint at byte offset `from`; the value behind YAFL
// `codepointAt`. Returns the Unicode scalar as a plain int32 (every scalar
// fits in Int32 — there is no `char` type in YAFL), or -1 when there is no
// valid scalar there: out of range, mid-sequence, or malformed (see
// _utf8_decode). -1 is an unambiguous "none" sentinel because scalars are
// non-negative; YAFL lifts it to Int32|None. The single source of truth for
// the codepoint layer; `decode`, `codepoints` and friends build on it.
EXPORT int32_t string_codepoint_at(object_t* self, object_t* o_from) {
    int overflow = 0;
    int32_t from = int32_from_integer_with_overflow(o_from, &overflow);
    if (overflow) return -1;

    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);

    int32_t cp;
    if (_utf8_decode((const unsigned char*)cstr, len, from, &cp) == 0)
        return -1;
    return cp;
}


// Codepoint count: the number of bytes that are not UTF-8 continuation
// bytes (10xxxxxx). For valid UTF-8 this is exactly the character count;
// one O(n) pass with no per-codepoint decode. Counterpart to string_length
// (which counts bytes).
EXPORT object_t* string_codepoint_count(object_t* self) {
    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);

    int32_t count = 0;
    for (int32_t i = 0; i < len; ++i)
        if (((unsigned char)cstr[i] & 0xC0) != 0x80) count++;
    return integer_from_int32(count);
}


// True iff every byte of `self` belongs to a valid, minimally-encoded UTF-8
// sequence. Lets IO code validate raw bytes before decoding (and tell
// end-of-string apart from malformed input, which `codepointAt` collapses
// to None).
EXPORT bool string_valid_utf8(object_t* self) {
    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);

    const unsigned char* p = (const unsigned char*)cstr;
    int32_t cp;
    for (int32_t i = 0; i < len; ) {
        int w = _utf8_decode(p, len, i, &cp);
        if (w == 0) return false;
        i += w;
    }
    return true;
}


EXPORT object_t* string_resize(object_t* self, object_t* new_size) {
    int  overflow = 0;
    int32_t  size = int32_from_integer_with_overflow(new_size, &overflow);
    if (size < 0 || overflow) __abort_on_overflow();

    int32_t str_length;
    intptr_t local_buffer;
    char* cstr = string_to_cstr(self, &local_buffer, &str_length);

    // The string_t length-field convention is `string_length + 1` (the +1
    // is the implicit NUL terminator that all heap strings carry).
    string_t* new_str = (string_t*)array_create((vtable_t*)&STRING_VTABLE, size + 1);
    int32_t to_copy = str_length < size ? str_length : size;
    memcpy(new_str->array, cstr, to_copy);
    new_str->array[size] = 0;
    return (object_t*)new_str;
}






