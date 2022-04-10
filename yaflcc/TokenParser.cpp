//
// Created by Michael Brown on 18/03/2022.
//

#include "TokenParser.h"
#include <iostream>
#include <regex>


TokenParser::TokenParser(std::string characters) : characters_(characters) {
#define Rx(expr, tok)    { std::regex(expr), Token::tok }
    std::pair<std::regex, Token::KIND> PATTERNS[] {
            Rx("[ \r\n]+", IGNORE ),

            Rx("\\?", QUESTION), Rx(":", COLON ),

            Rx("\\.", DOT ),
            Rx("\\+", ADD ), Rx(  "-", SUB ), Rx("\\*", MUL ), Rx(  "/", DIV ), Rx(  "%", REM ),
            Rx( "<<", SHL ), Rx( ">>",ASHR ), Rx(">>>",LSHR ),
            Rx(  "&", AND ), Rx("\\^", XOR ), Rx("\\|",  OR ),
            Rx(  "=",  EQ ), Rx( "!=", NEQ ), Rx(  "<",  LT ), Rx( "<=", LTE ), Rx(  ">",  GT ), Rx( ">=", GTE ),
            Rx(  "!", NOT ),


            Rx("\\(", OBRACKET ),
            Rx("\\)", CBRACKET ),
            Rx(",", COMMA ),

            Rx("module", MODULE ),
            Rx("(fun)|(let)", FUN ),

            Rx("(`[^`]+`)|([a-zA-Z_][a-zA-Z_0-9]*)", NAME ),
            Rx("[0-9]+", NUMBER ),
    };

    std::string_view view = characters_;
    uint32_t line = 1, character = 1, indent = 0;
    bool startOfLine = true;

    while (!view.empty()) {
        size_t      matchedSize = 1;
        Token::KIND matchedKind = Token::UNKNOWN;

        for (auto&[regex, kind]: PATTERNS) {
            std::match_results<std::string_view::const_iterator> match;
            if (std::regex_search(view.cbegin(), view.cend(), match, regex, std::regex_constants::match_continuous)) {
                matchedSize = match.length();
                matchedKind = kind;
                break;
            }
        }

        auto text = view.substr(0, matchedSize);

        if (matchedKind != Token::IGNORE)
            tokens.emplace_back(text, line, character, indent, matchedKind);
        view = view.substr(matchedSize);

        for (auto chr : text) {
            if (chr == '\n') {
                line += 1;
                character = 0;
                startOfLine = true;
                indent = 0;
            } else if (startOfLine) {
                if (chr == ' ') indent ++;
                else startOfLine = false;
            }
            character += 1;
        }
    }

    tokens.emplace_back("", line, character, indent, Token::EOI);
}

TokenParser::~TokenParser() {
}
