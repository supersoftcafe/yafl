//
// Created by Michael Brown on 18/03/2022.
//

#include "Ast.h"

namespace ast {
    Expression::~Expression() = default;
    Value::~Value() = default;
    Declaration::~Declaration() = default;
    Binary::~Binary() = default;
    Bitwise::~Bitwise() = default;



    void Value::visit(Visitor &visitor) {
        visitor.onValue(this);
    }

    std::shared_ptr<Expression> Value::copy() {
        auto p = create();
        p->value = value;
        return p;
    }

    std::shared_ptr<Value> Value::create() {
        return std::make_shared<Value>();
    }


    void Declaration::visit(Visitor &visitor) {
        visitor.onDeclaration(this);
    }

    std::shared_ptr<Expression> Declaration::copy() {
        auto p = std::make_shared<Declaration>();
        p->type = type; p->name = name;
        if (init) p->init = init->copy();
        if (next) p->next = next->copy();
        return p;
    }

    std::shared_ptr<Declaration> Declaration::create() {
        return std::make_shared<Declaration>();
    }



    void Binary::visit(Visitor &visitor) {
        visitor.onBinary(this);
    }

    std::shared_ptr<Expression> Binary::copy() {
        auto p = create();
        p->kind = kind;
        if (left) p->left = left->copy();
        if (right) p->right = right->copy();
        return p;
    }

    std::shared_ptr<Binary> Binary::create() {
        return std::make_shared<Binary>();
    }



    void Bitwise::visit(Visitor &visitor) {
        visitor.onBitwise(this);
    }

    std::shared_ptr<Expression> Bitwise::copy() {
        auto p = std::make_shared<Bitwise>();
        p->kind = kind;
        if (left) p->left = left->copy();
        if (right) p->right = right->copy();
        return p;
    }

    std::shared_ptr<Bitwise> Bitwise::create() {
        return std::make_shared<Bitwise>();
    }
}
