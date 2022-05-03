//
// Created by Michael Brown on 18/03/2022.
//

#ifndef YAFLCC_TOKEN_H
#define YAFLCC_TOKEN_H

#include <vector>
#include <variant>
#include <functional>
#include <optional>
#include <string>
#include <tuple>
#include <span>


struct Source {
    std::string file;
    uint32_t line;
    uint32_t character;

    Source(std::string const & file, uint32_t line, uint32_t character) : file(file), line(line), character(character) { }
    Source() : file{}, line{}, character{} { }
};

struct Token {
    enum KIND {
        IGNORE = 0, UNKNOWN, EOI,

        INTRINSIC,
        MODULE, FUN, LET, USE, WHERE,
        NAME, INTEGER, FLOAT, STRING,
        COLON, QUESTION,

        DOT, AT,
        ADD, SUB, MUL, DIV, REM,
        SHL, ASHR, LSHR,
        AND, OR, XOR, NOT,
        EQ, NEQ, LT, LTE, GT, GTE,

        OBRACKET, CBRACKET, COMMA,
        SQUARE_OPEN, SQUARE_CLOSE,
    };

    Token(std::string text, Source source, uint32_t indent, KIND kind)
        : text(move(text)), source(source), indent(indent), kind(kind) { }
    Token() : text(), indent(0), kind(IGNORE) { }

    std::string text;
    Source source;
    uint32_t indent;
    KIND kind;
};

using Tokens = std::span<Token>;



// Needs to embody
//   Success + Optional<result>
//   Failure + Error info
template <class T>
struct ParseState {
private:
    std::variant<std::vector<std::string>, std::pair<Tokens, T>> v_;

public:
    ParseState(Tokens tk, T const & val) : v_{ std::in_place_type<std::pair<Tokens, T>>, tk, val } { }
    ParseState(Tokens tk, T && val) : v_{ std::in_place_type<std::pair<Tokens, T>>, tk, std::move(val) } { }
    ParseState(std::vector<std::string>&& errors) : v_{ std::in_place_type<std::vector<std::string>>, std::move(errors) } { }
    ParseState() : v_{ std::in_place_type<std::vector<std::string>>, std::vector<std::string>{ } } { }

    void emplace(Tokens tk, T && val) { v_.template emplace<std::pair<Tokens, T>>(tk, std::move(val)); }

    bool has_result() const { return std::holds_alternative<std::pair<Tokens, T>>(v_); }
    bool has_errors() const { return std::holds_alternative<std::vector<std::string>>(v_) && !std::get<std::vector<std::string>>(v_).empty(); }

    T& result() { return std::get<std::pair<Tokens, T>>(v_).second; }
    Tokens tokens() { return std::get<std::pair<Tokens, T>>(v_).first; }
    std::vector<std::string>& errors() { return std::get<std::vector<std::string>>(v_); }

    operator Tokens () { return tokens(); }
};



inline ParseState<Token*> getToken(Tokens tokens) {
    return { tokens.subspan(1), &tokens.front() };
}

inline Token* peekToken(Tokens tokens) {
    return &tokens.front();
}


template <class Type>
inline ParseState<Type> operator | (ParseState<Type> p1, ParseState<Type> p2) {
    if (p1.has_result() || (!p2.has_result() && !p2.has_errors()))
        return std::move(p1);
    return std::move(p2);
}

template <class Type, typename Lambda>
inline ParseState<Type> operator | (ParseState<Type> p1, Lambda p2) {
    if (p1.has_result())
        return std::move(p1);
    return p2();
}

#endif //YAFLCC_TOKEN_H
