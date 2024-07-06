
#include <ranges>
#include <cstring>
#include <algorithm>
#include <optional>
#include <span>
#include <functional>
#include <type_traits>
#include <concepts>
#include <cassert>
#include <algorithm>
#include <cctype>
#include <limits>
#include <memory>
#include <iostream>

#include "parse2.h"


namespace {
    using namespace yafl;
    using namespace std::placeholders;

    template <typename... Args, typename Result>
    constexpr auto f_to_l(Result(*f)(Args...)) {
        return [f](Args... args) -> Result {
            return f(args...);
        };
    }

    template <typename T>
    struct Parsed {
        using value_type = T;

        optional<T>           value;
        vector<ErrorMessage> errors;
        Source               source;

        constexpr Parsed(optional<T>&& v, Source s) : value(std::move(v)), source(s) { }
        constexpr Parsed(optional<T>&& v, ErrorMessage&& e, Source s) : value(std::move(v)), source(s) { errors.emplace_back(std::move(e)); }
        constexpr Parsed(optional<T>&& v, vector<ErrorMessage>&& e, Source s) : value(std::move(v)), errors(std::move(e)), source(s) { }

        constexpr bool operator == (const Parsed<T>& o) const {
            return value == o.value && errors == o.errors && source == o.source;
        }

        // Delete copy constructor and assignment operator
        Parsed(const Parsed&) = delete;
        Parsed& operator=(const Parsed&) = delete;
        Parsed(Parsed&&) = default;
    };

    template<typename P>
    using Parser_value_t = typename invoke_result_t<P, Source>::value_type;


    template <typename T>
    constexpr void move_append(vector<T>& dst, vector<T>& src) {
        if (dst.empty()) {
            std::swap(dst, src);
        } else {
            dst.reserve(dst.size() + src.size());
            std::move(std::begin(src), std::end(src), std::back_inserter(dst));
            src.clear();
        }
    }

    template <typename X>
    auto constexpr vector_of(X&& x) {
        vector<X> v;
        v.emplace_back(std::move(x));
        return std::move(v);
    }
    template <typename X>
    auto constexpr vector_of(X&& x, X&& y) {
        vector<X> v;
        v.emplace_back(std::move(x));
        v.emplace_back(std::move(y));
        return std::move(v);
    }



    // Type trait to check if a type is a std::tuple
    template<typename T>
    struct is_tuple : std::false_type {};

    template<typename... T>
    struct is_tuple<std::tuple<T...>> : std::true_type {};

    // Helper function to convert a value to a tuple if it's not already one
    template<typename T>
    auto constexpr to_tuple(T&& value) {
        if constexpr (is_tuple<std::decay_t<T>>::value) {
            return std::forward<T>(value);
        } else {
            return std::make_tuple(std::forward<T>(value));
        }
    }
    static_assert(to_tuple(1) == tuple<int> { 1 });
    static_assert(tuple_cat( tuple<int> { 1 }, tuple<double> { 1.1 } ) == tuple<int, double> { 1, 1.1 });
    static_assert(tuple_cat( to_tuple(1), to_tuple(1.1)) == tuple<int, double> { 1, 1.1 });
    static_assert(tuple_cat( to_tuple(1), to_tuple(tuple<double> { 1.1 })) == tuple<int, double> { 1, 1.1 });



    constexpr bool ckd_add(uint64_t* result, uint64_t a, uint64_t b) {
        if (std::numeric_limits<uint64_t>::max() - a < b)
            return true;
        *result = a + b;
        return false;
    }

    constexpr bool ckd_mul(uint64_t* result, uint64_t a, uint64_t b) {
        uint64_t r = a * b;
        if (a != 0 && r / b != a)
            return true;
        *result = r;
        return false;
    }



