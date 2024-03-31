//
// Created by mbrown on 30/03/24.
//

#undef NDEBUG
#include <assert.h>
#include "../src/blitz.h"
#include "../src/lists.h"


void test_lists() {
    list_head_t head;
    lists_init(&head);

    list_node_t node1, node2, node3;

    lists_push(&head, &node1);
    lists_push(&head, &node2);
    lists_push(&head, &node3);

    list_node_t *result;

    result = lists_pop_newest(&head);
    assert(result == &node3);

    result = lists_pop_oldest(&head);
    assert(result == &node1);

    result = lists_pop_newest(&head);
    assert(result == &node2);

    result = lists_pop_oldest(&head);
    assert(result == NULL);

    result = lists_pop_newest(&head);
    assert(result == NULL);

    result = lists_pop_oldest(&head);
    assert(result == NULL);
}