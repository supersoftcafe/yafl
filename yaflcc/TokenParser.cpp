//
// Created by Michael Brown on 18/03/2022.
//

#include "TokenParser.h"
#include <iostream>
#include <regex>

using namespace std;

void parseTokens(string_view view, vector<Token>& tokens, vector<string>& errors) {
#define Rx(expr, tok)    { regex(expr), Token::tok },
    pair<regex, Token::KIND> PATTERNS[] {
            Rx("([ \r\n]+)|(#[^\r\n]*\n)", IGNORE )

            Rx("\\?", QUESTION) Rx(":", COLON )

            Rx("\\.", DOT ) Rx(  "@",  AT )
            Rx("\\+", ADD ) Rx(  "-", SUB ) Rx("\\*", MUL ) Rx(  "/", DIV ) Rx(  "%", REM )
            Rx(">>>",LSHR ) Rx( "<<", SHL ) Rx( ">>",ASHR )
            Rx(  "=",  EQ ) Rx( "!=", NEQ ) Rx( "<=", LTE ) Rx( ">=", GTE ) Rx(  "<",  LT ) Rx(  ">",  GT )
            Rx(  "&", AND ) Rx("\\^", XOR ) Rx("\\|",  OR )
            Rx(  "!", NOT ) Rx(",", COMMA )
            Rx("\\(", OBRACKET ) Rx("\\[", SQUARE_OPEN)
            Rx("\\)", CBRACKET ) Rx("\\]", SQUARE_CLOSE)

            Rx("use", USE )
            Rx("module", MODULE )
            Rx("(fun)|(let)", FUN )
            Rx("(`[^`]+`)|([a-zA-Z_][a-zA-Z_0-9]*)", NAME )

            Rx("[+-]?([0-9]*)\\.[0-9]+", FLOAT )
            Rx("[+-]?((0b[_0-1]+)|(0o[_0-7]+)|(0x[_0-9a-f]+)|([0-9]+))", INTEGER )
            Rx("\"([^\"]|\\\\\")*\"", STRING )
    };

    uint32_t line = 1, character = 1, indent = 0;
    bool startOfLine = true;

    while (!view.empty()) {
        size_t      matchedSize = 1;
        Token::KIND matchedKind = Token::UNKNOWN;

        for (auto&[regex, kind]: PATTERNS) {
            match_results<string_view::const_iterator> match;
            if (regex_search(view.cbegin(), view.cend(), match, regex, regex_constants::match_continuous)) {
                matchedSize = match.length();
                matchedKind = kind;
                break;
            }
        }

        if (matchedSize == 0) {
            errors.emplace_back(to_string(line) + ':' + to_string(indent) + " unknown character");
            return;
        }

        auto text = view.substr(0, matchedSize);

        if (matchedKind != Token::IGNORE)
            tokens.emplace_back(string(text), line, character, indent, matchedKind);
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

