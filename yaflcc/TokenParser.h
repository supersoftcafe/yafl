//
// Created by Michael Brown on 18/03/2022.
//

#ifndef YAFLCC_TOKENPARSER_H
#define YAFLCC_TOKENPARSER_H

#include "Token.h"
#include <vector>
#include <string>

class TokenParser {
private:
    std::string characters_;

public:
    std::vector<Token> tokens;

    explicit TokenParser(std::string characters);
    ~TokenParser();
};


#endif //YAFLCC_TOKENPARSER_H
