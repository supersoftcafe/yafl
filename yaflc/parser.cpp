//
// Created by mbrown on 09/04/24.
//

#include "parser.h"
#include <algorithm>
#include <optional>
#include <span>
#include <functional>
#include <type_traits>
#include <concepts>
#include <cassert>

namespace ps {
    using namespace std::placeholders;

    using Tokens = span<tk::Token const>::iterator;
    struct Parsed {
        list<Node> nodes;
        list<ErrorMessage> errors;
        Tokens newhead;

        Parsed(Tokens t): newhead { t } { }
        Parsed(Node&& n, Tokens t) : newhead { t } {
            nodes.emplace_back(std::move(n));
        }
        Parsed(ErrorMessage&& e, Tokens t) : newhead { t } {
            errors.emplace_back(std::move(e));
        }
        Parsed(Node&& n, ErrorMessage&& e, Tokens t) : newhead { t } {
            nodes.emplace_back(std::move(n));
            errors.emplace_back(std::move(e));
        }

        // Delete copy constructor and assignment operator
        Parsed(const Parsed&) = delete;
        Parsed& operator=(const Node&) = delete;
        Parsed(Parsed&&) = default;
    };

    template<typename T>
    using Parser = function<Parsed(Tokens,Tokens)>;

/*
    template<typename T>
    using Parsed = optional<tuple<T, list<Error>, Tokens>>;

    template<typename T>
    using Parser = function<Parsed<T>(Tokens,Tokens)>;

    template<typename P>
    using Parser_result_t = std::invoke_result_t<P, Tokens, Tokens>;

    template<typename P>
    using Parser_value_t = tuple_element_t<0, typename Parser_result_t<P>::value_type>;


    // Type trait to check if a type is a std::tuple
    template<typename T>
    struct is_tuple : std::false_type {};

    template<typename... T>
    struct is_tuple<std::tuple<T...>> : std::true_type {};

    // Helper function to convert a value to a tuple if it's not already one
    template<typename T>
    auto to_tuple(T&& value) {
        if constexpr (is_tuple<std::decay_t<T>>::value) {
            return std::forward<T>(value);
        } else {
            return std::make_tuple(std::forward<T>(value));
        }
    }



    // Type trait to check if a type is a std::variant
    template<typename T>
    struct is_variant : std::false_type {};

    template<typename... T>
    struct is_variant<std::variant<T...>> : std::true_type {};

    // Helper function to convert a value to a tuple if it's not already one
    template<typename T>
    auto to_variant(T&& value) {
        if constexpr (is_variant<std::decay_t<T>>::value) {
            return std::forward<T>(value);
        } else {
            return std::variant<std::decay_t<T>>(std::forward<T>(value));
        }
    }


    template <typename R, int O, typename T, int I = 0>
    R variant_translate(T&& value) {
        if constexpr (I < std::variant_size<std::decay_t<T>>::value) {
            if (I == value.index())
                return R { std::in_place_index_t<O + I>(), std::move(std::get<I>(value)) };
            else
                return variant_translate<R, O, T, I+1>(value);
        } else {
            std::abort();
        }
    }

    template<typename T>
    struct as_variant {
        using type = std::variant<T>;
    };

    template<typename... T>
    struct as_variant<std::variant<T...>> {
        using type = std::variant<T...>;
    };

    template <typename ... T>
    using as_variant_t = typename as_variant<T...>::type;


    template <class... Args>
    struct template_concat;

    template <template <class...> class T, class... Args1, class... Args2, typename... Remaining>
    struct template_concat<T<Args1...>, T<Args2...>, Remaining...> {
        using type = typename template_concat<T<Args1..., Args2...>, Remaining...>::type;
    };

    template <template <class...> class T, class... Args1>
    struct template_concat<T<Args1...>> {
        using type = T<Args1...>;
    };

    template <class... Args>
    using template_concat_t = typename template_concat<Args...>::type;





    template <typename P1, typename P2> requires std::invocable<P1, Tokens, Tokens>
        && std::invocable<P2, Tokens, Tokens>
        && std::convertible_to<invoke_result_t<P2,Tokens,Tokens>, invoke_result_t<P1,Tokens,Tokens>>
    auto operator ^ (P1 parser1, P2 parser2) {
        return [=](Tokens head, Tokens tail) {
            return invoke(parser1, head, tail).or_else([=]() {
                return invoke(parser2, head, tail);
            });
        };
    }

    template <typename P1, typename P2> requires std::invocable<P1, Tokens, Tokens> && std::invocable<P2, Tokens, Tokens>
    auto all(P1 parser1, P2 parser2) {
        return [=](Tokens head, Tokens tail) {
            return invoke(parser1, head, tail).and_then([=](auto&& value1) {
                auto&& [ node1, newhead1 ] = value1;
                return invoke(parser2, newhead1, tail).transform([&](auto&& value2) {
                    auto&& [ node2, newhead2 ] = value2;
                    return pair { tuple_cat( to_tuple(std::move(node1)), to_tuple(std::move(node2)) ), get<1>(value2) };
                });
            });
        };
    }

    template <typename P1, typename P2> requires std::invocable<P1, Tokens, Tokens> && std::invocable<P2, Tokens, Tokens>
    auto operator & (P1 parser1,  P2 parser2) {
        using R1 = Parser_value_t<P1>;
        using R2 = Parser_value_t<P2>;
        return [=](Tokens head, Tokens tail) {
            return invoke(parser1, head, tail).and_then([=](auto&& value1) {
                auto&& [ node1, errors1, newhead1 ] = value1;

                if (empty(errors1)) {
                    return invoke(parser2, newhead1, tail).transform([&](auto&& value2) {
                        auto&& [ node2, errors2, newhead2 ] = value2;
                        return tuple { tuple_cat( to_tuple(std::move(node1)), to_tuple(std::move(node2)) ), std::move(errors2), newhead2 };
                    }).or_else([&]() {
                        return optional { tuple { tuple_cat( to_tuple(std::move(node1)), to_tuple(R2 { }) ), list_of(Error { (newhead1-1)->line, "Unexpected end of sequence" } ), newhead1 } };
                    });
                } else {
                    return optional { tuple { tuple_cat( to_tuple(std::move(node1)), to_tuple(R2 { }) ), std::move(errors1), newhead1 } };
                }
            });
        };
    }

    template <typename P, typename T> requires std::invocable<P, Tokens, Tokens>
    auto operator >> (P parser, T transform) {
        return [=](Tokens head, Tokens tail) {
            return invoke(parser, head, tail).transform([=](auto&& value) {
                auto&& [ node, newhead ] = value;
                if constexpr (is_tuple<std::decay_t<decltype(node)>>::value)
                     return apply (transform, node);
                else return invoke(transform, node);
            });
        };
    }

    template <typename P> requires std::invocable<P, Tokens, Tokens>
    auto many(P parser) {
        return [=](Tokens head, Tokens tail) {
            list<decay_t<decltype(get<0>(parser(head, tail).value()))>> result_list;

            for (;;) {
                auto result = invoke(parser, head, tail);
                if (!result) break;

                auto& [ node, newhead ] = result.value();
                result_list.emplace_back(std::move(node));
                head = newhead;
            }

            return !empty(result_list) ? optional { pair { std::move(result_list), head } } : nullopt;
        };
    }
    */

