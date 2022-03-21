//
// Created by Michael Brown on 18/03/2022.
//

#include "Ast.h"

namespace ast {
    Expression::~Expression() = default;
    LiteralValue::~LiteralValue() = default;
    Declaration::~Declaration() = default;
    Binary::~Binary() = default;
    Bitwise::~Bitwise() = default;


    void LiteralValue::visit(Visitor &visitor) {
        visitor.onValue(this);
    }

    void Declaration::visit(Visitor &visitor) {
        visitor.onDeclaration(this);
    }

    void Binary::visit(Visitor &visitor) {
        visitor.onBinary(this);
    }

    void Bitwise::visit(Visitor &visitor) {
        visitor.onBitwise(this);
    }
}
