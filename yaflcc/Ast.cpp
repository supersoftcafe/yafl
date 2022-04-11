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
    Function::~Function() = default;
    TypeDef::~TypeDef() = default;
    BuiltinType::~BuiltinType() = default;

    void LiteralValue::accept(Visitor &visitor) { visitor.visit(this); }
    void LiteralValue::print(ostream& out) { out << value; }

    void Declaration::accept(Visitor &visitor) { visitor.visit(this); }
    void Declaration::print(ostream& out) { out << expression; }

    void DotOperator::accept(Visitor &visitor) { visitor.visit(this); }
    void DotOperator::print(ostream& out) { out << left << '.' << right; }

    void Call::accept(Visitor &visitor) { visitor.visit(this); }
    void Call::print(ostream& out) {
        out << function << '(';
        bool needsComma = false;
        for (auto& param : parameters) {
            if (needsComma) out << ',';
            needsComma = true;
            out << param;
        }
        out << ')';
    }

    void Function::print(ostream& out) {
        out << name << '(';
        bool needsComma = false;
        for (auto& param : parameters) {
            if (needsComma) out << ',';
            needsComma = true;
            out << param;
        }
        out << ')';


        if (!empty(result.names)) {
            out << ':';
            bool needsDot = false;
            for (auto& name : result.names) {
                if (needsDot) out << '.';
                needsDot = true;
                out << name;
            }
        }

        if (body) {
            out << " = " << body;
        }
    }


    static void addUnaryOperator(Module* module, FunctionKind kind, string name, TypeDef* type) {
        auto v = vector<unique_ptr<Function>>();
        v.emplace_back(new Function("value", type));
        module->functions.emplace_back(new Function(kind, std::move(name), type, std::move(v)));
    }

    static void addBinaryOperator(Module* module, FunctionKind kind, string name, TypeDef* type) {
        auto v = vector<unique_ptr<Function>>();
        v.emplace_back(new Function("left", type));
        v.emplace_back(new Function("right", type));
        module->functions.emplace_back(new Function(kind, std::move(name), type, std::move(v)));
    }

    static auto find(auto & collection, auto & name) {
        return std::find_if(std::begin(collection), std::end(collection), [&name](auto& a){ return a->name == name; });
    }


    static void addBasicOperator(Module* module, FunctionKind kind, string name) {
        auto typeInt32 = find(module->types, "Int32")->get();
        auto typeInt64 = find(module->types, "Int64")->get();
        auto typeFloat32 = find(module->types, "Float32")->get();
        auto typeFloat64 = find(module->types, "Float64")->get();

        addUnaryOperator(module, kind, name, typeInt32);
        addUnaryOperator(module, kind, name, typeInt64);
        addUnaryOperator(module, kind, name, typeFloat32);
        addUnaryOperator(module, kind, name, typeFloat64);
        addBinaryOperator(module, kind, name, typeInt32);
        addBinaryOperator(module, kind, name, typeInt64);
        addBinaryOperator(module, kind, name, typeFloat32);
        addBinaryOperator(module, kind, name, typeFloat64);
    }

    Ast::Ast() : root{new Module("")} {
        root->types.emplace_back(make_unique<BuiltinType>(BuiltinType::BOOL , "Bool" , "b"));
        root->types.emplace_back(make_unique<BuiltinType>(BuiltinType::INT8 , "Int8" , "i1"));
        root->types.emplace_back(make_unique<BuiltinType>(BuiltinType::INT16, "Int16", "i2"));
        root->types.emplace_back(make_unique<BuiltinType>(BuiltinType::INT32, "Int32", "i4"));
        root->types.emplace_back(make_unique<BuiltinType>(BuiltinType::INT64, "Int64", "i8"));
        root->types.emplace_back(make_unique<BuiltinType>(BuiltinType::FLOAT32, "Float32", "f4"));
        root->types.emplace_back(make_unique<BuiltinType>(BuiltinType::FLOAT64, "Float64", "f8"));

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
        Module* module = root.get();

        for (auto const & name : path) {
            auto found = find(module->modules, name);
            if (found != std::end(module->modules)) {
                module = found->get();
            } else {
                auto m = new Module(name);
                module->modules.emplace_back(m);
                module = m;
            }
        }

        return module;
    }
}
