//
// Created by mbrown on 30/03/24.
//

#include "lists.h"
#include <stdlib.h>
#include <assert.h>

#define MAGIC 0x883a7fe

void lists_push(list_node_t **head_ptr, list_node_t *node) {
    node->magic = MAGIC;
    if (*head_ptr) {
        // There is a circular list already here that we can insert into
        node->next = *head_ptr;
        node->prev = node->next->prev;
        node->next->prev = node;
        node->prev->next = node;
    } else {
        // No list yet so initialise it with this element looped on itself
        node->next = node;
        node->prev = node;
        *head_ptr = node;
    }
}

list_node_t *lists_pop_newest(list_node_t **head_ptr) {
    list_node_t *node = *head_ptr;
    if ( node == NULL ) {
        // List is empty
    } else if ( node->prev == node ) {
        // This was the last node, so we need to reset the head
        assert(node->magic == MAGIC);
        *head_ptr = NULL;

        node->magic = 0;
        node->next = NULL;
        node->prev = NULL;
    } else {
        // Newest is 'prev' to head node
        node = node->prev;
        assert(node->magic == MAGIC);

        // Unlink it
        list_node_t *p = node->prev;
        list_node_t *n = node->next;
        n->prev = p; p->next = n;

        node->magic = 0;
        node->next = NULL;
        node->prev = NULL;
    }
    return node;
}

list_node_t *lists_pop_oldest(list_node_t **head_ptr) {
    list_node_t *node = *head_ptr;
    if ( node == NULL ) {
        // List is empty
    } else if ( node->next == node ) {
        // This was the last node, so we need to reset the head
        assert(node->magic == MAGIC);
        *head_ptr = NULL;

        node->magic = 0;
        node->next = NULL;
        node->prev = NULL;
    } else {
        // Newest is the head so move the head
        assert(node->magic == MAGIC);
        *head_ptr = node->next;

        // Unlink it
        list_node_t *p = node->prev;
        list_node_t *n = node->next;
        n->prev = p; p->next = n;

        node->magic = 0;
        node->next = NULL;
        node->prev = NULL;
    }
    return node;
}