    auto constexpr nothing() {
        return [](Source source) -> Parsed<int> {
            return { { }, { }, source };
        };
    }
    constexpr auto is_sign = [](char chr) {
        return chr == '+' || chr == '-';
    };
    constexpr auto is_space = [](char chr) {
        return chr == ' ' || chr == '\f' || chr == '\t' || chr == '\v' || chr == '\n' || chr == '\r';
    };
    constexpr auto is_decimal = [](char chr) {
        return chr >= '0' && chr <= '9';
    };
    constexpr auto is_alpha = [](char chr) {
        return (chr >= 'A' && chr <= 'Z') || (chr >= 'a' && chr <= 'z') || chr == '_';
    };
    constexpr auto is_literal = [](char chr) {
        return (chr >= 'A' && chr <= 'Z') || (chr >= 'a' && chr <= 'z')  || ( chr >= '0' && chr <= '9' ) || chr == '_';
    };



    constexpr bool is_equal(const Parsed<Declaration::ptr>& a, const Parsed<Declaration::ptr>& b) {
        return ((!a.value && !b.value) || (a.value && b.value && is_equal(*a.value, *b.value)))
            && a.errors == b.errors
            && a.source == b.source;
    }
    constexpr bool is_equal(const Parsed<vector<Declaration::ptr>>& a, const Parsed<vector<Declaration::ptr>>& b) {
        return ((!a.value && !b.value) || (a.value && b.value && is_equal(*a.value, *b.value)))
            && a.errors == b.errors
            && a.source == b.source;
    }
    constexpr bool is_equal(const Parsed<Expression::ptr>& a, const Parsed<Expression::ptr>& b) {
        return ((!a.value && !b.value) || (a.value && b.value && is_equal(*a.value, *b.value)))
            && a.errors == b.errors
            && a.source == b.source;
    }



    constexpr bool eol(Source s) {
        auto v = s.peek();
        return !v || v == '\n';
    }
    static_assert(eol(  "") == true);
    static_assert(eol("\n") == true);
    static_assert(eol("nn") == false);





    constexpr Source skip_space(Source value) {
        size_t index = 0;
        while (index < size(value) && is_space(value[index]))
            index++;
        return value.substr(index);
    }
    static_assert(skip_space("abc") == "abc");
    static_assert(skip_space(" abc") == Source { "abc", { }, 1, 2 });
    static_assert(skip_space("  \n  \r\tabc") == Source { "abc", { }, 2, 5 });


    template <typename P> requires std::invocable<P, char>
    auto constexpr if_char(P predicate) {
        return [=](Source value) -> Parsed<char> {
            auto [ left, right ] = value.pop();
            if (left && std::invoke(predicate, *left))
                return { { *left }, { }, right };
            return { { }, { }, value };
        };
    }
    auto constexpr if_char(string_view predicate) {
        return if_char([=](char c){return predicate.contains(c);});
    }
    auto constexpr if_char(char predicate) {
        return if_char([=](char c){return predicate == c;});
    }
    static_assert(if_char("abc")("fred") == Parsed<char> { { }, { }, Source { "fred", 1, 1 } } );
    static_assert(if_char("abc")("bert") == Parsed<char> { 'b', { }, Source { "ert", 1, 2 } } );



    template <typename P> requires std::invocable<P, char>
    auto constexpr while_char(P predicate) {
        return [=](Source value) -> Parsed<string_view> {
            size_t index = 0;
            while (index < size(value) && predicate(value[index])) index++;
            if (index == 0) return { { }, { }, value };
            auto [ left, right ] = value.take(index);
            return { left->value(), { }, right };
        };
    }
    auto constexpr while_char(string_view predicate) {
        return while_char([=](char c){return predicate.contains(c);});
    }
    auto constexpr while_char(char predicate) {
        return while_char([=](char c){return predicate == c;});
    }
    static_assert(while_char(is_space)(" \t\nfred") == Parsed<string_view> { " \t\n", { }, { "fred", 2, 1 }});
    static_assert(while_char(is_literal)("this28:") == Parsed<string_view> { "this28", { }, { ":", 1, 7 }});



