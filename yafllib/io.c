
#include "yafl.h"
#include <stdio.h>

typedef struct {
    object_t parent;
    FILE*      file;
    bool      owned;
} io_t;

VTABLE_DECLARE_STRUCT(io_vtable, 16);
static struct io_vtable IO_VTABLE = {
    .object_size = sizeof(io_t),
    .array_el_size = 0,
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = 0,
    .name = "io",
    .implements_array = VTABLE_IMPLEMENTS(0),
};