    template <typename P> requires std::invocable<P, Tokens, Tokens>
    auto many(P parser) {
        return [=](Tokens head, Tokens tail) {
            Parsed result { head };
            bool done;

            do {
                Parsed result2 = invoke(parser, result.newhead, tail);
                done = empty(result2.nodes) || !empty(result2.errors);
                result.nodes.splice(begin(result.nodes), result2.nodes);
                result.errors.splice(begin(result.errors), result2.errors);
                result.newhead = result2.newhead;
            } while (!done);

            return result;
        };
    }

    template <typename P1, typename P2> requires std::invocable<P1, Tokens, Tokens> && std::invocable<P2, Tokens, Tokens>
    auto operator & (P1 parser1,  P2 parser2) {
        return [=](Tokens head, Tokens tail) {
            Parsed result = invoke(parser1, head, tail);
            if (!empty(result.nodes) && empty(result.errors)) {
                Parsed result2 = invoke(parser2, result.newhead, tail);
                result.nodes.splice(begin(result.nodes), result2.nodes);
                result.errors.splice(begin(result.errors), result2.errors);
                result.newhead = result2.newhead;
            }
            return result;
        };
    }

    template <typename P1, typename P2> requires std::invocable<P1, Tokens, Tokens> && std::invocable<P2, Tokens, Tokens>
    auto operator ^ (P1 parser1, P2 parser2) {
        return [=](Tokens head, Tokens tail) {
            Parsed result = invoke(parser1, head, tail);
            if (empty(result.nodes) && empty(result.errors)) {
                return invoke(parser2, head, tail);
            }
            return result;
        };
    }