    template <typename P> requires std::invocable<P, Source>
    auto constexpr many(P parser) {
        using Vec = vector<Parser_value_t<P>>;
        return [=](Source source) -> Parsed<Vec>  {
            vector<ErrorMessage> result_errors { };
            for (Vec result_values { };;) {
                auto [ result, error, remainder ] = invoke(parser, source);
                move_append(result_errors, error);
                source = remainder;
                if (!result)
                    return { { std::move(result_values) }, std::move(result_errors), source };
                result_values.emplace_back(std::move(*result));
            }
        };
    }
    static_assert(many(if_char('a'))("") == Parsed<vector<char>>{{vector<char>{}}, { }, {"", 1, 1}});
    static_assert(many(if_char('a'))("a") == Parsed<vector<char>>{{vector<char>{'a'}}, { }, {"", 1, 2}});
    static_assert(many(if_char('a'))("aa") == Parsed<vector<char>>{{vector<char>{'a', 'a'}}, { }, {"", 1, 3}});
    static_assert(many(if_char('a'))("aab") == Parsed<vector<char>>{{vector<char>{'a', 'a'}}, { }, {"b", 1, 3}});



    template <typename P> requires std::invocable<P, Source>
    auto constexpr maybe(P parser) {
        return [=](Source source) -> Parsed<optional<Parser_value_t<P>>> {
            auto [ result, error, remainder ] = invoke(parser, source);
            if (!empty(error))
                return { { }, std::move(error), remainder };
            return { { result }, std::move(error), remainder };
        };
    }

    template <typename P> requires std::invocable<P, Source>
    auto constexpr require(P parser) {
        return [=](Source source) -> Parsed<Parser_value_t<P>> {
            auto [ result, error, remainder ] = invoke(parser, source);
            if (!empty(error))
                return { { }, std::move(error), remainder };
            if (!result)
                return { { }, { source, "unexpected characters" }, remainder };
            return { std::move(result), std::move(error), remainder };
        };
    }
    static_assert(require(if_char("a"))("a") == Parsed<char>{ {'a'}, { }, {"", 1, 2}});
    static_assert(require(if_char("a"))("z") == Parsed<char>{ { }, { { 1, 1 }, "unexpected characters" }, {"z", 1, 1}});



    template <typename V>
    auto constexpr unit(V v) {
        return [v](Source value) -> Parsed<V> {
            return { { v }, { }, value };
        };
    }



    template <typename P1, typename P2> requires invocable<P1, Source> && invocable<P2, Source>
    auto constexpr iff(P1 parser1, P2 parser2) {
        return [=](Source value) -> Parsed<Parser_value_t<P2>> {
            auto r = invoke(parser1, value);
            if (!r.value || !empty(r.errors))
                return { { }, std::move(r.errors), value }; // First test failed so don't return anything
            return parser2(value); // Reset source stream and go with second parser
        };
    }
    static_assert(iff(if_char("abc"), unit(1))("abc") == Parsed<int>{ 1, { }, "abc"});
    static_assert(iff(if_char("abc"), unit(1))("xyz") == Parsed<int>{ { }, { }, "xyz"});



    template <typename P1, typename P2> requires invocable<P1, Source> && invocable<P2, Source>
    auto constexpr operator & (P1 parser1, P2 parser2) {
        using R1 = Parser_value_t<P1>;
        using R2 = Parser_value_t<P2>;
        using Tup = typeof(tuple_cat(to_tuple(R1 { }), to_tuple(R2 { })));
        return [=](Source source) -> Parsed<Tup> {
            auto r1 = invoke(parser1, source);
            if (!r1.value)
                return { { }, std::move(r1.errors), source };

            auto r2 = invoke(parser2, r1.source);
            move_append(r1.errors, r2.errors);
            if (!r2.value)
                return { { }, std::move(r1.errors), source };

            return { { tuple_cat(to_tuple(std::move(*r1.value)), to_tuple(std::move(*r2.value))) }, { }, r2.source };
        };
    }
    static_assert((if_char("abc") & if_char("xyz"))("ttt")
        == Parsed<tuple<char, char>> { { }, { }, "ttt" } );
    static_assert((if_char("abc") & if_char("xyz"))("att")
        == Parsed<tuple<char, char>> { { }, { }, { "att", 1, 1 } } );
    static_assert((if_char("abc") & if_char("xyz"))("azt")
        == Parsed<tuple<char, char>> { { { 'a', 'z' } }, { }, Source { "t", 1, 3 } } );
    static_assert((if_char("abc") & if_char("xyz") & if_char("abc"))("azbt")
        == Parsed<tuple<char, char, char>> { { { 'a', 'z', 'b' } }, { }, Source { "t", 1, 4 } } );



