
#undef NDEBUG
#include <assert.h>
#include <string.h>
#include "../src/mmap.h"
#include "../src/string.h"
#include "../src/integer.h"


static object_t* create(char* cstr) {
    intptr_t buf;
    object_t* a = string_create_from_cstr(cstr);
    assert(strcmp(cstr, string_to_cstr(a, &buf)) == 0);
    return a;
}


void test_string() {
    intptr_t buf;

    mmap_init();
    object_init();

    heap_t heap;
    object_heap_create(&heap);
    object_heap_select(&heap);

    object_t* a = create("fred");
    object_t* b = create(" ");
    object_t* c = create("bill");
    object_t* d = create("aggriculture");
    object_t* e = create(".");

    object_t* r;

    r = string_append(a, b);
    assert(strcmp("fred ", string_to_cstr(r, &buf)) == 0);
    r = string_append(r, c);
    assert(strcmp("fred bill", string_to_cstr(r, &buf)) == 0);
    r = string_append(r, b);
    assert(strcmp("fred bill ", string_to_cstr(r, &buf)) == 0);
    r = string_append(r, d);
    r = string_append(r, e);

    char* cstr = "fred bill aggriculture.";
    object_t* r_cstr = string_create_from_cstr(cstr);
    assert(string_compare(r, r_cstr) == 0);
    char* x = string_to_cstr(r, &buf);
    uint32_t l = strlen(x);
    assert(strcmp(cstr, x) == 0);

    char* cstr2 = "fred bill aggriculture..";
    object_t* r_cstr2 = string_create_from_cstr(cstr2);
    assert(string_compare(r, r_cstr2) != 0);

    // Sliced result will be heap allocated. End offset should be cropped at end of string.
    object_t* sliced3 = string_slice(r, integer_create_from_native(4), integer_create_from_native(100));
    char* cstr3 = " bill aggriculture.";
    object_t* r_cstr3 = string_create_from_cstr(cstr3);
    assert(string_compare(sliced3, r_cstr3) == 0);

    // This slice should be small enough to be packed into the pointer. Start offset should be cropped at start of string.
    object_t* sliced4 = string_slice(r, integer_create_from_native(-100), integer_create_from_native(5));
    char* cstr4 = "fred ";
    object_t* r_cstr4 = string_create_from_cstr(cstr4);
    assert(string_compare(sliced4, r_cstr4) == 0);
}
