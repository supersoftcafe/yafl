//
// Created by mbrown on 30/03/24.
//

#ifndef YAFLR_LISTS_H
#define YAFLR_LISTS_H


struct list_node;
typedef struct list_node list_node_t;
struct list_node {
    int magic;
    list_node_t *next, *prev;
};

void lists_push(list_node_t **head_ptr, list_node_t *node);

list_node_t *lists_pop_newest(list_node_t **head_ptr);

list_node_t *lists_pop_oldest(list_node_t **head_ptr);


#endif //YAFLR_LISTS_H