    template <typename P1, typename P2> requires invocable<P1, Source> && invocable<P2, Source>
    // P1 and P2 must have the same return type
    auto constexpr operator ^ (P1 parser1, P2 parser2) {
        return [=](Source source) -> invoke_result_t<P1, Source> {
            auto r1 = invoke(parser1, source);
            if (r1.value) return r1;
            auto r2 = invoke(parser2, source);
            if (r2.value) return r2;
            if (!empty(r1.errors)) return r1;
            return r2;
        };
    }
    static_assert((if_char("abc") ^ if_char("xyz"))("bert") == Parsed<char> { 'b', { }, Source { "ert", 1, 2 } } );
    static_assert((if_char("abc") ^ if_char("xyz"))("zara") == Parsed<char> { 'z', { }, Source { "ara", 1, 2 } } );
    static_assert((if_char("abc") ^ if_char("xyz"))("fred") == Parsed<char> { { }, { }, Source { "fred" } } );



    template <typename P1, typename P2> requires std::invocable<P1, Source> && std::invocable<P2, Parser_value_t<P1>, Source>
    auto constexpr operator | (P1 parser, P2 transformer) {
        return [=](Source source) -> std::invoke_result_t<P2, Parser_value_t<P1>, Source> {
            auto result = std::invoke(parser, source);
            if (!result.value)
                return { { }, std::move(result.errors), result.source };
            return std::invoke(transformer, std::move(*result.value), result.source);
        };
    }
    template <typename R1, typename A1, typename P2> requires std::invocable<P2, R1>
    auto constexpr operator | (R1(*parser)(A1), P2 transformer) {
        return [=](Source source) -> std::invoke_result_t<P2, R1> {
            auto result = std::invoke(parser, source);
            if (!result.value)
                return { { }, result.error, result.source };
            return std::invoke(transformer, result);
        };
    }
    template<typename T>constexpr Parsed<string> to_string(const T&v, const Source&s){return{string{v},{},s};}
    static_assert((if_char("abc") | to_string<char>)("bert") == Parsed<string> { "b", { }, { "ert", 1, 2}  } );



    size_t constexpr count_space(Source value, size_t acc = 0) {
        auto [ left, right ] = value.pop();
        return is_space(left.value_or('\0')) ? count_space(right, acc + 1) : acc;
    }
    static_assert(count_space("    ") == 4);
    static_assert(count_space("    fred") == 4);
    static_assert(count_space("") == 0);



#define DISCARD     [](auto v,auto s)->Parsed<tuple<>>{return {tuple<>{},{},s};}


    auto constexpr         WS  =   maybe(while_char(is_space))                                       | DISCARD;
    auto constexpr REQUIRE_EOL = require(maybe(while_char(" \f\t\v\r")) & require(while_char('\n'))) | DISCARD;

    static_assert(REQUIRE_EOL("\n") == Parsed<tuple<>> { tuple<>{}, { }, {"", 2, 1}} );
    static_assert(REQUIRE_EOL("  \t\n") == Parsed<tuple<>> { tuple<>{}, { }, {"", 2, 1}} );
    static_assert(REQUIRE_EOL("  \t") == Parsed<tuple<>> { optional<tuple<>>{}, { { 1, 4}, "unexpected characters" }, "  \t"} );


    /* Get a line plus all following lines that are indented further.
     * Lines with only whitespace are skipped.
     * The result is an exact prefix of the original string so the length can be used for calling substr.
     */
    size_t constexpr count_chars_in_block_(Source value, size_t indent, size_t count) {
        auto [ left, right ] = value.read_line();
        if (left) {
            auto line = *left;
            auto line_indent = count_space(line);
            if (line_indent > indent || line_indent == size(line))
                return count_chars_in_block_(right, indent, count + size(line));
        }
        return count;
    }
    Source::Result constexpr read_block(Source value) {
        auto [ left, right ] = value.read_line();
        if (!left) return { left, right };
        auto left_value = left.value();

        auto indent = count_space(left_value);
        if (indent == size(left_value))
            return read_block(right);

        return value.take(count_chars_in_block_(right, indent, size(left_value)));
    }

