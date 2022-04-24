//
// Created by Michael Brown on 18/03/2022.
//

#include "Ast.h"
#include "Tools.h"
#include <memory>

namespace ast {
    using namespace std;

    Function::~Function() = default;

    void Expression::print(ostream& out) {
        switch (kind) {
            case INTEGER:
            case FLOAT:
            case NAME:
                out << value;
                break;

            case STRING:
                out << '"' << value << '"';
                break;

            case DOT:
                out << parameters.at(0) << '.' << value;
                break;

            case CALL:
                out << parameters.at(0) << '(';
                bool needsComma = false;
                for (auto& param : span(parameters).subspan(1)) {
                    if (needsComma) out << ',';
                    needsComma = true;
                    out << param;
                }
                out << ')';
                break;
        }
    }

    void Function::print(ostream& out) {
        for (auto& annotation : annotations) {
            out << '@' << annotation << ' ';
        }

        out << name;
        if (!empty(parameters)) {
            out << '(';
            bool needsComma = false;
            for (auto &param: parameters) {
                if (needsComma) out << ',';
                needsComma = true;
                out << param;
            }
            out << ')';
        }

        if (!empty(result.typeName)) {
            out << ':';
            if (!empty(result.moduleName))
                out << result.moduleName << '.';
            out << result.typeName;
        }

        if (body) {
            out << " = " << body;
        }
    }



    Ast::Ast() {
        auto system = findOrCreateModule("System");
        auto emplaceType = [system](auto kind, auto name, auto irType) {
            auto type = new TypeDef{.kind = kind, .name = name , .irType = irType};
            system->types.emplace_back(type);
            return type;
        };

        typeBool    = emplaceType(TypeDef::BUILTIN, "Bool"   , "b" );
        typeInt8    = emplaceType(TypeDef::BUILTIN, "Int8"   , "i1");
        typeInt16   = emplaceType(TypeDef::BUILTIN, "Int16"  , "i2");
        typeInt32   = emplaceType(TypeDef::BUILTIN, "Int32"  , "i4");
        typeInt64   = emplaceType(TypeDef::BUILTIN, "Int64"  , "i8");
        typeFloat32 = emplaceType(TypeDef::BUILTIN, "Float32", "f4");
        typeFloat64 = emplaceType(TypeDef::BUILTIN, "Float64", "f8");
    }
    Ast::~Ast() = default;


    Module* Ast::findOrCreateModule(string const & name) {
        auto found = find_if(begin(modules), end(modules), [&name](auto& a){ return a->name == name; });

        if (found == end(modules))
            return modules.emplace_back(new Module { .name = name }).get();
        else
            return found->get();
    }
}
