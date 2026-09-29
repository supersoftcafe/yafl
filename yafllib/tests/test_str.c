#include "test_framework.h"
#include <string.h>
#include <stdlib.h>

/* str_t — the 16-byte String value. The awkward shapes are HEAP values with
 * TAIL bytes: every operation must see head[0, head_len) ++ tail as one
 * string, including needles, codepoints and comparisons that straddle the
 * join. mk_tailed builds one deterministically. */

static str_t S(const char* c) { return str_from_bytes((const uint8_t*)c, (int32_t)strlen(c)); }

/* Byte-for-byte equality with a C string, through the public API only. */
static int same(str_t s, const char* expect) {
    int32_t n = (int32_t)strlen(expect);
    if (str_length(s) != n) return 0;
    for (int32_t i = 0; i < n; i++)
        if (str_byte_at(s, integer_from_int32(i)) != (uint8_t)expect[i]) return 0;
    return 1;
}

static uint32_t head_len(str_t s) { return s.meta & STR_META_LEN_MASK; }
static uint32_t tail_len(str_t s) { return s.meta >> STR_META_LEN_BITS; }

/* 16-byte exact heap head + `tail` (<= STR_TAIL_MAX bytes) in the tail. */
static str_t mk_tailed(const char* head16, const char* tail) {
    str_t h = S(head16);
    return str_append(h, S(tail));
}

/* ---- literals and modes ---- */

TEST(literal_short_inline)
    str_t e = STR16_SHORT(""), a = STR16_SHORT("A"), f = STR16_SHORT("fifteen chars!!");
    ASSERT(str_is_inline(e) && str_length(e) == 0);
    ASSERT(str_is_inline(a) && same(a, "A"));
    ASSERT(str_is_inline(f) && same(f, "fifteen chars!!"));
TEST_END()

TEST(literal_long_heap)
    str_t l = STR16_LONG("sixteen chars!!!");
    ASSERT(!str_is_inline(l) && same(l, "sixteen chars!!!"));
TEST_END()

TEST(canonical_by_length)
    ASSERT(str_is_inline(S("123456789012345")));
    ASSERT(!str_is_inline(S("1234567890123456")));
    ASSERT(str_is_inline(str_append(S("1234567"), S("89012345"))));
    ASSERT(!str_is_inline(str_append(S("12345678"), S("90123456"))));
TEST_END()

TEST(inline_equality_is_bytes)
    ASSERT(str_eq(S("abc"), STR16_SHORT("abc")));
    ASSERT(!str_eq(S("abc"), S("abd")));
    ASSERT(!str_eq(S("abc"), S("abcd")));
TEST_END()

TEST(inline_append_every_length_pair)
    /* Every (la, lb) in 0..15 x 0..15: the inline fast path (la + lb <= 15)
     * and the step past it into the heap. Content, length and mode checked. */
    const char* A = "ABCDEFGHIJKLMNO";
    const char* B = "abcdefghijklmno";
    char expect[32];
    for (int la = 0; la <= 15; la++)
        for (int lb = 0; lb <= 15; lb++) {
            str_t a = str_from_bytes((const uint8_t*)A, la);
            str_t b = str_from_bytes((const uint8_t*)B, lb);
            str_t r = str_append(a, b);
            memcpy(expect, A, la); memcpy(expect + la, B, lb); expect[la + lb] = 0;
            ASSERT(same(r, expect));
            ASSERT(str_is_inline(r) == (la + lb <= 15));
            ASSERT(str_eq(r, str_from_bytes((const uint8_t*)expect, la + lb)));
        }
TEST_END()

/* ---- tails and in-place growth ---- */

TEST(small_append_goes_to_tail)
    str_t t = mk_tailed("0123456789abcdef", "xy");
    ASSERT(head_len(t) == 16 && tail_len(t) == 2);
    ASSERT(same(t, "0123456789abcdefxy"));
TEST_END()

TEST(owner_extends_in_place)
    str_t t = mk_tailed("0123456789abcdef", "xy");
    str_t u = str_append(t, S("PQRS"));          /* tail overflows: flush */
    ASSERT(u.head == t.head);                    /* same buffer, extended */
    ASSERT(tail_len(u) == 0 && same(u, "0123456789abcdefxyPQRS"));
    ASSERT(same(t, "0123456789abcdefxy"));       /* the old value is unchanged */
TEST_END()

