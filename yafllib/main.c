
#include "yafl.h"
#include <stdio.h>

static roots_declaration_func_t previous_declare_roots;
static void declare_roots(void(*declare)(object_t**)) {
    previous_declare_roots(declare);
}

static void entrypoint(object_t* self, fun_t continuation) {
    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, INTEGER_LITERAL_1(0));
}


int main(int argc, char** argv) {
    previous_declare_roots = add_roots_declaration_func(declare_roots);
    thread_start(entrypoint);
}
