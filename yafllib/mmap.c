
#include <pthread.h>
#include <sys/mman.h>
#include <unistd.h>

#include "common.h"
#include "yafl.h"


EXPORT void abort_on_out_of_memory() {
    log_error_and_exit("Aborting due to memory allocation failure", stderr);
}


// TODO: Remove upper limit on RAM

typedef struct {
    uint32_t size;
    _Atomic(uint32_t) index;
    char* start;
    _Atomic(uint8_t) table[16];
} _pages_info_t;

static pthread_once_t pages_once = ONCE_FLAG_INIT;
static _pages_info_t* pages_info = NULL;

static void init2() {
    size_t count = 16ULL*1024*1024*1024 / GC_PAGE_SIZE;
    size_t size = sizeof(_pages_info_t) + count + (count * GC_PAGE_SIZE) + GC_PAGE_SIZE;
    void *ptr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_ANONYMOUS | MAP_PRIVATE, -1, 0);
    if (ptr == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }

    uintptr_t ptr_int = (uintptr_t)ptr;
    uintptr_t ptr_aligned = (ptr_int + GC_PAGE_SIZE - 1) &~ (GC_PAGE_SIZE - 1);
    uintptr_t ptr_end = ptr_aligned + (GC_PAGE_SIZE * count);
    // We're not releasing the unused pages because, they're unused and the OS doesn't allocate them until accessed anyway.

    _pages_info_t* p = (_pages_info_t*)ptr_end;
    p->size = count;
    p->index = 0;
    p->start = (char*)ptr_aligned;
    memset(p->table, 0, count);

    pages_info = p;
}

static _pages_info_t* init() {
    pthread_once(&pages_once, init2);
    return pages_info;
}

static _Atomic(size_t) alloc_count = 0;
static _Atomic(size_t) free_count = 0;

EXPORT void* memory_pages_alloc(size_t page_count) {
    assert(page_count == 1);

    _pages_info_t* p = pages_info ?: init();

    for (uint32_t count = 0; count < p->size; ++count) {
        size_t index = atomic_fetch_add(&p->index, 1) % p->size;

        uint8_t expected = 0;
        _Atomic(uint8_t) *cptr = (_Atomic(uint8_t)*)&p->table[index];
        if (atomic_compare_exchange_strong(cptr, &expected, 1)) {
            char *ptr = p->start + (index*GC_PAGE_SIZE);
            atomic_fetch_add(&alloc_count, 1);
            return ptr;
        }
    }

    abort_on_out_of_memory();
    return NULL;
}

EXPORT void memory_pages_free(void* ptr, size_t page_count) {
    assert(page_count == 1);
    assert(memory_pages_is_heap(ptr));
    assert(((uintptr_t)ptr & (GC_PAGE_SIZE-1)) == 0);

    _pages_info_t* p = pages_info;
    size_t index = ((char*)ptr - p->start) / GC_PAGE_SIZE;

    assert(index < p->size);
    assert(p->table[index] == 1);

    atomic_fetch_add(&free_count, 1);
    madvise(ptr, GC_PAGE_SIZE, MADV_DONTNEED);
    atomic_store(&p->table[index], 0);
}

EXPORT bool memory_pages_is_heap(void* ptr) {
    _pages_info_t* p = pages_info;
    ptrdiff_t offset = (char*)ptr - p->start;
    return offset >= 0 && offset < ((size_t)p->size * GC_PAGE_SIZE);
}