TEST(fork_copies_and_leaves_owner_intact)
    str_t base = mk_tailed("0123456789abcdef", "xy");
    str_t v = str_append(base, S("VVVVV"));      /* first extension: in place */
    str_t w = str_append(base, S("WWWWW"));      /* base no longer owns the end */
    ASSERT(v.head == base.head && w.head != base.head);
    ASSERT(same(v, "0123456789abcdefxyVVVVV"));
    ASSERT(same(w, "0123456789abcdefxyWWWWW"));
    ASSERT(same(base, "0123456789abcdefxy"));
TEST_END()

TEST(literal_head_is_read_only)
    str_t s = STR16_LONG("literal string of 26 bytes");
    ASSERT(!str_is_inline(s));
    str_t t = str_append(s, S("0123456789"));    /* past any tail: must copy */
    ASSERT(t.head != s.head);
    ASSERT(same(t, "literal string of 26 bytes0123456789"));
    ASSERT(same(s, "literal string of 26 bytes"));
TEST_END()

TEST(read_only_head_takes_no_tail)
    /* A short append to a read-only head (a long literal) copies into a
     * fresh exact buffer instead of parking bytes in the tail:
     * the tail would only postpone the copy, and a tailed value can never
     * use the hash cache. */
    str_t lit = STR16_LONG("identifier_prefix_");
    str_t k = str_append(lit, S("1234"));
    ASSERT(k.head != lit.head && tail_len(k) == 0);
    ASSERT(same(k, "identifier_prefix_1234"));
TEST_END()

TEST(random_appends_and_forks_match_reference)
    /* Many values over shared buffers, appended in random order; each keeps
     * its own C reference copy. */
    enum { N = 64, STEPS = 20000 };
    str_t v[N]; char* ref[N]; int32_t len[N];
    for (int i = 0; i < N; i++) { v[i] = S(""); ref[i] = calloc(1, 1); len[i] = 0; }
    unsigned seed = 12345;
    static const char* pieces[] = { "a", "bc", "def", "ghij", "klmnopq", "0123456789abcdefghij" };
    for (int step = 0; step < STEPS; step++) {
        seed = seed * 1103515245u + 12345u;
        int i = (seed >> 8) % N, j = (seed >> 16) % N;
        const char* p = pieces[(seed >> 24) % 6];
        int32_t pn = (int32_t)strlen(p);
        /* v[i] = v[j] + p : sometimes an extension, sometimes a fork */
        char* r = malloc((size_t)(len[j] + pn + 1));
        memcpy(r, ref[j], (size_t)len[j]); memcpy(r + len[j], p, (size_t)pn); r[len[j] + pn] = 0;
        v[i] = str_append(v[j], S(p));
        free(ref[i]); ref[i] = r; len[i] = len[j] + pn;
        if (len[i] > 4000) { v[i] = S(""); free(ref[i]); ref[i] = calloc(1, 1); len[i] = 0; }
        GC_SAFE_POINT();
    }
    for (int i = 0; i < N; i++) { ASSERT(same(v[i], ref[i])); free(ref[i]); }
TEST_END()

TEST(concat_n_first_operand_extends)
    str_t acc = mk_tailed("0123456789abcdef", "xy");
    str_t r = str_concat_n(3, acc, S("<"), S(">>"));
    ASSERT(r.head == acc.head || tail_len(r) > 0);
    ASSERT(same(r, "0123456789abcdefxy<>>"));
    ASSERT(same(str_concat_n(3, S(""), S("ab"), S("cd")), "abcd"));
TEST_END()

/* ---- reads across the head/tail join ---- */

TEST(compare_across_modes)
    str_t t = mk_tailed("0123456789abcdef", "xy");
    str_t flat = S("0123456789abcdefxy");
    ASSERT(str_compare(t, flat) == 0 && str_eq(t, flat));
    ASSERT(str_compare(t, S("0123456789abcdefxz")) < 0);
    ASSERT(str_compare(S("0123456789abcdefxz"), t) > 0);
    ASSERT(str_compare(t, S("0123456789abcdef")) > 0);
TEST_END()

