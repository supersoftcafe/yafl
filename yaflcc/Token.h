//
// Created by Michael Brown on 18/03/2022.
//

#ifndef YAFLCC_TOKEN_H
#define YAFLCC_TOKEN_H

#include <functional>
#include <optional>
#include <string>
#include <tuple>
#include <span>

class Token {
public:
    enum KIND { IGNORE,
        MODULE, FUN, LET,
        NAME, NUMBER,
        COLON, EQUALS, DOT,
    };

    Token(std::string_view text, int line, int character, KIND kind) : text(text), line(line), character(character), kind(kind) { }
    Token() : text(), line(0), character(0), kind(IGNORE) { }

    std::string_view text;
    int line, character;
    KIND kind;
};

using Tokens = std::span<Token>;

template <class T>
struct ParseState : public std::optional<std::pair<Tokens, T>> {
    ParseState(Tokens tk, T val) : std::optional<std::pair<Tokens, T>>({tk, val }) { }
    ParseState() = default;

    void xfer(T& result) {
        if (*this)
            std::swap(result, this->value().second);
    }

    T& result() { return this->value().second; }
    Tokens tokens() { return this->value().first; }
    operator Tokens () { return tokens(); }
};


inline ParseState<Token*> getToken(Tokens tokens, Token::KIND kind = Token::IGNORE) {
    if (std::empty(tokens) || (kind != Token::IGNORE && tokens.front().kind != kind))
        return { };
    return { tokens.subspan(1), &tokens.front() };
}

template <class T>
inline ParseState<T> operator | (ParseState<T> opt1, ParseState<T> opt2) {
    return empty(opt1) ? opt2 : opt1;
}



#endif //YAFLCC_TOKEN_H
