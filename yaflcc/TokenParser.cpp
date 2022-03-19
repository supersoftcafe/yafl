//
// Created by Michael Brown on 18/03/2022.
//

#include "TokenParser.h"
#include <iostream>
#include <regex>

TokenParser::TokenParser(std::string characters) : characters_(characters), success_(false) {
}

TokenParser::~TokenParser() {
}

bool TokenParser::parse() {
#define Rx(expr, tok)    { std::regex(expr), Token::tok }
    std::pair<std::regex, Token::KIND> PATTERNS[] {
            Rx("[ \t\r\n]+", IGNORE ),
            Rx(":", COLON ),
            Rx("=", EQUALS ),
            Rx("\\.", DOT ),
            Rx("module", MODULE ),
            Rx("(fun)|(let)", FUN ),
            Rx("(`[^`]+`)|([a-zA-Z_][a-zA-Z_0-9]*)", NAME ),
            Rx("[0-9]+", NUMBER ),
    };

    std::string_view view = characters_;
    int line = 1; int character = 1;

    while (!view.empty()) {
        size_t      matchedSize = 0;
        Token::KIND matchedKind = Token::IGNORE;

        for (auto&[regex, kind]: PATTERNS) {
            std::match_results<std::string_view::const_iterator> match;
            if (std::regex_search(view.cbegin(), view.cend(), match, regex, std::regex_constants::match_continuous)) {
                if (match.size() > matchedSize) {
                    matchedSize = match.length();
                    matchedKind = kind;
                }
            }
        }

        if (matchedSize == 0) {
            std::cerr << "bad character" << std::endl;
            return false;
        } else {
            auto text = view.substr(0, matchedSize);

            if (matchedKind != Token::IGNORE)
                tokens_.emplace_back(text, line, character, matchedKind);
            view = view.substr(matchedSize);

            for (auto chr : text) {
                if (chr == '\n') {
                    line += 1;
                    character = 1;
                } else {
                    character += 1;
                }
            }
        }
    }

    return success_ = true;
}
