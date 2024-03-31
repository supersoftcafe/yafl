//
// Created by mbrown on 30/03/24.
//

#ifndef YAFLR_LISTS_H
#define YAFLR_LISTS_H

#include <stdint.h>

struct list_node;
typedef struct list_node list_node_t;
struct list_node {
    intptr_t magic;
    list_node_t *next, *prev;
};

struct list_head;
typedef struct list_head list_head_t;
struct list_head {
    list_node_t l;
};


void lists_init(list_head_t *head);

void lists_push(list_head_t *head, list_node_t *node);

list_node_t *lists_pop_newest(list_head_t *head);

list_node_t *lists_pop_oldest(list_head_t *head);

list_node_t *lists_get_head(list_head_t *head);

list_node_t *lists_get_next(list_head_t *head, list_node_t *node);


#endif //YAFLR_LISTS_H
