//
// Created by Michael Brown on 18/03/2022.
//

#include "Ast.h"
#include "Tools.h"
#include <memory>

namespace ast {
    using namespace std;


    Ast::Ast() {
        auto system = findOrCreateModule("System");
        auto emplaceType = [system](auto kind, auto name, auto irType) {
            auto decl = &system->declarations.emplace_front(
                    Declaration { .scope = system->selfScope, .name = name, .type = Primitive { .kind = kind, .irType = irType }});
            return Type{Named{.typeName = name, .module = system, .declaration = decl }};
        };

        typeBool    = emplaceType(Primitive::BOOL   , "Bool"   , "b" );
        typeInt8    = emplaceType(Primitive::INT8   , "Int8"   , "i1");
        typeInt16   = emplaceType(Primitive::INT16  , "Int16"  , "i2");
        typeInt32   = emplaceType(Primitive::INT32  , "Int32"  , "i4");
        typeInt64   = emplaceType(Primitive::INT64  , "Int64"  , "i8");
        typeFloat32 = emplaceType(Primitive::FLOAT32, "Float32", "f4");
        typeFloat64 = emplaceType(Primitive::FLOAT64, "Float64", "f8");
    }

    Ast::~Ast() = default;


    Module* Ast::findOrCreateModule(string const & name) {
        auto found = find_if(begin(modules), end(modules), [&name](auto& a){ return a.name == name; });

        if (found == end(modules)) {
            auto modulePtr = &modules.emplace_front(Module{.name = name});
            modulePtr->selfScope = &modulePtr->scopes.emplace_front(ScopeContext{.owner = modulePtr, .modules = {modulePtr}});
            return modulePtr;
        } else {
            return &*found;
        }
    }
}
