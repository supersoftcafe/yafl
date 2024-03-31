//
// Created by mbrown on 30/03/24.
//

#include "lists.h"
#include "blitz.h"
#include <stdlib.h>
#include <assert.h>

static const intptr_t MAGIC_HEAD = 0x30fe3a2;
static const intptr_t MAGIC_NODE = 0x883a7fe;

void lists_init(list_head_t *head) {
#ifndef NDEBUG
    head->l.magic = MAGIC_HEAD;
#endif
    head->l.next = &head->l;
    head->l.prev = &head->l;
}

list_node_t *lists_get_next(list_head_t *head, list_node_t *node) {
    return node->next == &head->l ? node->next->next : node->next;
}

list_node_t *lists_get_head(list_head_t *head) {
    return head->l.next == &head->l ? NULL : head->l.next;
}

void lists_push(list_head_t *head, list_node_t *node) {
    assert(head->l.magic == MAGIC_HEAD);
    assert(node->magic != MAGIC_NODE);
    assert(node->magic != MAGIC_HEAD);

#ifndef NDEBUG
    node->magic = MAGIC_NODE;
#endif

    node->next = &head->l;
    node->prev = head->l.prev;
    node->prev->next = node;
    head->l.prev = node;
}

list_node_t *lists_pop_newest(list_head_t *head) {
    assert(head->l.magic == MAGIC_HEAD);

    list_node_t *node = head->l.prev;

    list_node_t *prev = node->prev;
    list_node_t *next = &head->l;

    prev->next = next;
    next->prev = prev;

    node = node == &head->l ? NULL : node;

    assert(node == NULL || node->magic == MAGIC_NODE);
#ifndef NDEBUG
    if (node != NULL)
        node->magic = 0;
#endif

    return node;
}

list_node_t *lists_pop_oldest(list_head_t *head) {
    assert(head->l.magic == MAGIC_HEAD);

    list_node_t *node = head->l.next;

    list_node_t *prev = &head->l;
    list_node_t *next = node->next;

    prev->next = next;
    next->prev = prev;

    node = node == &head->l ? NULL : node;

    assert(node == NULL || node->magic == MAGIC_NODE);
#ifndef NDEBUG
    if (node != NULL)
        node->magic = 0;
#endif

    return node;
}


