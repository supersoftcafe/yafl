
#include "yafl.h"
#include <string.h>


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
    int32_t start_int32 = integer_to_int32(start_int);
    int32_t end_int32 = integer_to_int32(end_int);
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
EXPORT object_t* string_find_byte(object_t* self, object_t* o_byte, object_t* o_from) {
    int overflow = 0;
    int32_t needle = integer_to_int32_with_overflow(o_byte, &overflow);
    if (overflow || needle < 0 || needle > 255) return integer_create_from_int32(-1);
    int32_t from = integer_to_int32_with_overflow(o_from, &overflow);
    if (overflow) return integer_create_from_int32(-1);
    if (from < 0) from = 0;

    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(self, &buf, &len);
    if (from >= len) return integer_create_from_int32(-1);

    void* hit = memchr(cstr + from, needle, (size_t)(len - from));
    if (hit == NULL) return integer_create_from_int32(-1);
    return integer_create_from_int32((int32_t)((char*)hit - cstr));
}


// Build a 256-bit byte-set from `accept`: lookup[i] is 1 iff byte i appears
// in accept.  Used by string_find_any / string_skip_any to dispatch on a
// byte class in O(1) per input byte (vs O(|accept|) per byte for strpbrk
// on long needles, and without needing a NUL-terminated needle copy).
static void _build_byteset(const char* needle, int32_t needle_len,
                           unsigned char lookup[256]) {
    for (int i = 0; i < 256; ++i) lookup[i] = 0;
    for (int32_t i = 0; i < needle_len; ++i)
        lookup[(unsigned char)needle[i]] = 1;
}


// Return the index of the first byte at or after `from` that belongs to
// `accept`, or length(self) if no such byte exists (in particular when
// `from >= length`).  Returning length-not-found rather than -1 is more
// convenient for parsers — the result is always a safe slice upper bound.
EXPORT object_t* string_find_any(object_t* self, object_t* o_accept, object_t* o_from) {
    intptr_t s_buf; int32_t s_len;
    char* s = string_to_cstr(self, &s_buf, &s_len);

    int overflow = 0;
    int32_t from = integer_to_int32_with_overflow(o_from, &overflow);
    if (overflow) return integer_create_from_int32(s_len);
    if (from < 0) from = 0;
    if (from >= s_len) return integer_create_from_int32(s_len);

    intptr_t a_buf; int32_t a_len;
    char* accept = string_to_cstr(o_accept, &a_buf, &a_len);

    unsigned char lookup[256];
    _build_byteset(accept, a_len, lookup);

    for (int32_t i = from; i < s_len; ++i) {
        if (lookup[(unsigned char)s[i]]) return integer_create_from_int32(i);
    }
    return integer_create_from_int32(s_len);
}


// Return the index of the first byte at or after `from` that is NOT in
// `accept`, or length(self) if every remaining byte is in `accept`.
// Counterpart of string_find_any; used to skip a fixed run of characters
// (whitespace, digit-set, etc.) in one C call rather than per-byte YAFL
// recursion.
EXPORT object_t* string_skip_any(object_t* self, object_t* o_accept, object_t* o_from) {
    intptr_t s_buf; int32_t s_len;
    char* s = string_to_cstr(self, &s_buf, &s_len);

    int overflow = 0;
    int32_t from = integer_to_int32_with_overflow(o_from, &overflow);
    if (overflow) return integer_create_from_int32(s_len);
    if (from < 0) from = 0;
    if (from >= s_len) return integer_create_from_int32(s_len);

    intptr_t a_buf; int32_t a_len;
    char* accept = string_to_cstr(o_accept, &a_buf, &a_len);

    unsigned char lookup[256];
    _build_byteset(accept, a_len, lookup);

    for (int32_t i = from; i < s_len; ++i) {
        if (!lookup[(unsigned char)s[i]]) return integer_create_from_int32(i);
    }
    return integer_create_from_int32(s_len);
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

    object_t* acc = integer_create_from_int32(0);
    object_t* ten = integer_create_from_int32(10);
    while (i < len) {
        unsigned char c = (unsigned char)cstr[i++];
        if (c < '0' || c > '9') return NULL;
        acc = integer_mul(acc, ten);
        acc = integer_add_full(acc, integer_create_from_int32(c - '0'));
    }
    if (neg) acc = integer_sub_full(integer_create_from_int32(0), acc);
    return acc;
}


EXPORT object_t* print_string(object_t* self, object_t* data) {
    intptr_t buf; int32_t len;
    char* cstr = string_to_cstr(data, &buf, &len);
    int32_t result = (int32_t)fwrite(cstr, 1, len, stdout);
    return integer_create_from_int32(result);
}


EXPORT object_t* wchar_to_string(object_t* integer) {
    uint8_t utf8[4];
    int overflow = 0;
    int32_t codepoint = integer_to_int32_with_overflow(integer, &overflow);
    if (codepoint >= 0 && !overflow) {
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

