
#include "yafl.h"
#include <stdio.h>
#include <errno.h>

typedef struct {
    object_t parent;
    FILE*    file;
    bool     owned;
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


static object_t* _io_wrap(FILE* file, bool owned) {
    io_t* io = (io_t*)object_create((vtable_t*)&IO_VTABLE);
    io->file  = file;
    io->owned = owned;
    return (object_t*)io;
}

static object_t* _io_fopen(object_t* path, const char* mode) {
    char buf[4096];
    string_copy_cstr(path, buf, sizeof(buf));
    errno = 0;
    FILE* f = fopen(buf, mode);
    return f ? _io_wrap(f, true) : integer_create_from_int32(-errno);
}


EXPORT object_t* io_stdin(object_t* self) {
    return _io_wrap(stdin, false);
}

EXPORT object_t* io_stdout(object_t* self) {
    return _io_wrap(stdout, false);
}

EXPORT object_t* io_stderr(object_t* self) {
    return _io_wrap(stderr, false);
}

EXPORT object_t* io_create(object_t* self, object_t* path) {
    return _io_fopen(path, "w");
}

EXPORT object_t* io_open_read(object_t* self, object_t* path) {
    return _io_fopen(path, "r");
}

EXPORT object_t* io_open_write(object_t* self, object_t* path, bool truncate) {
    return _io_fopen(path, truncate ? "w" : "a");
}

EXPORT object_t* io_read(object_t* self, object_t* o_length) {
    io_t* io = (io_t*)self;
    if (io->file == NULL)
        return NULL;

    int overflow = 0;
    int32_t length = integer_to_int32_with_overflow(o_length, &overflow);
    if (overflow || length <= 0 || length > INT32_MAX - 1)
        return integer_create_from_int32(-EINVAL);

    if (length <= 32) {
        uint8_t buf[32];
        int32_t n = (int32_t)fread(buf, 1, length, io->file);
        if (n > 0)
            return string_from_bytes(buf, n);
        if (feof(io->file))
            return NULL;
        return integer_create_from_int32(-errno);
    } else {
        object_t* s = string_allocate(length);
        int32_t n = (int32_t)fread(((string_t*)s)->array, 1, length, io->file);
        if (n > 0)
            return string_truncate(s, n);
        if (feof(io->file))
            return NULL;
        return integer_create_from_int32(-errno);
    }
}

EXPORT object_t* io_write(object_t* self, object_t* data) {
    io_t* io = (io_t*)self;
    if (io->file == NULL)
        return NULL;
    const char* bytes;
    int32_t len;
    char stack_buf[sizeof(uintptr_t)];
    if (PTR_IS_STRING(data)) {
        len = string_copy_cstr(data, stack_buf, sizeof(stack_buf));
        bytes = stack_buf;
    } else {
        len = string_length(data);
        bytes = (const char*)((string_t*)data)->array;
    }
    errno = 0;
    int32_t n = (int32_t)fwrite(bytes, 1, len, io->file);
    if (n < len && errno != 0)
        return integer_create_from_int32(-errno);
    return integer_create_from_int32(n);
}

EXPORT object_t* io_close(object_t* self) {
    io_t* io = (io_t*)self;
    if (io->owned && io->file != NULL)
        fclose(io->file);
    io->file = NULL;
    return NULL;
}