    template <typename T>
    list<T> list_of(T&& t) {
        list<T> list;
        list.emplace_back(std::move(t));
        return list;
    }



    Tokens slice_indent_section(Tokens head, Tokens tail) {
        return head == tail ? tail : find_if_not(head+1, tail, [&](tk::Token const&x){return x.line.offset > head->line.offset;});
    }

    template <typename P> requires std::invocable<P, Tokens, Tokens>
    auto block(P parser) {
        return [=](Tokens head, Tokens tail) {
            tail = slice_indent_section(head, tail);
            return invoke(parser, head, tail);
        };
    }



    auto require(tk::Kind token_kind) {
        return [=](Tokens head, Tokens tail) {
            return head != tail && head->kind == token_kind
                ? Parsed { Node { token_kind, head->line, string(head->text) }, head+1 }
                : Parsed { head };
        };
    }



    Parsed parse_expression(Tokens, Tokens);
    auto parse_term = require(tk::Kind::IDENTIFIER) ^ require(tk::Kind::INTEGER);
    auto parse_times = parse_term ^ ( parse_expression & require(tk::Kind::TIMES) & parse_expression );
    auto parse_plus = parse_times ^ ( parse_expression & require(tk::Kind::PLUS) & parse_expression );
    Parsed parse_expression(Tokens head, Tokens tail) {
        return parse_plus(head, tail);
    }

    auto parse_path = require(tk::Kind::IDENTIFIER) & many(require(tk::Kind::DOT) & require(tk::Kind::IDENTIFIER));
    auto parse_module = require(tk::Kind::IMPORT) & parse_path;
    auto parse_import = require(tk::Kind::IMPORT) & parse_path;
    auto parse_let = require(tk::Kind::LET) & require(tk::Kind::IDENTIFIER) & require(tk::Kind::EQUALS) & parse_expression;
    auto parse_ast = parse_module & many(parse_import) & many(parse_let);





    tuple<list<Node>, list<ErrorMessage>> parse(span<tk::Token const> tokens) {
        Tokens head = begin(tokens);
        Tokens tail = end(tokens);
        Tokens cursor = head;
        list<Node> nodes;
        list<ErrorMessage> errors;

        auto handle_bad_tokens = [&]() {
            if (head != cursor)
                errors.emplace_back(head->line, "Unexpected tokens");
        };

        while (cursor != tail) {
            auto result = parse_ast(cursor, tail);
            if (!empty(result.nodes) || !empty(result.errors)) {
                handle_bad_tokens();
                nodes.splice(end(nodes), result.nodes);
                errors.splice(end(errors), result.errors);
                head = cursor = result.newhead;
            } else {
                cursor ++;
            }
        }
        handle_bad_tokens();

        return tuple { std::move(nodes), std::move(errors) };
    }
};
