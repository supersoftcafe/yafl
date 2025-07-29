
#include "yafl.h"
#include <stdio.h>
#include <stdlib.h>

static roots_declaration_func_t previous_declare_roots;

static void declare_roots(void(*declare)(object_t**)) {
    previous_declare_roots(declare);
}





void test1() {
    object_t* one = INTEGER_LITERAL_1(0, 1);
    object_t* twenty = INTEGER_LITERAL_1(0, 20);
    object_t* result = integer_add(twenty, one);
    object_t* twentyone = INTEGER_LITERAL_1(0, 21);
    int32_t comparison = integer_cmp(result, twentyone);

    fprintf(stderr, "%llx %llx %llx %llx %d\n", (intptr_t)one, (intptr_t)twenty, (intptr_t)result, (intptr_t)twentyone, comparison);

    if (comparison) {
        fprintf(stderr, "Failed 20+1\n");
        abort();
    }
}




static void entrypoint(object_t* self, fun_t continuation) {

    test1();


    ((void(*)(object_t*,object_t*))continuation.f)(continuation.o, INTEGER_LITERAL_1(0, 0));
}


int main(int argc, char** argv) {
    previous_declare_roots = add_roots_declaration_func(declare_roots);
    thread_start(entrypoint);
}
