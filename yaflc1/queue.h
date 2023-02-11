//
// Created by Michael Brown on 09/02/2023.
//

#ifndef YAFLC1_QUEUE_H
#define YAFLC1_QUEUE_H

#include <stdlib.h>

void queue_init(size_t size);
void queue_push(void* value, uintptr_t priority);
void* queue_pop();


#endif //YAFLC1_QUEUE_H
