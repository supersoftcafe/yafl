
#include <cstdint>
#include <vector>
#include <iostream>
#include <string_view>
#include <fstream>
#include <format>
#include <regex>
#include <filesystem>
#include <string>
#include <streambuf>
#include <optional>
#include <tuple>
#include <span>

#include "tokenizer.h"

using namespace std;



struct Node {
    Kind          kind;
    size_t line_indent;
    SourceRef    start;
    SourceRef      end;
    vector<Node> nodes;
};


span<Node> trim_span_by_indent(const span<Node> s) {
    auto indent = s.begin()->line_indent;
    auto found = ranges::find_if(s, [&](const Node& n) { return n.line_indent < indent; });
    return {s.begin(), found};
}

struct NodeParse {
    const span<Node> nodes_span;

    explicit NodeParse(const span<Node> nodes_span) : nodes_span(trim_span_by_indent(nodes_span)) {

    }

    optional<tuple<Node, ptrdiff_t>> parse_import() {
        if (nodes_span.size() < 2)
            return nullopt;

        auto& tk_import = nodes_span[0];
        auto& identifier = nodes_span[1];

        if (tk_import.kind != Kind::TK_IMPORT || identifier.kind != Kind::IDENTIFIER)
            return nullopt;

        return tuple {
            Node{Kind::IMPORT, tk_import.line_indent, tk_import.start, identifier.end, { identifier }},
            2
        };
    }

    optional<tuple<Node, ptrdiff_t>> parse_module() {
        if (nodes_span.size() < 2)
            return nullopt;

        auto& tk_module = nodes_span[0];
        auto& identifier = nodes_span[1];

        if (tk_module.kind != Kind::TK_MODULE || identifier.kind != Kind::IDENTIFIER)
            return nullopt;

        return tuple {
                Node{Kind::MODULE, tk_module.line_indent, tk_module.start, identifier.end, { identifier }},
                2
        };
    }

    optional<tuple<Node, ptrdiff_t>> parse_literal() {

    }

    optional<tuple<Node, ptrdiff_t>> parse_muldiv() {

    }

    optional<tuple<Node, ptrdiff_t>> parse_addsub() {

    }

    optional<tuple<Node, ptrdiff_t>> parse_let() {
        if (nodes_span.size() < 4)
            return nullopt;

        auto& tk_let = nodes_span[0];
        auto& identifier = nodes_span[1];
        auto& tk_equals = nodes_span[2];

        if (tk_let.kind != Kind::TK_LET || identifier.kind != Kind::IDENTIFIER || tk_equals.kind != Kind::TK_EQUALS)
            return nullopt;


        return true;
    }

    optional<tuple<Node, ptrdiff_t>> parse() {
        auto o = parse_import()
         .or_else([&]() { return parse_module(); })
         .or_else([&]() { return parse_let(); });
    }
};





string read_file(const filesystem::path& filename) {
    ifstream stream { filename };
    return {istreambuf_iterator<char>(stream), istreambuf_iterator<char>()};
}

int main() {
    vector<Node> nodes;

    cerr << std::filesystem::current_path() << endl;

    ifstream file_in("../yaflc/examples/test.yafl");

    size_t line_no = 0;
    for (string line; getline(file_in, line); ) {
        line_no += 1;
        size_t line_indent = line.find_first_not_of(' ');
        lines.emplace_back(std::move(line), line_indent);
        tokenize_string(line_no, line_indent, lines.back().text, nodes);
    }

    for (bool keep_going = true; keep_going; ) {
        keep_going = false;
        for (int index = (int)nodes.size(); --index >= 0; ) {
            auto nodes_span = span<Node>(nodes).subspan(index);
            auto result = NodeParse(nodes_span).parse();

            if (result.has_value()) {
                auto& [node, count] = result.value();
                keep_going = true;

                auto begin = nodes.begin() + index;
                *begin = std::move(node);
                nodes.erase(begin + 1, begin + count);
            }
        }
    }

    if (!errors.empty()) {
        for (const string &error : errors) {
            cout << error << endl;
        }
        return 1;
    }

    return 0;
}
