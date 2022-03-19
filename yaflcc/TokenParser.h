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
    std::string    characters_;
    std::vector<Token> tokens_;
    bool              success_;

public:
    explicit TokenParser(std::string characters);
    ~TokenParser();

    bool parse();

    bool success() const {
        return success_;
    }

    std::vector<Token> & tokens() {
        return tokens_;
    }
};


#endif //YAFLCC_TOKENPARSER_H