    // There's nothing
    static_assert(read_block("") == Source::Result { { }, "" });

    // Just one line
    static_assert(read_block("fred\n")
        == Source::Result { "fred\n", { "", "", 2, 1 } } );

    // Block is only the first line
    static_assert(read_block("fred\nbill\n")
        == Source::Result { "fred\n", { "bill\n", "", 2, 1 } } );

    // Block is first and second lines only
    static_assert(read_block("fred\n bill\nend")
        == Source::Result { "fred\n bill\n", {"end", "", 3, 1 } } );

    // Skip blank line and then cut out the block
    static_assert(read_block("    \n  start\n    indent\n")
        == Source::Result { { { "  start\n    indent\n", "", 2, 1 } }, { "", "", 4, 1 } } );

    static_assert(read_block("  fred\r\n  end\r\n")
        == Source::Result { "  fred\r\n", { "  end\r\n", 2, 1 } } );

    static_assert(read_block("  fred\r\n   bill\r\n     more\r\n")
        == Source::Result { "  fred\r\n   bill\r\n     more\r\n", { "", 4, 1 } } );

    static_assert(read_block("  fred\r\n   bill\r\n     more\r\n  end")
        == Source::Result { "  fred\r\n   bill\r\n     more\r\n", { "  end", 4, 1 } } );



    constexpr Parsed<char> parse_string_char(Source value) {
        auto [ left, right ] = value.pop();

        if (left && !eol(value)) {
            auto chr = *left;

            if (chr == '\\') {
                auto [ left2, right2 ] = right.pop();
                if (!left2 || eol(value)) {
                    return Parsed<char> { { }, { right, "missing escape character" }, right };
                }

                switch (chr = *left2) {
                    case  'n': chr = '\n'; break;
                    case  'r': chr = '\r'; break;
                    case  't': chr = '\t'; break;
                    case '\\': chr = '\\'; break;
                    default: return { { }, { right, "illegal escape character" }, right2 };
                }

                return { chr, { }, right2 };
            } else {
                return { chr, { }, right };
            }
        }

        return { { }, { }, value };
    }
    static_assert(parse_string_char("") == Parsed<char> { { }, { }, { "", 1, 1 } });
    static_assert(parse_string_char("xy") == Parsed<char> { 'x', { }, { "y", 1, 2 } });
    static_assert(parse_string_char("\n") == Parsed<char> { { }, { }, "\n" });
    static_assert(parse_string_char("\\n") == Parsed<char> { '\n', { }, { "", 1, 3 } } );
    static_assert(parse_string_char("\\") == Parsed<char> { { }, { {1, 2}, "missing escape character" }, { "", 1, 2 } } );
    static_assert(parse_string_char("\\x") == Parsed<char> { { }, { {1, 2}, "illegal escape character" }, { "", 1, 3 } } );



    constexpr Parsed<string> parse_string(Source source) {
        if (eol(source) || source[0] != '\"')
            return { { }, { }, source };
        source = source.substr(1);
        string result = "";

        while (!eol(source)) {
            if (source[0] == '\"')
                return { result, { }, source.substr(1) };

            auto [chr, errors, remainder] = parse_string_char(source);
            source = remainder;

            if (!empty(errors))
                return { { }, std::move(errors), source };
            else if (!chr)
                break; // unterminated

            result += chr.value();
        }

        return { { }, { source, "unterminated string" }, source };
    }
    static_assert(parse_string("\"abc\"")
        == Parsed<string> { "abc", { }, { "", 1, 6 } } );
    static_assert(parse_string("\"abc\n\"")
        == Parsed<string> { { }, { {1, 5}, "unterminated string" }, { "\n\"", 1, 5 } } );


    constexpr auto parse_sign_string = if_char(is_sign);
    constexpr auto parse_literal_string = iff(if_char(is_decimal), while_char(is_literal));
    constexpr auto parse_numeric_string = iff(if_char(is_decimal), while_char(is_literal));




