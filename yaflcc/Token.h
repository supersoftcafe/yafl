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

class Token {
public:
    enum KIND {
        IGNORE, UNKNOWN, EOI,

        MODULE, FUN, LET,
        NAME, NUMBER,
        COLON, QUESTION,

        DOT,
        ADD, SUB, MUL, DIV, REM,
        SHL, ASHR, LSHR,
        AND, OR, XOR, NOT,
        EQ, NEQ, LT, LTE, GT, GTE,

        OBRACKET, CBRACKET, COMMA,
    };

    Token(std::string_view text, uint32_t line, uint32_t character, uint32_t indent, KIND kind)
        : text(text), line(line), indent(indent), character(character), kind(kind) { }
    Token() : text(), line(0), character(0), indent(0), kind(IGNORE) { }

    std::string_view text;
    uint32_t line, character, indent;
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

template <class T>
inline ParseState<T> operator | (ParseState<T> opt1, ParseState<T> opt2) {
    return empty(opt1) ? opt2 : opt1;
}



#endif //YAFLCC_TOKEN_H
