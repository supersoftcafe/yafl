#include <yafl.h>







static NOINLINE
void __entrypoint__(object_t* this, fun_t Q36qcontinuation);

// Main::main@evc0xJ
static NOINLINE
void MainQ__qmainQ64qevc0xJ(object_t* this, fun_t Q36qcontinuation);

// System::print@uFyesN
static NOINLINE
void SystemQ__qprintQ64quFyesN(object_t* this, object_t* strQ64q2VKuiZ, fun_t Q36qcontinuation);

static object_t* Q36qstringsQ__qstringQ64q0;




static object_t* Q36qstringsQ__qstringQ64q0 = STR("Hi there\n");

static NOINLINE
void __entrypoint__(object_t* this, fun_t Q36qcontinuation)
{
    /* Begin local variables */
    int32_t result;

    /* Begin operations */
    {
        fun_t fun = ((fun_t){.f=MainQ__qmainQ64qevc0xJ,.o=NULL});
        return ((void(*)(void*, fun_t))fun.f)(fun.o, Q36qcontinuation);
    }
}

// Main::main@evc0xJ
static NOINLINE
void MainQ__qmainQ64qevc0xJ(object_t* this, fun_t Q36qcontinuation)
{
    /* Begin local variables */
    object_t* uvar_s0_0;

    /* Begin operations */
    {
        fun_t fun = ((fun_t){.f=SystemQ__qprintQ64quFyesN,.o=NULL});
        return ((void(*)(void*, object_t*, fun_t))fun.f)(fun.o, Q36qstringsQ__qstringQ64q0, Q36qcontinuation);
    }
}

// System::print@uFyesN
static NOINLINE
void SystemQ__qprintQ64quFyesN(object_t* this, object_t* strQ64q2VKuiZ, fun_t Q36qcontinuation)
{
    /* Begin local variables */
    
    /* Begin operations */
    {
        fun_t fun = Q36qcontinuation;
        return ((void(*)(void*, object_t*))fun.f)(fun.o, print_string(strQ64q2VKuiZ));
    }
}


static roots_declaration_func_t _previous_declare_roots;
static void _declare_roots(void(*declare)(object_t**)) {
    _previous_declare_roots(declare);
    declare(&Q36qstringsQ__qstringQ64q0);
}


int main() {
    _previous_declare_roots = add_roots_declaration_func(_declare_roots);
    thread_start(__entrypoint__);
    return 0;
}