    constexpr Parsed<string_view> parse_identifier(Source value) {
        if (empty(value))
            return Parsed<string_view> { { }, { }, value };

        auto chr = value[0];
        if ((chr < 'A' || chr > 'Z') && (chr < 'a' || chr > 'z') && chr != '_')
            return Parsed<string_view> { { }, { }, value };

        size_t index = 1;
        while (index < size(value)) {
            chr = value[index];
            if (!is_literal(chr))
                break;
            index++;
        }

        auto [ left, right ] = value.take(index);
        return Parsed<string_view> { left.transform([](auto x){return x.value();}), { }, right };
    }
    static_assert(parse_identifier("abc") == Parsed<string_view> { "abc", { }, { "", 1, 4 } } );
    static_assert(parse_identifier("a12") == Parsed<string_view> { "a12", { }, { "", 1, 4 } } );
    static_assert(parse_identifier("012") == Parsed<string_view> { { }, { }, "012" } );
    static_assert(parse_identifier("a12_") == Parsed<string_view> { "a12_", { }, { "", 1, 5 } } );
    static_assert(parse_identifier("a12_&") == Parsed<string_view> { "a12_", { }, { "&", 1, 5 } } );
    static_assert(parse_identifier("abc\nfre") == Parsed<string_view> { "abc", { }, { "\nfre", 1, 4 } } );



    constexpr auto keyword(string_view name) {
        return parse_identifier | [=](string_view identifier, Source source) -> Parsed<string_view> {
            if (identifier == name) {
                return Parsed<string_view> { name, { }, source };
            } else {
                return Parsed<string_view> { { }, { source, "expected identifier" }, source };
            }
        };
    }

    template <typename P> requires invocable<P, Source>
    constexpr auto block(P parser) {
        return [=](Source source) -> Parsed<Parser_value_t<P>> {
            auto [ contents, block_tail ] = read_block(source);
            if (!contents)
                return { { }, { }, block_tail };
            auto [ result, errors, parser_tail ] = invoke(parser, *contents);
            auto [ _a, _b, ws_tail ] = WS(parser_tail);
            if (ws_tail != block_tail)
                errors.emplace_back(ws_tail, "excess characters found");
            return { std::move(result), std::move(errors), block_tail };
        };
    }


