
#ifndef YAFLR_INTEGER_H
#define YAFLR_INTEGER_H

#include "object.h"


object_t* integer_create();
object_t* integer_create_from_native(intptr_t value);
object_t* integer_add(object_t* self, object_t* data);
object_t* integer_add_with_native(object_t* self, intptr_t value);
int integer_compare(object_t* self, object_t* data);
int integer_compare_with_native(object_t* self, intptr_t value);
intptr_t integer_to_native(object_t* self);


#endif

