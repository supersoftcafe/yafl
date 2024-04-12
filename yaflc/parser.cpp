//
// Created by mbrown on 09/04/24.
//

#include "parser.h"
#include <optional>
#include <span>

namespace ps {

    optional<tuple<Node, vector<Error>, span<tk::Token>::iterator>> parse_import(span<tk::Token> nodes) {
        if (nodes.size() < 1)
            return nullopt;
        auto& import = nodes[0];
        if (import.kind != tk::Kind::IMPORT)
            return nullopt;

        if (nodes.size() < 2) {
            return {{
                {
                    .kind = Kind::IMPORT,
                    .line = import.line,
                    .offset = import.offset,
                    .text = import.text.substring(0, 0),
                },
                {
                    .line = import.line,
                    .offset = import.offset,
                    .message = "'import' statement is missing a name",
                    .code = import.text,
                },
                nodes.iterator + 1
            }};
        }
        auto& identifier = nodes[1];

        if (identifier.kind != tk::Kind::IDENTIFIER) {
            return {{
                {
                    .kind = Kind::IMPORT,
                    .line = import.line,
                    .offset = import.offset,
                    .text = import.text.substring(0, 0),
                },
                {{
                    .line = import.line,
                    .offset = import.offset,
                    .message = "'import' statement is missing a name",
                    .code = import.text,
                }},
                nodes.iterator + 1
            }};
        }

        return {{
            {
                .kind = Kind::IMPORT,
                .line = import.line,
                .offset = import.offset,
                .text = identifier.text,
            },
            { },
            nodes.iterator + 2
        }};
    }

    tuple<vector<Node>, vector<Error>> parse(const vector<tk::Token>& tokens) {
        vector<Error> errors;
        vector<Node> nodes;

        // What about unparseable crap at the start of the file

        // Module line?

        // What about unparseable crap before imports

        // Repetition??
        auto import = parse_import(span { tokens });
        if (import.has_value()) {
            auto& [node, suberrors, iter] = import.value();
            nodes.emplace_back(std::move(node));
            std::move(suberrors.begin(), suberrors.end(), back_inserter(errors));

        }

        // What about unparseable crap here before the body of the file

        // All of this becomes a single node representing all of that module.
        // And then we loop to parse the next module, if it's in the same file..
        // Repeat until there are no more nodes

        return tuple { std::move(nodes), std::move(errors) };
    }
};
