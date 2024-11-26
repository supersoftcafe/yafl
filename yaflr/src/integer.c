
#include "integer.h"
#include <stdint.h>
#include <alloca.h>
#include <assert.h>


struct integer {
    vtable_t* vtable;
    uint32_t length;
    intptr_t array[0];
};
typedef struct integer integer_t;


static vtable_t VTABLE = {
    .object_size = offsetof(integer_t, array[0]),
    .array_el_size = sizeof(intptr_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .array_len_index = offsetof(integer_t, length),
    .functions_mask = 0
};




object_t* integer_create() {
    return (object_t*)1;
}

static integer_t* integer_allocate(uint32_t length) {
    integer_t* integer = object_create_array(integer_t, array, length);
    integer->vtable = &VTABLE;
    integer->length = length;
    return integer;
}

object_t* integer_create_from_native(intptr_t value) {
    if (value == 0) {
        return (object_t*)1;
    } else if (value >= INTPTR_MIN/2 && value <= INTPTR_MAX/2) {
        return (object_t*)((intptr_t)value * 2 + 1);
    } else {
        integer_t* integer = integer_allocate(1);
        integer->array[0] = value;
        return (object_t*)integer;
    }
}

object_t* integer_add_with_native(object_t* self, intptr_t value) {
    integer_t* a = (integer_t*)self;

    if ((1 & (intptr_t)a) != 0) {
        // Try to add inside the container word directly, but if it overflows fallback to the usual algorithm.
        intptr_t result;
        if (!__builtin_add_overflow((intptr_t)a, value*2, &result)) {
            return (object_t*)result; // Bit 0 is retained, so it's still flagged as immediate
        }
    }

    struct {
        vtable_t* vtable;
        uint32_t length;
        intptr_t array[1];
    } integer = {
        .vtable = NULL, // Nothing uses the vtable pointer
        .length = 1,
        .array[0] = value
    };

    return integer_add(self, (object_t*)&integer);
}

object_t* integer_add(object_t* self, object_t* data) {
    integer_t* a = (integer_t*)self;
    integer_t* b = (integer_t*)data;

    // If both inputs are immediate, do a fast add
    if ((1 & (intptr_t)a) != 0 && (1 & (intptr_t)b) != 0) {
        return integer_create_from_native( (intptr_t)a / 2 + (intptr_t)b / 2 );
    }

    // If either input is immediate, copy to an object for convenience
    if ((1 & (intptr_t)a) != 0) {
        integer_t* tmp = alloca(offsetof(integer_t, array[1]));
        tmp->array[0] = (intptr_t)a / 2;
        tmp->length = 1;
        a = tmp;
    }
    if ((1 & (intptr_t)b) != 0) {
        integer_t* tmp = alloca(offsetof(integer_t, array[1]));
        tmp->array[0] = (intptr_t)b / 2;
        tmp->length = 1;
        b = tmp;
    }

    // Allocate enough space for the result and one overflow word
    integer_t* r = integer_allocate((a->length > b->length ? a : b)->length + 1);

    // Extract sign information for the adding loop
    intptr_t sign_a = a->array[a->length-1] >> (sizeof(intptr_t)*8-1);
    intptr_t sign_b = b->array[b->length-1] >> (sizeof(intptr_t)*8-1);

    // Adding loop
    uintptr_t carry = 0;
    for (uint32_t index = 0; index < r->length; ++index) {
        r->array[index] = __builtin_addcl(
            index < a->length ? a->array[index] : sign_a,
            index < b->length ? b->array[index] : sign_b,
            carry, &carry);
    }

    // Trim off redundent words at end retaining sign information
    while (r->length > 1 && r->array[r->length-1] == r->array[r->length-2] >> (sizeof(intptr_t)*8-1)) {
        r->length -= 1;
    }

    // If we can fit the result into a word, discard the allocation immediately
    if (r->length == 1 && (r->array[0] >= INTPTR_MIN/2 && r->array[0] <= INTPTR_MAX/2)) {
        return (object_t*)(r->array[0] * 2 + 1);
    }

    return (object_t*)r;
}

int integer_compare_with_native(object_t* self, intptr_t value) {
    integer_t* a = (integer_t*)self;

    if ((1 & (intptr_t)a) != 0) {
        intptr_t avalue = (intptr_t)a / 2;
        if (avalue < value) return -1;
        if (avalue > value) return 1;
        return 0;
    }

    if (a->length == 1) {
        intptr_t avalue = a->array[0];
        if (avalue < value) return -1;
        if (avalue > value) return 1;
        return 0;
    }

    return a->array[a->length-1] < 0 ? -1 : 1;
}

int integer_compare(object_t* self, object_t* data) {
    integer_t* a = (integer_t*)self;
    integer_t* b = (integer_t*)data;

    // If both inputs are immediate, do a fast compare
    if ((1 & (intptr_t)a) != 0 && (1 & (intptr_t)b) != 0) {
        if ((intptr_t)a < (intptr_t)b) return -1;
        if ((intptr_t)a > (intptr_t)b) return 1;
        return 0;
    }

    // If either input is immediate, copy to an object for convenience
    if ((1 & (intptr_t)a) != 0) {
        integer_t* tmp = alloca(offsetof(integer_t, array[1]));
        tmp->array[0] = (intptr_t)a / 2;
        tmp->length = 1;
        a = tmp;
    }
    if ((1 & (intptr_t)b) != 0) {
        integer_t* tmp = alloca(offsetof(integer_t, array[1]));
        tmp->array[0] = (intptr_t)b / 2;
        tmp->length = 1;
        b = tmp;
    }

    // Extract sign information for the comparison loop
    intptr_t sign_a = a->array[a->length-1] >> (sizeof(intptr_t)*8-1);
    intptr_t sign_b = b->array[b->length-1] >> (sizeof(intptr_t)*8-1);

    // Early exit if sign tells us a quick answer
    if (sign_a < sign_b) return -1;
    if (sign_a > sign_b) return 1;

    // Comparison loop. Because the sign of both is the same, we can do unsigned comparison
    for (uint32_t index = (a->length > b->length ? a : b)->length; index-- > 0; ) {
        uintptr_t ai = (uintptr_t)(index < a->length ? a->array[index] : sign_a);
        uintptr_t bi = (uintptr_t)(index < b->length ? b->array[index] : sign_b);
        if (ai < bi) return -1;
        if (ai > bi) return 1;
    }

    return 0;
}

intptr_t integer_to_native(object_t* self) {
    integer_t* a = (integer_t*)self;

    if ((1 & (intptr_t)a) != 0) {
        return (intptr_t)a / 2;
    }

    assert(a->length == 1);

    return a->array[0];
}

