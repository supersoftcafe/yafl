
/*
#if defined(_WIN32)
#  define THREAD_MODEL windows
#  include <windows.h>
#else
#  define THREAD_MODEL posix
#  include <pthread.h>
#endif*/


#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <errno.h>


#ifndef __STDC_NO_THREADS__
#include <threads.h>
#endif

#ifndef __STDC_NO_ATOMICS__
#include <stdatomic.h>
#endif


#ifndef thread_local
#  if __STDC_VERSION__ >= 201112 && !defined __STDC_NO_THREADS__
#    define thread_local _Thread_local
#  elif defined(_WIN32) && (defined(_MSC_VER) || defined(__ICL) || defined(__DMC__) || defined(__BORLANDC__) )
#    define thread_local __declspec(thread)
#  elif defined(__GNUC__) || defined(__SUNPRO_C) || defined(__xlC__)
#    define thread_local __thread  __attribute__((tls_model("initial-exec")))
#  else
#    error "Cannot define thread_local"
#  endif
#endif


#define STACK_GROWTH_DIRECTION    -1




