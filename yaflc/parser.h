//
// Created by mbrown on 09/04/24.
//

#ifndef YAFLC_PARSER_H
#define YAFLC_PARSER_H

#include <list>
#include <span>
#include <memory>
#include <any>
#include "tokenizer.h"
#include "error.h"

namespace ps {

    using namespace std;

    struct Node {
        tk::Kind kind;
        SourceRef line;
        string value;
        list<Node> nodes;

        Node(tk::Kind kind, SourceRef line) : kind(kind), line(line) { }
        Node(tk::Kind kind, SourceRef line, string&& value) : kind(kind), line(line), value(std::move(value)) { }
        Node(tk::Kind kind, SourceRef line, string&& value, list<Node>&& nodes) : kind(kind), line(line), value(std::move(value)), nodes(std::move(nodes)) { }

        // Delete copy constructor and assignment operator
        Node(const Node&) = delete;
        Node& operator=(const Node&) = delete;
        Node(Node&&) = default;
    };


    tuple<list<Node>, list<ErrorMessage>> parse(span<tk::Token const> tokens);
};

#endif //YAFLC_PARSER_H



