//
// Created by mbrown on 09/04/24.
//

#ifndef YAFLC_ERROR_H
#define YAFLC_ERROR_H


#include <string>

using namespace std;



struct LineRef {
    size_t line;
    size_t offset;
};


struct Error22 {
    LineRef line;
    string message;

    Error22(LineRef line, string&& message) : line(line), message(std::move(message)) { }

    // Delete copy constructor and assignment operator
    Error22(const Error22&) = delete;
    Error22& operator=(const Error22&) = delete;
    Error22(Error22&&) = default;
};

#endif //YAFLC_ERROR_H
