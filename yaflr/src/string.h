
#ifndef YAFLR_STRING_H
#define YAFLR_STRING_H

#include "object.h"


object_t* string_create();
object_t* string_create_from_cstr(char* data);
object_t* string_create_from_bytes(uint8_t* data, intptr_t length);

object_t* string_append(object_t* self, object_t* data);
object_t* string_slice(object_t* self, object_t* start, object_t* end);

int string_compare(object_t* self, object_t* data);
intptr_t string_length_native(object_t* self);
object_t* string_length(object_t* self);

char* string_to_cstr(object_t* self, intptr_t* local_buffer);


#endif
