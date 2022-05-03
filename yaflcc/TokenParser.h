//
// Created by Michael Brown on 18/03/2022.
//

#ifndef YAFLCC_TOKENPARSER_H
#define YAFLCC_TOKENPARSER_H

#include "Token.h"
#include <vector>
#include <string>


void parseTokens(std::string file, std::string_view characters, std::vector<Token>& tokens, std::vector<std::string>& errors);


#endif //YAFLCC_TOKENPARSER_H
