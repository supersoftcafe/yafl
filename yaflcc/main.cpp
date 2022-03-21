
#include "Token.h"
#include "TokenParser.h"
#include "GrammarParser.h"
#include <iostream>
#include <fstream>
#include <vector>
#include <regex>


int main(int argc, char** argv) {
    std::ifstream        in { argv[1] };
    TokenParser tokenParser { std::string(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()) };
    tokenParser.parse();

    GrammarParser grammarParser;
    grammarParser.parseFile(tokenParser.tokens());

    return 0;
}