    constexpr auto ast_integer = maybe(if_char(is_sign)) & maybe(WS) & parse_numeric_string | [](auto values, Source src) -> Parsed<Expression::ptr> {
        auto [sign_char, white_space, str] = values;

        auto [base, triml]
            = str.starts_with("0x") ? tuple { 16, 2} :
              str.starts_with("0o") ? tuple {  8, 2} :
              str.starts_with("0b") ? tuple {  2, 2} : tuple { 10, 0};
        str.remove_prefix(triml);

        auto [size, trimr]
            = str.ends_with("i64") ? tuple { 64, 3} :
              str.ends_with("i32") ? tuple { 32, 3} :
              str.ends_with("i16") ? tuple { 16, 3} :
              str.ends_with( "i8") ? tuple {  8, 2} : tuple { 32, 0};
        str.remove_suffix(trimr);

        uint64_t unsigned64_value = 0;
        bool no_digits = true;
        for (auto chr : str) {
            if (chr != '_') {
                no_digits = false;
                uint_fast8_t value
                    = chr >= '0' && chr <= '9' ? chr - '0' :
                      chr >= 'a' && chr <= 'z' ? chr - 'a' + 10 :
                      chr >= 'A' && chr <= 'Z' ? chr - 'A' + 10 : 37;
                if (value >= base)
                    return { { }, { src, "invalid numeric literal" }, src };

                // Does it unsigned overflow when we add the new digit
                if (ckd_mul(&unsigned64_value, unsigned64_value, base) || ckd_add(&unsigned64_value, unsigned64_value, value))
                    return { { }, { src, "overflow" }, src };
            }
        }
        if (no_digits)
            return { { }, { src, "invalid numeric literal" }, src};

        if (sign_char && *sign_char == '-') {
            unsigned64_value = 0ULL - unsigned64_value;
            if ((unsigned64_value & (1ULL << (size-1))) == 0 && (unsigned64_value & ((1ULL << size) - 1)) != 0) // signed32_value > 0
                return { { }, { src, "overflow" }, src };
        } else if (base == 10) {
            if ((unsigned64_value & (1ULL << (size-1))) != 0) // signed32_value < 0
                return { { }, { src, "overflow" }, src };
        } else {
            if (unsigned64_value >> size != 0)
                return { { }, { src, "overflow" }, src };
        }

        // Sign extension
        int64_t signed64_value = (int64_t)unsigned64_value;
        if (size != 64)
            signed64_value = (signed64_value << (64 - size)) >> (64 - size);

        return { Integer::create(signed64_value, size), { }, src};
    };
    static_assert(is_equal(ast_integer("abc"), Parsed<Expression::ptr> { { }, { }, "abc"}));
    static_assert(is_equal(ast_integer("123"), Parsed<Expression::ptr> { Integer::create(123, 32), { }, { "", 1, 4 }}));
    static_assert(is_equal(ast_integer("-123"), Parsed<Expression::ptr> { Integer::create(-123, 32), { }, { "", 1, 5 }}));
    static_assert(is_equal(ast_integer("-  123"), Parsed<Expression::ptr> { Integer::create(-123, 32), { }, { "", 1, 7 }}));
    static_assert(is_equal(ast_integer("-  123zz"), Parsed<Expression::ptr> { { }, { { 1, 9 }, "invalid numeric literal" }, { "", 1, 9 }}));
    static_assert(is_equal(ast_integer("0x7fi8"), Parsed<Expression::ptr> { Integer::create(127, 8), { }, { "", 1, 7}}));
    static_assert(is_equal(ast_integer("0xffi8"), Parsed<Expression::ptr> { Integer::create(-1, 8), { }, { "", 1, 7}}));
    static_assert(is_equal(ast_integer("0x1ffi8"), Parsed<Expression::ptr> { { }, { { 1, 8 }, "overflow" }, { "", 1, 8}}));
    static_assert(is_equal(ast_integer("-0xffi8"), Parsed<Expression::ptr> { { }, { { 1, 8 }, "overflow" }, { "", 1, 8}}));



    constexpr auto ast_string = parse_string | [](auto str,Source src){return Parsed<Expression::ptr>{String::create(str),{},src};};
    static_assert(is_equal(
        ast_string("\"fred\""),
        {String::create("fred"), { }, {"", 1, 7}}
    ));



    constexpr Parsed<Expression::ptr> ast_expression(Source source) {
        auto fold_operators = [](auto e, auto s) -> Parsed<Expression::ptr> {
            return {{ranges::fold_left(get<1>(e), std::move(get<0>(e)), [](auto&&l, auto&&r){
                return BinaryOp::create(std::move(l), get<0>(r), std::move(get<1>(r)));
            })},{},s};
        };
        auto remove_brackets = [](auto e, auto s) -> Parsed<Expression::ptr> {
            return {{std::move(get<1>(e))},{},s};
        };

        auto terminal = ast_integer ^ ast_string;
        auto brackets = if_char('(') & WS & ast_expression & WS & if_char(')')  | remove_brackets;
        auto factor   = terminal ^ brackets;
        auto term     = factor & many( WS & if_char("*/%") & WS & factor )      | fold_operators;
        auto expr     = term   & many( WS & if_char("+-" ) & WS & term   )      | fold_operators;

        return expr(source);
    }