TEST(hash_depends_only_on_bytes)
    /* The same bytes in every shape — inline, exact heap, heap + tail at each
     * possible split — hash equally; different bytes (incl. a trailing NUL)
     * almost surely do not. */
    const char* text = "0123456789abcdefghijklmnopqrstuvwxyz";
    int32_t n = (int32_t)strlen(text);
    str_t flat = str_from_bytes((const uint8_t*)text, n);
    for (int32_t split = 16; split <= n; split++) {
        str_t h = str_from_bytes((const uint8_t*)text, split);
        for (int32_t k = split; k < n; ) {           /* append 1..4 bytes at a time */
            int32_t m = n - k < 3 ? n - k : 3;
            h = str_append(h, str_from_bytes((const uint8_t*)text + k, m));
            k += m;
        }
        ASSERT(str_hash(h) == str_hash(flat));
    }
    ASSERT(str_hash(S("hi")) == str_hash(STR16_SHORT("hi")));
    ASSERT(str_hash(S("hi")) != str_hash(S("ih")));
    ASSERT(str_hash(S("a")) != str_hash(str_from_bytes((const uint8_t*)"a\0", 2)));
    ASSERT(str_hash(S("")) != 0);
TEST_END()

TEST(hash_cache_is_per_covered_length)
    /* A prefix value and the owner that grew past it share one head. Each
     * must get the hash of ITS bytes, whichever computed (and cached) first,
     * in any interleaving — the cache is keyed by covered length. */
    str_t prefix = S("0123456789abcdefghij");                      /* 20 bytes, heap, no tail */
    str_t grown  = str_append(prefix, S("KLMNOPQRSTUVW"));          /* extends the same head */
    ASSERT(grown.head == prefix.head);
    int32_t hp = str_hash(str_from_bytes((const uint8_t*)"0123456789abcdefghij", 20));
    int32_t hg = str_hash(str_from_bytes((const uint8_t*)"0123456789abcdefghijKLMNOPQRSTUVW", 33));
    for (int round = 0; round < 3; round++) {
        ASSERT(str_hash(prefix) == hp);
        ASSERT(str_hash(grown) == hg);
        ASSERT(str_hash(grown) == hg);                               /* cached */
        ASSERT(str_hash(prefix) == hp);
    }
    ASSERT(hp != hg);
TEST_END()

static int32_t flat_hash(const char* c) { return str_hash(str_from_bytes((const uint8_t*)c, (int32_t)strlen(c))); }

TEST(hash_resumes_from_cached_prefix)
    /* The dict-key scenario: hash a key (caches its head's prefix state),
     * append in place, hash the grown value (resumes, caches a longer
     * prefix), hash the key again (the longer prefix does not apply: it must
     * recompute, not reuse) — plus a tailed value and a fork over the same
     * head. Every hash equals the hash of a fresh flat copy of its bytes. */
    str_t key = S("0123456789abcdefghij");                          /* 20 bytes */
    ASSERT(str_hash(key) == flat_hash("0123456789abcdefghij"));
    str_t tailed = str_append(key, S("xyz"));                        /* tail: 3 bytes */
    ASSERT(tailed.head == key.head && tail_len(tailed) == 3);
    ASSERT(str_hash(tailed) == flat_hash("0123456789abcdefghijxyz"));
    str_t grown = str_append(key, S("KLMNOPQRSTUVW"));               /* in place */
    ASSERT(grown.head == key.head);
    ASSERT(str_hash(grown) == flat_hash("0123456789abcdefghijKLMNOPQRSTUVW"));
    ASSERT(str_hash(key) == flat_hash("0123456789abcdefghij"));      /* after the longer prefix */
    ASSERT(str_hash(tailed) == flat_hash("0123456789abcdefghijxyz"));
    str_t fork = str_append(key, S("----------------"));             /* copies: new head */
    ASSERT(fork.head != key.head);
    ASSERT(str_hash(fork) == flat_hash("0123456789abcdefghij----------------"));
    ASSERT(str_hash(grown) == flat_hash("0123456789abcdefghijKLMNOPQRSTUVW"));
TEST_END()

TEST(slice_across_join)
    str_t t = mk_tailed("0123456789abcdef", "xyzw");
    ASSERT(same(str_slice(t, integer_from_int32(14), integer_from_int32(18)), "efxy"));
    ASSERT(same(str_slice(t, integer_from_int32(0), integer_from_int32(20)), "0123456789abcdefxyzw"));
    ASSERT(same(str_slice(t, integer_from_int32(5), integer_from_int32(3)), ""));
TEST_END()

