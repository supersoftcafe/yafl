//
// Created by mbrown on 09/04/24.
//

#ifndef YAFLC_PARSER_H
#define YAFLC_PARSER_H

#include <list>
#include <span>
#include "tokenizer.h"
#include "error.h"

namespace ps {

    using namespace std;

    enum Kind {
        UNEXPECTED,
        IDENTIFIER,
        IMPORT,
        MODULE,
    };


    struct Node {
        Kind kind;
        LineRef line;
        string error;
        string_view text;
        list<Node> nodes;

        Node(Kind kind, LineRef line, string&& error) : kind(kind), line(line), error(std::move(error)) { }
        Node(Kind kind, LineRef line, string&& error, string_view text) : kind(kind), line(line), error(std::move(error)), text(text) { }
        Node(Kind kind, LineRef line, string&& error, list<Node>&& nodes) : kind(kind), line(line), error(std::move(error)), nodes(std::move(nodes)) { }
        Node(Kind kind, LineRef line, string&& error, string_view text, list<Node>&& nodes) : kind(kind), line(line), error(std::move(error)), text(text), nodes(std::move(nodes)) { }

        // Delete copy constructor and assignment operator
        Node(const Node&) = delete;
        Node& operator=(const Node&) = delete;
        Node(Node&&) = default;
    };

    list<Node> parse(span<tk::Token const> tokens);
};

#endif //YAFLC_PARSER_H
