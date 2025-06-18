
#include "common.h"
#include "yafl.h"


/**********************************************************
 *****************************
 *************
 *****
 **
 *                     Big integer
 **
 *****
 *************
 *****************************
 **********************************************************/

#include <alloca.h>


struct integer_vtable {
    vtable_t v;
};
EXPORT struct integer_vtable INTEGER_VTABLE = { .v = {
    .object_size = offsetof(integer_t, array[0]),
    .array_el_size = sizeof(intptr_t),
    .object_pointer_locations = 0,
    .array_el_pointer_locations = 0,
    .functions_mask = 0,
    .array_len_offset = offsetof(integer_t, length),
    .implements_array = VTABLE_IMPLEMENTS(0),
} };


EXPORT integer_t* _integer_allocate(uint32_t length) {
    return (integer_t*)array_create((vtable_t*)&INTEGER_VTABLE, length);
}


EXPORT object_t* integer_create_from_intptr(intptr_t value) {
    if (value < INTPTR_MIN/2 || value > INTPTR_MAX/2) {
        integer_t* integer = _integer_allocate(1);
        integer->array[0] = value;
        return (object_t*)integer;
    }
    return (object_t*)((intptr_t)value * 2 + 1);
}


EXPORT COLD object_t* integer_addsub_full(object_t* self, object_t* data, intptr_t(*operation)(intptr_t,intptr_t,uintptr_t,uintptr_t*)) {
    integer_t* a = (integer_t*)self;
    integer_t* b = (integer_t*)data;

    // If either input is immediate, copy to an object for convenience
    if (((intptr_t)a & 1) != 0) {
        integer_t* tmp = (integer_t*)alloca(offsetof(integer_t, array[1]));
        tmp->array[0] = (intptr_t)a / 2;
        tmp->length = 1;
        a = tmp;
    }
    if (((intptr_t)b & 1) != 0) {
        integer_t* tmp = (integer_t*)alloca(offsetof(integer_t, array[1]));
        tmp->array[0] = (intptr_t)b / 2;
        tmp->length = 1;
        b = tmp;
    }

    // Allocate enough space for the result and one overflow word
    integer_t* r = _integer_allocate((a->length > b->length ? a : b)->length + 1);

    // Extract sign information for the adding loop
    intptr_t sign_a = a->array[a->length-1] >> (sizeof(intptr_t)*8-1);
    intptr_t sign_b = b->array[b->length-1] >> (sizeof(intptr_t)*8-1);

    // Adding loop
    uintptr_t carry = 0;
    for (uint32_t index = 0; index < r->length; ++index) {
        r->array[index] = operation(
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


static intptr_t __operation_add__(intptr_t a, intptr_t b, uintptr_t carry_in, uintptr_t* carry_out) {
    return __builtin_addcl(a, b, carry_in, carry_out);
}


EXPORT object_t* integer_add(object_t* self, object_t* data) {
    if (LIKELY(((intptr_t)self & (intptr_t)data & 1) != 0)) {
        intptr_t result = (intptr_t)self / 2 + (intptr_t)data / 2;
        if (LIKELY(result >= INTPTR_MIN/2 && result <= INTPTR_MAX/2)) {
            return (object_t*)(result * 2 + 1);
        }
    }
    return integer_addsub_full(self, data, __operation_add__);
}


static intptr_t __operation_sub__(intptr_t a, intptr_t b, uintptr_t carry_in, uintptr_t* carry_out) {
    return __builtin_subcl(a, b, carry_in, carry_out);
}


EXPORT object_t* integer_sub(object_t* self, object_t* data) {
    if (LIKELY(((intptr_t)self & (intptr_t)data & 1) != 0)) {
        intptr_t result = (intptr_t)self / 2 + (intptr_t)data / 2;
        if (LIKELY(result >= INTPTR_MIN/2 && result <= INTPTR_MAX/2)) {
            return (object_t*)(result * 2 + 1);
        }
    }
    return integer_addsub_full(self, data, __operation_sub__);
}



EXPORT object_t* integer_div(object_t* self, object_t* data) {
    if (LIKELY(((intptr_t)self & (intptr_t)data & 1) != 0)) {
        intptr_t result = ((intptr_t)self / 2) / ((intptr_t)data / 2);
        return (object_t*)(result * 2 + 1);
    }
    __abort_on_overflow(); // TODO: Implement long division
    __builtin_unreachable();
}


EXPORT object_t* integer_rem(object_t* self, object_t* data) {
    if (LIKELY(((intptr_t)self & (intptr_t)data & 1) != 0)) {
        intptr_t result = ((intptr_t)self / 2) % ((intptr_t)data / 2);
        return (object_t*)(result * 2 + 1);
    }
    __abort_on_overflow(); // TODO: Implement long division
    __builtin_unreachable();
}


EXPORT object_t* integer_add_intptr(object_t* self, intptr_t value) {
    integer_t* a = (integer_t*)self;

    if (((intptr_t)a & 1) != 0 && value >= INTPTR_MIN/2 && value <= INTPTR_MAX/2) {
        // Try to add without removing the marker bit.
        // If it overflows fallback to the usual algorithm.
        intptr_t result;
        if (!__builtin_add_overflow((intptr_t)a, value*2, &result)) {
            return (object_t*)result; // Bit 0 is retained, so it's still flagged as immediate
        }
    }

    integer_t* tmp = (integer_t*)alloca(offsetof(integer_t, array[1]));
    tmp->array[0] = value;
    tmp->length = 1;

    return integer_addsub_full(self, (object_t*)tmp, __operation_add__);
}


EXPORT COLD int integer_cmp_full(object_t* self, object_t* data) {
    integer_t* a = (integer_t*)self;
    integer_t* b = (integer_t*)data;

    // If either input is immediate, copy to an object for convenience
    if (((intptr_t)a & 1) != 0) {
        integer_t* tmp = (integer_t*)alloca(offsetof(integer_t, array[1]));
        tmp->array[0] = (intptr_t)a / 2;
        tmp->length = 1;
        a = tmp;
    }
    if (((intptr_t)b & 1) != 0) {
        integer_t* tmp = (integer_t*)alloca(offsetof(integer_t, array[1]));
        tmp->array[0] = (intptr_t)b / 2;
        tmp->length = 1;
        b = tmp;
    }

    // Extract sign information for the comparison loop
    intptr_t sign_a = a->array[a->length-1] >> (sizeof(intptr_t)*8-1);
    intptr_t sign_b = b->array[b->length-1] >> (sizeof(intptr_t)*8-1);

    // Early exit if sign tells us a quick answer
    if (sign_a < sign_b)
        return -1;
    if (sign_a > sign_b)
        return 1;

    // Comparison loop. Because the sign of both is the same, we can do unsigned comparison
    for (uint32_t index = (a->length > b->length ? a : b)->length; index-- > 0; ) {
        uintptr_t ai = (uintptr_t)(index < a->length ? a->array[index] : sign_a);
        uintptr_t bi = (uintptr_t)(index < b->length ? b->array[index] : sign_b);
        if (ai < bi)
            return -1;
        if (ai > bi)
            return 1;
    }

    return 0;
}


EXPORT int integer_cmp_intptr(object_t* self, intptr_t value) {
    integer_t* a = (integer_t*)self;

    intptr_t avalue;
    if (((intptr_t)a & 1) != 0) {
        avalue = (intptr_t)a / 2;
        if (avalue < value) return -1;
        if (avalue > value) return 1;
        return 0;
    } else {
        value = 0;
        avalue = a->array[a->length-1];
        if (a->length != 1)
            value = 0;
    }
    if (avalue < value)
        return -1;
    if (avalue > value)
        return 1;
    return 0;
}


EXPORT int32_t integer_cmp(object_t* self, object_t* data) {
    // If both inputs are immediate, do a fast compare
    if (LIKELY(((intptr_t)self & (intptr_t)data & 1) != 0)) {
        if ((intptr_t)self < (intptr_t)data) return -1;
        if ((intptr_t)self > (intptr_t)data) return 1;
        return 0;
    }
    return integer_cmp_full(self, data);
}


EXPORT int32_t _integer_to_int32(object_t* self, int* overflow) {
    intptr_t result;
    if (((intptr_t)self & 1) != 0) {
        result = (intptr_t)self / 2;
    } else {
        integer_t* a = (integer_t*)self;
        if (a->length > 1) {
            *overflow = 1;
            result = a->array[a->length-1] < 0 ? INT32_MIN : INT32_MAX;
        } else {
            result = a->array[0];
#if WORD_SIZE == 64
            if (result < INT32_MIN) {
                *overflow = 1;
                result = INT32_MIN;
            } else if (result > INT32_MAX) {
                *overflow = 1;
                result = INT32_MAX;
            }
#endif
        }
    }

    return result;
}