    static_assert(is_equal(
        ast_expression("\"fred\""),
        {String::create("fred"), { }, {"", 1, 7}}
    ));
    static_assert(is_equal(
        ast_expression("27"),
        {Integer::create(27, 32), { }, {"", 1, 3}}
    ));
    static_assert(is_equal(
        ast_expression("(27)"),
        {Integer::create(27, 32), { }, {"", 1, 5}}
    ));
    static_assert(is_equal(
        ast_expression("27*10"),
        {BinaryOp::create(Integer::create(27,32),'*',Integer::create(10,32)), { }, {"", 1, 6}}
    ));
    static_assert(is_equal(
        ast_expression("27 * 10"),
        {BinaryOp::create(Integer::create(27,32),'*',Integer::create(10,32)), { }, {"", 1, 8}}
    ));
    static_assert(is_equal(
        ast_expression("0xf + -1"),
        {BinaryOp::create(Integer::create(15,32),'+',Integer::create(-1,32)), { }, {"", 1, 9}}
    ));
    static_assert(is_equal(
        ast_expression("3\n--4"),
        {BinaryOp::create(Integer::create(3,32), '-', Integer::create(-4,32)), { }, {"", 2, 4}}
    ));
    static_assert(is_equal(
        ast_expression("(3-4)"),
        {BinaryOp::create(Integer::create(3,32), '-', Integer::create(4,32)), { }, {"", 1, 6}}
    ));
    static_assert(is_equal(
        ast_expression("3\n--4*5"),
        {BinaryOp::create(Integer::create(3,32), '-', BinaryOp::create(Integer::create(-4,32),'*',Integer::create(5,32))), { }, {"", 2, 6}}
    ));
    static_assert(is_equal(
        ast_expression("(3\n--4*5)"),
        {BinaryOp::create(Integer::create(3,32), '-', BinaryOp::create(Integer::create(-4,32),'*',Integer::create(5,32))), { }, {"", 2, 7}}
    ));
    static_assert(is_equal(
        ast_expression("3\n-(-4*5)"),
        {BinaryOp::create(Integer::create(3,32), '-', BinaryOp::create(Integer::create(-4,32),'*',Integer::create(5,32))), { }, {"", 2, 8}}
    ));
    static_assert(is_equal(
        ast_expression("3\n*(-4-5)"),
        {BinaryOp::create(Integer::create(3,32), '*', BinaryOp::create(Integer::create(-4,32),'-',Integer::create(5,32))), { }, {"", 2, 8}}
    ));
    static_assert(is_equal(
        ast_expression("1 + 2 *\n 3 --4"),
        {BinaryOp::create(BinaryOp::create(Integer::create(1,32), '+', BinaryOp::create(Integer::create(2,32), '*', Integer::create(3,32))), '-', Integer::create(-4,32)), { }, {"", 2, 7}}
    ));



    constexpr Parsed<vector<Declaration::ptr>> ast_declarations(Source source) {
        auto let_to_value = [](auto value, Source source) -> Parsed<Declaration::ptr> {
            return {{Value::create(string(get<1>(value)), std::move(get<3>(value)))}, {}, source};
        };
        auto fun_to_value = [](auto value, Source source) -> Parsed<Declaration::ptr> {
            return {{Value::create(string(get<1>(value)), Lambda::create(std::move(get<2>(value))))}, {}, source};
        };

        auto let = block(WS & keyword("let") & WS & parse_identifier & WS & if_char('=') & WS & ast_expression & REQUIRE_EOL) | let_to_value;
        auto fun = block(WS & keyword("fun") & WS & parse_identifier & REQUIRE_EOL & ast_declarations)                        | fun_to_value;

        auto declaration  = let ^ fun;
        auto declarations = many(declaration);

        return declarations(source);
    }


    static_assert(is_equal(
        ast_declarations("let a =     1i16\n"),
        { { vector_of(Value::create("a", Integer::create(1,16))) }, { }, {"", 2, 1}}
    ));

    static_assert(is_equal(
        ast_declarations(
            "fun xx\r\n"
            "  let z = 20  \n"
            "let x = 1\n"
        ),
        { { vector_of(
            Value::create("xx", Lambda::create(vector_of(Value::create("z", Integer::create(20,32))))),
            Value::create("x", Integer::create(1,32))
        ) }, { }, {"", 4, 1}}
    ));


};


namespace yafl {


    void run_tests() {
        auto x = ast_declarations(
            "fun xx\r\n"
            "  let z = 20  \n"
            "let x = 1\n"
        );
        if (x.value)
            cout << *x.value << endl;
        int y = 1;
    }


    tuple<vector<Declaration::ptr>, vector<ErrorMessage>> constexpr parse(Source s) {
        return tuple<vector<Declaration::ptr>, vector<ErrorMessage>> { vector<Declaration::ptr> { }, vector<ErrorMessage> { } };
    }
};

