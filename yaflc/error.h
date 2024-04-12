//
// Created by mbrown on 09/04/24.
//

#ifndef YAFLC_ERROR_H
#define YAFLC_ERROR_H

#include <string>

using namespace std;

struct Error {
    size_t line;
    size_t offset;
    string message;
    string_view code;
};

#endif //YAFLC_ERROR_H
