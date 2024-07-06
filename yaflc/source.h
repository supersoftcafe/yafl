#ifndef SOURCE_H
#define SOURCE_H

#include <algorithm>
#include <utility>
#include <cstdint>
#include <optional>
#include <string_view>


namespace yafl {



struct SourceRef {
    uint32_t line;
    uint32_t offset;
    constexpr auto operator <=> (SourceRef o) const {
        auto r = line <=> o.line;
        if (r != 0) return r;
        return offset <=> o.offset;
    }
    constexpr auto operator == (SourceRef o) const {
        return line == o.line &&  offset == o.offset;
    }
    constexpr operator bool () const {
        return line || offset;
    }
};

class Source
{
public:
    using Char = std::pair<std::optional<char>, Source>;
    using Result = std::pair<std::optional<Source>, Source>;


    constexpr Source(const char* value)
    : value_(value), filename_(""), sourceRef_{1, 1} { }

    constexpr Source(std::string_view value)
    : value_(value), filename_(""), sourceRef_{1, 1} { }

    constexpr Source(std::string_view value, SourceRef sourceRef)
    : value_(value), filename_(""), sourceRef_(sourceRef) { }

    constexpr Source(std::string_view value, uint32_t line, uint32_t offset)
    : value_(value), filename_(""), sourceRef_{line, offset} { }

    constexpr Source(std::string_view value, std::string_view filename, SourceRef sourceRef)
    : value_(value), filename_(filename), sourceRef_(sourceRef) { }

    constexpr Source(std::string_view value, std::string_view filename, uint32_t line, uint32_t offset)
    : value_(value), filename_(filename), sourceRef_{line, offset} { }

    constexpr Source(std::string_view value, std::string_view filename)
    : value_(value), filename_(filename), sourceRef_{1, 1} { }


    constexpr inline auto operator <=> (Source other) const {
        auto v = value_ <=> other.value_; if (v != 0) return v;
        auto f = filename_ <=> other.filename_; if (f != 0) return f;
        return sourceRef_ <=> other.sourceRef_;
    }

    constexpr inline auto operator == (Source other) const {
        return     value_ == other.value_
             && filename_ == other.filename_
            && sourceRef_ == other.sourceRef_;
    }

    constexpr inline auto substr(size_t index) {
        auto [ left, right ] = take(index);
        return right;
    }

    constexpr inline auto operator [] (size_t index) const {
        return value_[index];
    }

    constexpr inline auto at(size_t index) const {
        return value_.at(index);
    }

    constexpr inline std::optional<char> peek() const {
        return std::empty(value_)
            ? std::optional<char> { }
            : std::optional<char> { value_[0] };
    }

    constexpr inline Char pop() const {
        return std::empty(value_)
            ? Char { { }, *this }
            : Char { value_[0],
                Source { value_.substr(1), filename_,
                    (value_[0] == '\n' ? sourceRef_.line + 1 : sourceRef_.line),
                    (value_[0] == '\n' ? 1 : sourceRef_.offset + 1)
                } };
    }

    constexpr inline Result take(size_t count) const {
        auto substr = [this, count]() -> Result {
            auto str = value_.substr(0, count);
            uint32_t nlc = std::count(std::begin(str), std::end(str), '\n');
            uint32_t ecnt = str.find_last_of('\n');
            uint32_t size = std::size(str);
            return {
                { { str, filename_, sourceRef_ } },
                { value_.substr(count), filename_, sourceRef_.line + nlc, ecnt == (uint32_t)std::string_view::npos ? sourceRef_.offset + size : size - ecnt }
            };
        };
        return std::size(value_) < count
            ? Result { { }, *this }
            : substr();
    }

    constexpr inline Result read_line() const {
        auto index = value_.find_first_of('\n');
        auto line_length = index == std::string_view::npos ? std::size(value_) : index + 1;
        return line_length == 0
            ? Result { { }, *this }
            : Result { { { value_.substr(0, line_length), filename_, sourceRef_ } },
                { value_.substr(line_length), filename_, sourceRef_.line + 1, 1 }};
    }

    constexpr inline bool empty() const { return value_.empty(); }
    constexpr inline size_t size() const { return value_.size(); }

    constexpr inline std::string_view value() const { return value_; }
    constexpr inline std::string_view filename() const { return filename_; }
    constexpr inline SourceRef sourceRef() const { return sourceRef_; }

private:
    std::string_view value_;
    std::string_view filename_;
    SourceRef sourceRef_;;
};

constexpr inline bool empty(Source source) {
    return source.empty();
}

constexpr inline size_t size(Source source) {
    return source.size();
}




static_assert(Source { "fred", "file" }.peek() == 'f');
static_assert(Source { "fred", "file" }.pop() == Source::Char { 'f', { "red", "file", 1, 2 } } );
static_assert(Source { "\nred", "file" }.pop() == Source::Char { '\n', { "red", "file", 2, 1 } } );
static_assert(Source { "\nred", "file" }.take(1) == Source::Result { { { "\n", "file" } }, { "red", "file", 2, 1 } } );
static_assert(Source { "one\ntwo\r\nthree", "file", 1, 1 }.take(10) == Source::Result { { { "one\ntwo\r\nt", "file" } }, { "hree", "file", 3, 2 } } );
static_assert(Source { "somesuch", 2, 2}.take(4) == Source::Result { { { "some", 2, 2 } }, { "such", 2, 6 } } );

static_assert(Source { "fred" }.read_line() == Source::Result { "fred", { "", "", 2, 1 } } );
static_assert(Source { "fred\n" }.read_line() == Source::Result { "fred\n", { "", "", 2, 1 } } );
static_assert(Source { "fred\r\nbill\n", 2, 2 }.read_line() == Source::Result { { { "fred\r\n", 2, 2 } }, { "bill\n", "", 3, 1 } } );
static_assert(Source { "\nbill\n" }.read_line() == Source::Result { "\n", { "bill\n", "", 2, 1 } } );
static_assert(Source { "" }.read_line() == Source::Result { { }, { "", "", 1, 1 } } );

};


#endif // SOURCE_H