TEST(byte_at_across_join)
    str_t t = mk_tailed("0123456789abcdef", "xy");
    ASSERT(str_byte_at(t, integer_from_int32(15)) == 'f');
    ASSERT(str_byte_at(t, integer_from_int32(17)) == 'y');
    ASSERT(str_byte_at(t, integer_from_int32(18)) == -1);
    ASSERT(str_byte_at(t, integer_from_int32(-1)) == -1);
TEST_END()

TEST(find_byte_in_tail)
    str_t t = mk_tailed("0123456789abcdef", "xy");
    ASSERT(int32_from_integer(str_find_byte(t, 'y', integer_from_int32(0))) == 17);
    ASSERT(int32_from_integer(str_find_byte(t, 'q', integer_from_int32(0))) == -1);
TEST_END()

TEST(index_of_straddles_join)
    str_t t = mk_tailed("0123456789abcdef", "xyzw");
    ASSERT(int32_from_integer(str_index_of(t, S("efxy"), integer_from_int32(0))) == 14);
    ASSERT(int32_from_integer(str_index_of(t, S("yzw"), integer_from_int32(0))) == 17);
    ASSERT(int32_from_integer(str_index_of(t, S("89a"), integer_from_int32(0))) == 8);
    ASSERT(int32_from_integer(str_index_of(t, S("fz"), integer_from_int32(0))) == -1);
    ASSERT(int32_from_integer(str_index_of(t, S(""), integer_from_int32(3))) == 3);
TEST_END()

TEST(codepoint_straddles_join)
    /* 16-byte head ending in 0xC3, tail starts with 0xA9: "é" across the join */
    uint8_t head[16]; memset(head, 'a', 15); head[15] = 0xC3;
    str_t h = str_from_bytes(head, 16);
    uint8_t tl[2] = { 0xA9, 'z' };
    str_t t = str_append(h, str_from_bytes(tl, 2));
    ASSERT(tail_len(t) == 2);
    ASSERT(str_codepoint_at(t, integer_from_int32(15)) == 0xE9);
    ASSERT(str_codepoint_at(t, integer_from_int32(16)) == -2);   /* mid-sequence: a malformed byte */
    ASSERT(str_valid_utf8(t));
    ASSERT(int32_from_integer(str_codepoint_count(t)) == 17);
    ASSERT(!str_valid_utf8(h));                                   /* truncated */
TEST_END()

TEST(find_and_skip_any_across_join)
    str_t t = mk_tailed("aaaaaaaaaaaaaaa ", " \tx!");
    ASSERT(int32_from_integer(str_find_any(t, S(" \t"), integer_from_int32(0))) == 15);
    ASSERT(int32_from_integer(str_skip_any(t, S(" \t"), integer_from_int32(15))) == 18);
    ASSERT(int32_from_integer(str_find_any(t, S("!"), integer_from_int32(0))) == 19);
    ASSERT(int32_from_integer(str_find_any(t, S("#"), integer_from_int32(0))) == 20);
TEST_END()

/* find/skip_any take a set of CODEPOINTS: multi-byte members and non-members
 * are whole characters, results land on codepoint boundaries, and a malformed
 * byte is never a member. The accept set is read three ways — in place (one
 * run), gathered from a tail into scratch, gathered into a heap copy (> 64
 * bytes) — and its ASCII members straddle both words of the bitmap. */
