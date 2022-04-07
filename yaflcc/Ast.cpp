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
    DotOperator::~DotOperator() = default;
    Call::~Call() = default;
//    BinaryMath::~BinaryMath() = default;
//    UnaryMath::~UnaryMath() = default;
    Function::~Function() = default;
    TypeDef::~TypeDef() = default;
    BuiltinType::~BuiltinType() = default;

    void LiteralValue::accept(Visitor &visitor) { visitor.visit(this); }
    void Declaration::accept(Visitor &visitor) { visitor.visit(this); }
    void DotOperator::accept(Visitor &visitor) { visitor.visit(this); }
    void Call::accept(Visitor &visitor) { visitor.visit(this); }
//    void BinaryMath::accept(Visitor &visitor) { visitor.visit(this); }
//    void UnaryMath::accept(Visitor &visitor) { visitor.visit(this); }


    static void addUnaryOperator(Module* module, FunctionKind kind, string name, TypeDef* type) {
        module->addFunction(make_unique<Function>(
                kind, std::move(name), type,
                vector{make_unique<Function>("value", type)}
        ));
    }

    static void addBinaryOperator(Module* module, FunctionKind kind, string name, TypeDef* type) {
        module->addFunction(make_unique<Function>(
                kind, std::move(name), type,
                vector{make_unique<Function>("left", type), make_unique<Function>("right", type)}
        ));
    }

    static void addBasicOperator(Module* module, FunctionKind kind, string name) {
        auto typeInt32 = module->types["Int32"].get();
        auto typeInt64 = module->types["Int64"].get();
        auto typeFloat32 = module->types["Float32"].get();
        auto typeFloat64 = module->types["Float64"].get();

        addUnaryOperator(module, kind, name, typeInt32);
        addUnaryOperator(module, kind, name, typeInt64);
        addUnaryOperator(module, kind, name, typeFloat32);
        addUnaryOperator(module, kind, name, typeFloat64);
        addBinaryOperator(module, kind, name, typeInt32);
        addBinaryOperator(module, kind, name, typeInt64);
        addBinaryOperator(module, kind, name, typeFloat32);
        addBinaryOperator(module, kind, name, typeFloat64);
    }

    Ast::Ast() : root{make_unique<Module>("")} {
        root->types.emplace("Bool" , make_unique<BuiltinType>(BuiltinType::BOOL , "b"));
        root->types.emplace("Int8" , make_unique<BuiltinType>(BuiltinType::INT8 , "i1"));
        root->types.emplace("Int16", make_unique<BuiltinType>(BuiltinType::INT16, "i2"));
        root->types.emplace("Int32", make_unique<BuiltinType>(BuiltinType::INT32, "i4"));
        root->types.emplace("Int64", make_unique<BuiltinType>(BuiltinType::INT64, "i8"));
        root->types.emplace("Float32", make_unique<BuiltinType>(BuiltinType::FLOAT32, "f4"));
        root->types.emplace("Float64", make_unique<BuiltinType>(BuiltinType::FLOAT64, "f8"));

        addBasicOperator(root.get(), FunctionKind::ADD, "`+`");
        addBasicOperator(root.get(), FunctionKind::ADD, "`-`");
        addBasicOperator(root.get(), FunctionKind::ADD, "`*`");
        addBasicOperator(root.get(), FunctionKind::ADD, "`/`");
        addBasicOperator(root.get(), FunctionKind::ADD, "`%`");
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


    void Module::addFunction(unique_ptr<Function>&& function) {
        functions[function->name].emplace_back(std::move(function));
    }
}
