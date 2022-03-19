//
// Created by Michael Brown on 15/03/2022.
//

#include "input.h"
#include <iostream>
#include <sstream>


void input::reset(std::string const & data, int firstLine) {
    in.str(data);
    in.clear();

    tokens_vector.clear();
    tokennumber = 0;
    linenumber = firstLine;
}

bool input::getline() {
    tokennumber = 0;
    tokens_vector.clear();

    for (std::string tok; std::getline(in, line); ) {
        linenumber += 1;

        bool iscomment = false;
        std::istringstream ss { line };
        while (std::getline(ss, tok, ' ')) {
            if (!tok.empty()) {
                if (tok.at(0) == '#')
                    iscomment = true;
                if (!iscomment)
                    tokens_vector.push_back(tok);
            }
        }

        if (!tokens_vector.empty())
            return true;
    }

    return false;
}

std::string input::pop() {
    return tokennumber < tokens_vector.size() ? tokens_vector.at(tokennumber++) : "";
}

std::string input::peek() {
    return tokennumber < tokens_vector.size() ? tokens_vector.at(tokennumber) : "";
}


[[noreturn]]
void input::rfatal(int line, char const * file, std::string_view msg) const {
    std::cerr << file << ':' << line << ", fatal " << linenumber << ": " << msg << std::endl;
    ::exit(1);
}

void input::rwarn(int line, char const * file, std::string_view msg) const {
    std::cerr << file << ':' << line << ", warn " << linenumber << ": " << msg << std::endl;
}