TEST(find_and_skip_any_unicode)
    str_t s = S("a\xC3\xA9\xE2\x82\xAC" "b~?@");        /* a é € b ~ ? @ : 10 bytes */
    ASSERT(int32_from_integer(str_find_any(s, S("\xE2\x82\xAC"), integer_from_int32(0))) == 3);
    ASSERT(int32_from_integer(str_find_any(s, S("b\xE2\x82\xAC\xC3\xA9"), integer_from_int32(0))) == 1);
    ASSERT(int32_from_integer(str_skip_any(s, S("a\xC3\xA9\xE2\x82\xAC"), integer_from_int32(0))) == 6);
    ASSERT(int32_from_integer(str_find_any(s, S(" \t"), integer_from_int32(0))) == 10);  /* steps over é, € */
    /* ASCII members in word 0 ('?' = 63) and word 1 ('@' = 64, '~' = 126) */
    ASSERT(int32_from_integer(str_find_any(s, S("~"), integer_from_int32(0))) == 7);
    ASSERT(int32_from_integer(str_find_any(s, S("?"), integer_from_int32(0))) == 8);
    ASSERT(int32_from_integer(str_find_any(s, S("@"), integer_from_int32(0))) == 9);
    ASSERT(int32_from_integer(str_skip_any(s, S("a\xC3\xA9\xE2\x82\xAC" "b~?"), integer_from_int32(0))) == 9);
    /* from = 2 is mid-sequence (é's continuation byte): malformed, not a member */
    ASSERT(int32_from_integer(str_find_any(s, S("\xE2\x82\xAC"), integer_from_int32(2))) == 3);
    ASSERT(int32_from_integer(str_skip_any(s, S("\xE2\x82\xAC"), integer_from_int32(2))) == 2);
    /* a tailed subject: é and ! live in the tail */
    str_t t = mk_tailed("aaaaaaaaaaaaaaaa", "\xC3\xA9!");
    ASSERT(tail_len(t) == 3);
    ASSERT(int32_from_integer(str_find_any(t, S("\xC3\xA9"), integer_from_int32(0))) == 16);
    ASSERT(int32_from_integer(str_skip_any(t, S("a\xC3\xA9"), integer_from_int32(0))) == 18);
    /* a tailed accept: gathered into scratch */
    str_t acc = mk_tailed("0123456789ABCDEF", "\xE2\x82\xAC");
    ASSERT(tail_len(acc) == 3);
    ASSERT(int32_from_integer(str_find_any(s, acc, integer_from_int32(0))) == 3);
    /* > 64 bytes: in place as one run, and gathered into a heap copy */
    uint8_t xs[72]; memset(xs, 'x', 70); xs[70] = 0xC3; xs[71] = 0xA9;
    str_t long_run = str_from_bytes(xs, 72);
    ASSERT(tail_len(long_run) == 0);
    ASSERT(int32_from_integer(str_find_any(s, long_run, integer_from_int32(0))) == 1);
    str_t long_tailed = str_append(str_from_bytes(xs, 70), S("\xC3\xA9"));
    ASSERT(tail_len(long_tailed) == 2);
    ASSERT(int32_from_integer(str_find_any(s, long_tailed, integer_from_int32(0))) == 1);
TEST_END()

TEST(parse_int_across_join)
    str_t t = mk_tailed("-000000000000123", "4567");
    ASSERT(integer_test_eq(str_parse_int(t), integer_from_int64(-1234567)));
    ASSERT(str_parse_int(S("12x")) == NULL);
TEST_END()

/* ---- slices, ordering, UTF-8 ---- */

TEST(slice_clamps_to_the_string)
    str_t s = S("hello");
    ASSERT(same(str_slice(s, integer_from_int32(0), integer_from_int32(5)), "hello"));
    ASSERT(same(str_slice(s, integer_from_int32(0), integer_from_int32(3)), "hel"));
    ASSERT(same(str_slice(s, integer_from_int32(2), integer_from_int32(5)), "llo"));
    ASSERT(str_length(str_slice(s, integer_from_int32(2), integer_from_int32(2))) == 0);
    ASSERT(str_length(str_slice(s, integer_from_int32(4), integer_from_int32(2))) == 0);   /* inverted */
    ASSERT(same(str_slice(s, integer_from_int32(0), integer_from_int32(100)), "hello"));
    ASSERT(same(str_slice(s, integer_from_int32(-5), integer_from_int32(3)), "hel"));
TEST_END()

TEST(compare_orders_by_bytes_then_length)
    ASSERT(str_compare(S("hello"), S("hello")) == 0);
    ASSERT(str_compare(S("abc"), S("abd")) < 0 && str_compare(S("abd"), S("abc")) > 0);
    ASSERT(str_compare(S("abc"), S("abcd")) < 0 && str_compare(S("abcd"), S("abc")) > 0);
    ASSERT(str_compare(S(""), S("")) == 0);
    /* by content and length, never stopping at a NUL; bytes compare unsigned */
    str_t a = str_from_bytes((const uint8_t*)"a\0bc", 4);
    str_t b = str_from_bytes((const uint8_t*)"a\0bd", 4);
    ASSERT(str_compare(a, str_from_bytes((const uint8_t*)"a\0bc", 4)) == 0);
    ASSERT(str_compare(a, b) < 0 && str_compare(b, a) > 0);
    ASSERT(str_compare(str_from_bytes((const uint8_t*)"\x80", 1), S("\x7f")) > 0);
TEST_END()

