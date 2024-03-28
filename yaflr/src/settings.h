//
// Created by mbrown on 25/02/24.
//

#ifndef YAFLR_SETTINGS_H
#define YAFLR_SETTINGS_H

enum { FIBER_SIZE = 65536 };
enum { FIBER_SIZE_LOG2 = 16 };
enum { MAX_FIBER_COUNT = 1024 };

#define index_of_lowest_bit(value)               \
        _Generic( (value),                       \
            unsigned long long: __builtin_ctzll, \
            unsigned long: __builtin_ctzl,       \
            unsigned int: __builtin_ctz          \
        )(value)

#define total_bits(type) \
        (sizeof(type) * 8)


#endif //YAFLR_SETTINGS_H
