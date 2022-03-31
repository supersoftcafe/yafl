//
// Created by Michael Brown on 18/03/2022.
//

#include "Ast.h"
#include <memory>

namespace ast {
    using namespace std;

    Expression::~Expression() = default;
    LiteralValue::~LiteralValue() = default;
    Declaration::~Declaration() = default;
    Binary::~Binary() = default;
    Unary::~Unary() = default;

    TypeDef::~TypeDef() = default;
    BuiltinType::~BuiltinType() = default;

    void LiteralValue::visit(Visitor &visitor) { visitor.onValue(this); }
    void Declaration::visit(Visitor &visitor) { visitor.onDeclaration(this); }
    void Binary::visit(Visitor &visitor) { visitor.onBinary(this); }
    void Unary::visit(Visitor &visitor) { visitor.onUnary(this); }



    Ast::Ast() {
        auto system = findOrCreateModule("System");

        system->types.emplace("Bool" , make_unique<BuiltinType>(BuiltinType::BOOL , "b"));
        system->types.emplace("Int8" , make_unique<BuiltinType>(BuiltinType::INT8 , "i1"));
        system->types.emplace("Int16", make_unique<BuiltinType>(BuiltinType::INT16, "i2"));
        system->types.emplace("Int32", make_unique<BuiltinType>(BuiltinType::INT32, "i4"));
        system->types.emplace("Int64", make_unique<BuiltinType>(BuiltinType::INT64, "i8"));
        system->types.emplace("Float32", make_unique<BuiltinType>(BuiltinType::FLOAT32, "f4"));
        system->types.emplace("Float64", make_unique<BuiltinType>(BuiltinType::FLOAT64, "f8"));
    }

    Ast::~Ast() = default;


    Module* Ast::findOrCreateModule(char const * name1) {
        return findOrCreateModule(vector<string>{name1});
    }

    Module* Ast::findOrCreateModule(char const * name1, char const * name2) {
        return findOrCreateModule(vector<string>{name1, name2});
    }

    Module* Ast::findOrCreateModule(vector<string> const & path) {
        if (root == nullptr)
            root = make_unique<Module>("");
        Module* module = root.operator->();

        for (auto const & name : path) {
            auto found = module->modules.find(name);
            if (found == std::end(module->modules))
                found = module->modules.insert(std::make_pair(name, make_unique<Module>(name))).first;
            module = found->second.operator->();
        }

        return module;
    }
}