/* str_wchar encodes at every UTF-8 width boundary. */
TEST(wchar_encodes_every_width)
    static const struct { int32_t cp; const char* utf8; } cases[] = {
        { 0x41, "A" }, { 0x7F, "\x7f" },
        { 0x80, "\xc2\x80" }, { 0xE9, "\xc3\xa9" }, { 0x7FF, "\xdf\xbf" },
        { 0x800, "\xe0\xa0\x80" }, { 0x4E2D, "\xe4\xb8\xad" }, { 0xFFFF, "\xef\xbf\xbf" },
        { 0x10000, "\xf0\x90\x80\x80" }, { 0x1F600, "\xf0\x9f\x98\x80" }, { 0x10FFFF, "\xf4\x8f\xbf\xbf" },
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++)
        ASSERT(same(str_wchar(cases[i].cp), cases[i].utf8));
TEST_END()

TEST(codepoint_at_decodes_valid_sequences)
    str_t s = S("a\xc3\xa9\xe2\x82\xac\xf0\x9f\x8e\x89");      /* a é € 🎉 */
    ASSERT(str_codepoint_at(s, integer_from_int32(0)) == 'a');
    ASSERT(str_codepoint_at(s, integer_from_int32(1)) == 0xE9);
    ASSERT(str_codepoint_at(s, integer_from_int32(3)) == 0x20AC);
    ASSERT(str_codepoint_at(s, integer_from_int32(6)) == 0x1F389);
    ASSERT(str_codepoint_at(s, integer_from_int32(10)) == -1);      /* out of range */
    ASSERT(str_codepoint_at(s, integer_from_int32(-1)) == -1);
    /* a real U+FFFD is a valid three-byte sequence, not a malformed byte */
    ASSERT(str_codepoint_at(S("\xef\xbf\xbd"), integer_from_int32(0)) == 0xFFFD);
TEST_END()

/* Bytes that are not valid UTF-8 — a binary file read as a String — decode
 * as U+FFFD, ONE byte wide each: every walker makes progress and covers the
 * whole string, the count equals the number of steps, and the scanners see
 * U+FFFD. Only isValidUtf8 is strict. str_codepoint_at reports a malformed
 * byte as -2 (a one-byte U+FFFD), so ONE call yields both the value and the
 * width: a valid sequence is minimal, so its width follows from its value. */
static int32_t utf8_width(int32_t cp) { return cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4; }

TEST(malformed_bytes_decode_as_replacement)
    static const uint8_t bytes[] = {
        'a', 0xA9,            /* 1: stray continuation byte */
        'b', 0xF0, 0x9F,      /* 3,4: truncated 4-byte sequence */
        'c', 0xC0, 0x80,      /* 6,7: overlong NUL */
        0xED, 0xA0, 0x80,     /* 8..10: UTF-16 surrogate */
        0xFF,                 /* 11: never a lead byte */
        0xC3, 0xA9, 'd',      /* 12: a valid é (2 bytes), then 'd' */
    };
    str_t s = str_from_bytes(bytes, (int32_t)sizeof bytes);
    static const struct { int32_t off, raw; } expect[] = {   /* raw -2: malformed */
        {0,'a'}, {1,-2}, {2,'b'}, {3,-2}, {4,-2}, {5,'c'},
        {6,-2}, {7,-2}, {8,-2}, {9,-2}, {10,-2},
        {11,-2}, {12,0xE9}, {14,'d'},
    };
    int32_t n = (int32_t)(sizeof expect / sizeof expect[0]);
    /* the walk, one call per step: each lands exactly where the table says */
    int32_t off = 0, steps = 0, raw;
    while ((raw = str_codepoint_at(s, integer_from_int32(off))) != -1) {
        ASSERT(steps < n && off == expect[steps].off && raw == expect[steps].raw);
        off += raw == -2 ? 1 : utf8_width(raw);
        steps++;
    }
    ASSERT(steps == n && off == (int32_t)sizeof bytes);
    ASSERT(int32_from_integer(str_codepoint_count(s)) == n);
    ASSERT(str_codepoint_at(s, integer_from_int32(13)) == -2);   /* inside é */
    ASSERT(!str_valid_utf8(s));
    /* the scanners see U+FFFD */
    ASSERT(int32_from_integer(str_find_any(s, S("\xef\xbf\xbd"), integer_from_int32(0))) == 1);
    ASSERT(int32_from_integer(str_skip_any(s, S("ab\xef\xbf\xbd"), integer_from_int32(0))) == 5);
    ASSERT(int32_from_integer(str_find_any(s, S("d"), integer_from_int32(0))) == 14);
