#include <stdio.h>
#include "yafl.h"

typedef struct {
    int32_t _0;
    int32_t _1;
} struct_anon_0_t;

// System::main@hDMEOS
typedef struct {
    object_t* type;
    fun_t Q36qcontinuation;
} SystemQ__qmainQ64qhDMEOSQ36qframe_t;

// System::Pair@k7nUo1
typedef struct {
    object_t* type;
    int32_t leftQ64qE5nlZh;
    int32_t rightQ64qTEsfgl;
} SystemQ__qPairQ64qk7nUo1_t;

// System::Pair@k7nUo1
EXTERN decl_func
void SystemQ__qPairQ64qk7nUo1(object_t* this, int32_t leftQ64qE5nlZh, int32_t rightQ64qTEsfgl, fun_t Q36qcontinuation);

// System::main@hDMEOS
EXTERN decl_func
void SystemQ__qmainQ64qhDMEOS(object_t* this, fun_t Q36qcontinuation);

// System::main@hDMEOS
EXTERN decl_func
void SystemQ__qmainQ64qhDMEOSQ36qcontQ36q0(object_t* Q36qframe, object_t* Q36qvalue);

EXTERN decl_func
void __entrypoint__(object_t* this, fun_t Q36qcontinuation);

// System::main@hDMEOS
static vtable_t* const obj_SystemQ__qmainQ64qhDMEOSQ36qframe;

// System::Pair@k7nUo1
static vtable_t* const obj_SystemQ__qPairQ64qk7nUo1;


// System::main@hDMEOS
static vtable_t* const obj_SystemQ__qmainQ64qhDMEOSQ36qframe = VTABLE_DECLARE(2){
    .object_size = sizeof(SystemQ__qmainQ64qhDMEOSQ36qframe_t),
    .array_el_size = 0,
    .object_pointer_locations = (0|maskof(SystemQ__qmainQ64qhDMEOSQ36qframe_t, .Q36qcontinuation.o)),
    .array_el_pointer_locations = 0,
    .functions_mask = rotate_function_id(1),
    .array_len_offset = 0,
    .implements_array = VTABLE_IMPLEMENTS(0, ),
    .lookup = {
        { .i = -1, .f = (void*)&__abort_on_vtable_lookup },
        { .i = -1, .f = (void*)&__abort_on_vtable_lookup } },
};

// System::Pair@k7nUo1
static vtable_t* const obj_SystemQ__qPairQ64qk7nUo1 = VTABLE_DECLARE(2){
    .object_size = sizeof(SystemQ__qPairQ64qk7nUo1_t),
    .array_el_size = 0,
    .object_pointer_locations = (0),
    .array_el_pointer_locations = 0,
    .functions_mask = rotate_function_id(1),
    .array_len_offset = 0,
    .implements_array = VTABLE_IMPLEMENTS(0, ),
    .lookup = {
        { .i = -1, .f = (void*)&__abort_on_vtable_lookup },
        { .i = -1, .f = (void*)&__abort_on_vtable_lookup } },
};

// System::Pair@k7nUo1
EXPORT decl_func
void SystemQ__qPairQ64qk7nUo1(object_t* this, int32_t leftQ64qE5nlZh, int32_t rightQ64qTEsfgl, fun_t Q36qcontinuation)
{
    /* Begin local variables */
    struct_anon_0_t uvar_0;
    object_t* uvar_1;

    /* Begin operations */
    uvar_0 = (struct_anon_0_t){
        ._0 = ((int32_t)leftQ64qE5nlZh),
        ._1 = ((int32_t)rightQ64qTEsfgl)
    };
    uvar_1 = object_create(obj_SystemQ__qPairQ64qk7nUo1);
    ((SystemQ__qPairQ64qk7nUo1_t*)uvar_1)->leftQ64qE5nlZh = (uvar_0._0);
    ((SystemQ__qPairQ64qk7nUo1_t*)uvar_1)->rightQ64qTEsfgl = (uvar_0._1);
    {
        fun_t fun = Q36qcontinuation;
        return ((void(*)(void*, object_t*))fun.f)(fun.o, uvar_1);
    }
}

// System::main@hDMEOS
EXPORT decl_func
void SystemQ__qmainQ64qhDMEOS(object_t* this, fun_t Q36qcontinuation)
{
    /* Begin local variables */
    object_t* uvar_0;
    object_t* xQ64q7AsGLU;
    object_t* Q36qframe;

    /* Begin operations */
    Q36qframe = object_create(obj_SystemQ__qmainQ64qhDMEOSQ36qframe);
    ((SystemQ__qmainQ64qhDMEOSQ36qframe_t*)object_mutation(Q36qframe))->Q36qcontinuation = Q36qcontinuation;
    {
        fun_t fun = ((fun_t){.f=SystemQ__qPairQ64qk7nUo1,.o=NULL});
        return ((void(*)(void*, int32_t, int32_t, fun_t, fun_t))fun.f)(fun.o, ((int32_t)1), ((int32_t)2), ((fun_t){.f=SystemQ__qmainQ64qhDMEOSQ36qcontQ36q0,.o=Q36qframe}), ((fun_t){.f=SystemQ__qmainQ64qhDMEOSQ36qcontQ36q0,.o=NULL}));
    }
cont$0:
    xQ64q7AsGLU = uvar_0;
    {
        fun_t fun = Q36qcontinuation;
        return ((void(*)(void*, int32_t))fun.f)(fun.o, ((SystemQ__qPairQ64qk7nUo1_t*)xQ64q7AsGLU)->rightQ64qTEsfgl);
    }
}

// System::main@hDMEOS
EXPORT decl_func
void SystemQ__qmainQ64qhDMEOSQ36qcontQ36q0(object_t* Q36qframe, object_t* Q36qvalue)
{
    /* Begin local variables */
    object_t* uvar_0;
    object_t* xQ64q7AsGLU;

    /* Begin operations */
    uvar_0 = Q36qvalue;
    goto cont$0;
    {
        fun_t fun = ((fun_t){.f=SystemQ__qPairQ64qk7nUo1,.o=NULL});
        ((void(*)(void*, int32_t, int32_t, fun_t))fun.f)(fun.o, ((int32_t)1), ((int32_t)2), ((fun_t){.f=SystemQ__qmainQ64qhDMEOSQ36qcontQ36q0,.o=Q36qframe}));
    }
cont$0:
    xQ64q7AsGLU = uvar_0;
    {
        fun_t fun = ((SystemQ__qmainQ64qhDMEOSQ36qframe_t*)Q36qframe)->Q36qcontinuation;
        return ((void(*)(void*, int32_t))fun.f)(fun.o, ((SystemQ__qPairQ64qk7nUo1_t*)xQ64q7AsGLU)->rightQ64qTEsfgl);
    }
}

EXPORT decl_func
void __entrypoint__(object_t* this, fun_t Q36qcontinuation)
{
    /* Begin local variables */
    int32_t result;

    /* Begin operations */
    {
        fun_t fun = ((fun_t){.f=SystemQ__qmainQ64qhDMEOS,.o=NULL});
        return ((void(*)(void*, fun_t))fun.f)(fun.o, Q36qcontinuation);
    }
}


EXPORT decl_func
void declare_roots_yafl(void(*declare)(object_t**)) {
}
