//
// Created by Michael Brown on 09/02/2023.
//

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include "context.h"
#include "blitz.h"


struct entry {
    void*       value;
    intptr_t priority;
};

static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  cond = PTHREAD_COND_INITIALIZER;
static struct entry*   queue;
static atomic_size_t   count = 0;

static size_t          QUEUE_SIZE;


void queue_init(size_t size) {
    QUEUE_SIZE = size;
    queue = malloc(size);
    if (queue == NULL)
        ERROR("malloc");
}

void queue_push(void* value, intptr_t priority) {
    int err;

    err = pthread_mutex_lock(&mutex);
    if (err)
        ERROR("pthread_mutex_lock failed with code %d\n", err);

    size_t index = atomic_fetch_add(&count, 1);
    if (index >= QUEUE_SIZE) {
        atomic_fetch_sub(&count, 1);
        ERROR("job queue is full\n");
    }

    // BEGIN push to queue
    for (size_t parent; index > 0 && queue[parent = (index-1)/2].priority > priority; index = parent)
        queue[index] = queue[parent];
    struct entry entry = { value, priority };
    queue[index] = entry;
    // END push to queue

    err = pthread_cond_signal(&cond);
    if (err)
        ERROR("pthread_cond_signal failed with code %d\n", err);

    err = pthread_mutex_unlock(&mutex);
    if (err)
        ERROR("pthread_mutex_unlock failed with code %d\n", err);
}

void* queue_pop() {
    int err;

    err = pthread_mutex_lock(&mutex);
    if (err)
        ERROR("pthread_mutex_lock failed with code %d\n", err);

    while (atomic_load(&count) == 0) {
        err = pthread_cond_wait(&cond, &mutex);
        if (err)
            ERROR("pthread_cond_wait failed with code %d\n", err);
    }

    DEBUG("Queue size is %ld\n", count);

    // START pop from queue;
    atomic_fetch_sub(&count, 1);
    void* result = queue[0].value;
    if (count > 0) {
        struct entry entry = queue[count];
        size_t index = 0;
        for (size_t child1; (child1 = (index * 2) + 1) < count; ) {
            size_t child2 = child1 + 1;
            size_t child = (child2 < count && queue[child2].priority < queue[child1].priority) ? child2 : child1;
            if (queue[child].priority >= entry.priority) break;
            queue[index] = queue[child];
            index = child;
        }
        queue[index] = entry;
    }
    // END pop from queue

    err = pthread_mutex_unlock(&mutex);
    if (err)
        ERROR("pthread_mutex_unlock failed with code %d\n", err);

    return result;
}

