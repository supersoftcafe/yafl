//
// Created by mbrown on 09/04/24.
//

#include "parser.h"
#include <algorithm>
#include <optional>
#include <span>
#include <functional>
#include <type_traits>
#include <cassert>

namespace ps {
    using namespace std::placeholders;

    using Tokens = span<tk::Token const>::iterator;

    template <typename T>
    using Parsed = optional<pair<T, Tokens>>;





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

    template <typename P1, typename P2> requires std::invocable<P1, Tokens, Tokens> && std::invocable<P2, Tokens, Tokens>
    auto operator | (P1 parser1, P2 parser2) {
        return [=](Tokens head, Tokens tail) {
            return invoke(parser1, head, tail).or_else([=]() {
                return invoke(parser2, head, tail);
            });
        };
    }

    template <typename P1, typename P2> requires std::invocable<P1, Tokens, Tokens> && std::invocable<P2, Tokens, Tokens>
    auto operator & (P1 parser1, P2 parser2) {
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



    bool slice_indent_section(Tokens head, Tokens& tail, tk::Kind token_kind) {
        if (head == tail || head->kind != token_kind) return false;
        tail = find_if_not(head+1, tail, [&](tk::Token const&x){return x.line.offset > head->line.offset;});
        return head != tail;
    }

    template <typename T>
    list<T> list_of(T&& t) {
        list<T> list;
        list.emplace_back(std::move(t));
        return list;
    }

    Parsed<Node> parse_node_and_identifier_path(Tokens head, Tokens tail, tk::Kind token_kind, Kind ast_kind) {
        if (!slice_indent_section(head, tail, token_kind) || head->kind != token_kind)
            return nullopt;

        auto next = head;
        list<Node> identifiers;
        do {
            if (++next == tail || next->kind != tk::Kind::IDENTIFIER) {
                identifiers.emplace_back(Kind::IDENTIFIER, (next-1)->line, "Missing identifier on module statement");
                break;
            } else {
                identifiers.emplace_back(Kind::IDENTIFIER, next->line, "", next->text);
            }
        } while (++next != tail && next->kind == tk::Kind::DOT);

        return { { Node { ast_kind, head->line, "", std::move(identifiers) }, tail } };
    };

    auto parse_module = bind(parse_node_and_identifier_path, _1, _2, tk::Kind::MODULE, Kind::MODULE);
    auto parse_import = bind(parse_node_and_identifier_path, _1, _2, tk::Kind::IMPORT, Kind::IMPORT);
    auto parse_statement = parse_module | parse_import;
    auto mamamam = many(parse_module);




    list<Node> parse(span<tk::Token const> tokens) {
        Tokens head = begin(tokens);
        Tokens tail = end(tokens);
        Tokens cursor = head;
        list<Node> nodes;

        auto handle_bad_tokens = [&]() {
            if (head != cursor)
                nodes.emplace_back(Kind::UNEXPECTED, head->line, "Unexpected tokens");
        };

        while (cursor != tail) {
            auto result = parse_statement(cursor, tail);
            if (result.has_value()) {
                handle_bad_tokens();
                auto& [ node, newhead ] = result.value();
                nodes.emplace_back(std::move(node));
                head = cursor = newhead;
            } else {
                cursor ++;
            }
        }
        handle_bad_tokens();

        return nodes;
    }
};