TEST_END()

TEST(codepoint_count_and_validity)
    str_t s = S("a\xc3\xa9\xe2\x82\xac\xf0\x9f\x8e\x89");      /* 10 bytes, 4 codepoints */
    ASSERT(str_length(s) == 10);
    ASSERT(int32_from_integer(str_codepoint_count(s)) == 4);
    ASSERT(int32_from_integer(str_codepoint_count(S(""))) == 0);
    ASSERT(str_valid_utf8(s));
    ASSERT(!str_valid_utf8(S("a\xc3")));                      /* a split sequence */
TEST_END()

/* ---- the C boundary ---- */

TEST(c_strings_in_and_out)
    ASSERT(same(str_from_cstr("from C"), "from C"));
    str_t t = mk_tailed("0123456789abcdef", "xy");
    char small[8], *heap;
    /* too long for the buffer: a heap copy, NUL-terminated */
    char* c = str_cstr(t, small, (int32_t)sizeof small, &heap);
    ASSERT(heap != NULL && c == heap && strcmp(c, "0123456789abcdefxy") == 0);
    free(heap);
    /* fits: the caller's buffer */
    c = str_cstr(S("hi"), small, (int32_t)sizeof small, &heap);
    ASSERT(heap == NULL && c == small && strcmp(c, "hi") == 0);
    /* truncating copy-out keeps size-1 bytes and terminates */
    char buf[5];
    ASSERT(str_copy_cstr(t, buf, (int32_t)sizeof buf) == 4 && strcmp(buf, "0123") == 0);
    ASSERT(str_copy_cstr(S("hello"), small, (int32_t)sizeof small) == 5 && strcmp(small, "hello") == 0);
TEST_END()

TEST(ascii_wchar_and_numbers)
    ASSERT(same(str_ascii('A'), "A") && str_is_inline(str_ascii('A')));
    ASSERT(same(str_wchar(0xE9), "\xC3\xA9"));
    ASSERT(same(str_from_int32(-42), "-42"));
    ASSERT(same(str_from_int64(1234567890123456789LL), "1234567890123456789"));
TEST_END()

/* ---- entrypoint ---- */

static roots_declaration_func_t prev_roots;
static void declare_roots(void(*declare)(object_t**)) { prev_roots(declare); }

static void run_tests(object_t* _, fun_t continuation) {
    (void)_;
    struct test_results r = {0, 0, NULL};
    struct test_results* _r = &r;
    printf("=== str tests ===\n");
    RUN(literal_short_inline);
    RUN(literal_long_heap);
    RUN(canonical_by_length);
    RUN(inline_equality_is_bytes);
    RUN(inline_append_every_length_pair);
    RUN(small_append_goes_to_tail);
    RUN(owner_extends_in_place);
    RUN(fork_copies_and_leaves_owner_intact);
    RUN(literal_head_is_read_only);
    RUN(read_only_head_takes_no_tail);
    RUN(random_appends_and_forks_match_reference);
    RUN(concat_n_first_operand_extends);
    RUN(compare_across_modes);
    RUN(hash_depends_only_on_bytes);
    RUN(hash_cache_is_per_covered_length);
    RUN(hash_resumes_from_cached_prefix);
    RUN(slice_across_join);
    RUN(byte_at_across_join);
    RUN(find_byte_in_tail);
    RUN(index_of_straddles_join);
    RUN(codepoint_straddles_join);
    RUN(find_and_skip_any_across_join);
    RUN(find_and_skip_any_unicode);
    RUN(parse_int_across_join);
    RUN(slice_clamps_to_the_string);
    RUN(compare_orders_by_bytes_then_length);
    RUN(wchar_encodes_every_width);
    RUN(codepoint_at_decodes_valid_sequences);
    RUN(malformed_bytes_decode_as_replacement);
    RUN(codepoint_count_and_validity);
    RUN(c_strings_in_and_out);
    RUN(ascii_wchar_and_numbers);
    PRINT_RESULTS("str", _r);
    object_t* status = integer_from_int32(r.failed ? 1 : 0);
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, status);
}

int main(void) {
    prev_roots = add_roots_declaration_func(declare_roots);
    thread_start(run_tests);
}
