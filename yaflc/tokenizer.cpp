//
// Created by mbrown on 09/04/24.
//

#include "tokenizer.h"
#include <tuple>
#include <regex>

using namespace std;

namespace tk {
    static tuple<Kind, regex> rules[] ={
            { WHITESPACE, regex {R"( +)"} },
            { MODULE, regex {R"(module)"} },
            { IMPORT, regex {R"(import)"} },
            { LET, regex {R"(let)"} },
            { EQUALS, regex {R"(=)"} },
            { IDENTIFIER, regex {R"rx([a-zA-Z_][a-zA-Z_0-9]*)rx"} },
            { COMMENT, regex {R"rx(#.*)rx"} },
    };

    static void tokenize_line(string_view line, size_t line_no, vector<Token>& result) {
        size_t first_indent = line.find_first_not_of(' ');
        if (first_indent == string_view::npos)
            first_indent = line.size();
        size_t current_indent = first_indent;

        while (!line.empty()) {
            size_t size = 0;
            Kind kind = UNEXPECTED;

            size_t unmatch_count = -1;
            do {
                unmatch_count += 1;
                for (auto &[rule_kind, rule_rx]: rules) {
                    match_results<std::string_view::const_iterator> match;
                    if (regex_search(line.cbegin() + unmatch_count, line.cend(), match, rule_rx, regex_constants::match_continuous)) {
                        ptrdiff_t match_size = match.length();
                        if (match_size > size) {
                            size = match_size;
                            kind = rule_kind;
                        }
                    }
                }
            } while (size == 0 && !line.empty());

            if (unmatch_count > 0) {
                result.push_back({
                    .kind = UNEXPECTED,
                    .line = line_no,
                    .offset = current_indent,
                    .line_indent = first_indent,
                    .text = line.substr(0, unmatch_count)
                });
                unmatch_count = 0;
                current_indent += unmatch_count;
                line = line.substr(unmatch_count);
            }

            if (size > 0) {
                if (kind != WHITESPACE) {
                    result.push_back({
                        .kind = kind,
                        .line = line_no,
                        .offset = current_indent,
                        .line_indent = first_indent,
                        .text = line.substr(0, size)
                    });
                }
                current_indent += size;
                line = line.substr(size);
            }
        }
    }

    vector<Token> tokenize(string_view text) {
        vector<Token> result { text.size() / 6 };
        size_t line_no = 0;

        while (!text.empty()) {
            size_t suffix_length, line_length = text.find_first_of('\n');

            if (line_length == string_view::npos) {
                line_length = text.size();
                suffix_length = 0;
            } else if (line_length > 0 && text[line_length-1] == '\r') {
                line_length -= 1;
                suffix_length = 2;
            } else {
                suffix_length = 1;
            }

            auto line = text.substr(0, line_length);
            text = text.substr(line_length + suffix_length);
            line_no += 1;

            tokenize_line(line, line_no, result);
        }

        return result;
    }
};
