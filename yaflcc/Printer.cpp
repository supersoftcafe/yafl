//
// Created by Michael Brown on 29/04/2022.
//

#include "Printer.h"

using namespace std;
using namespace ast;


ostream& operator << (ostream& out, Intrinsic const& e) {
    out << "__intrinsic__ " << e.name << '(';
    bool needsComma = false;
    for (auto& param : e.parameters) {
        if (needsComma) out << ", "; out << param;
        needsComma = true;
    }
    return out << ')';
}

ostream& operator << (ostream& out, Condition const& e) {
    auto& p = e.parameters;
    return out << p.at(0) << " ? " << p.at(1) << " : " << p.at(2);
}

ostream& operator << (ostream& out, Call const& e) {
    out << e.base.front() << '(';
    bool needsComma = false;
    for (auto& param : e.parameters) {
        if (needsComma) out << ", "; out << param;
        needsComma = true;
    }
    return out << ')';
}

ostream& operator << (ostream& out, StoreVariable const& e) {
    if (e.module)
        out << e.module->name << '.';
    return out << e.fieldName << " := " << e.value.front();
}

ostream& operator << (ostream& out, StoreField const& e) {
    if (!empty(e.base))
        out << e.base.front() << '.';
    return out << e.fieldName << " := " << e.value.front();
}

ostream& operator << (ostream& out, LoadVariable const& e) {
    return out << e.fieldName;
}

ostream& operator << (ostream& out, LoadField const& e) {
    if (!empty(e.base))
        out << e.base.front() << '.';
    return out << e.fieldName;
}

ostream& operator << (ostream& out, Expression const& expr) {
    for (auto& variable : expr.variables)
        out << variable;
    visit(overloaded{
        [&](monostate             e) { },
        [&](int64_t               e) { out << e; },
        [&](double                e) { out << e; },
        [&](string        const & e) { out << e; },
        [&](LoadField     const & e) { out << e; },
        [&](LoadVariable  const & e) { out << e; },
        [&](StoreField    const & e) { out << e; },
        [&](StoreVariable const & e) { out << e; },
        [&](Call          const & e) { out << e; },
        [&](Condition     const & e) { out << e; },
        [&](Lambda        const & e) { out << expr.type << " -> " << e.body.front(); },
        [&](Intrinsic     const & e) { out << e; }
    }, expr.op);
    return out;
}

ostream& operator << (ostream& out, Tuple const& type) {
    out << '(';
    bool needsComma = false;
    for (auto& parameter : type.parameters) {
        if (needsComma) out << ", ";
        out << parameter.name << ':' << parameter.type;
        needsComma = true;
    }
    return out << ')';
}

ostream& operator << (ostream& out, Function const& type) {
    return out << type.parameter << ':' << type.result.front();
}

ostream& operator << (ostream& out, Named const& type) {
    if (type.module)
        out << type.module->name << '.';
    return out << type.typeName;
}

ostream& operator << (ostream& out, Type const& type) {
    visit(overloaded{
        [&](Tuple    const& t) { out << t; },
        [&](Function const& t) { out << t; },
        [&](Named    const& t) { out << t; },
        [ ](monostate        ) { }
    }, type.type);
    return out;
}

ostream& operator << (ostream& out, Variable const& variable) {
    if (variable.type.asFunction() && holds_alternative<Lambda>(variable.value.op)) {
        return out << "fun " << variable.name << variable.type << " = " << get<Lambda>(variable.value.op).body.front();
    } else {
        return out << "let " << variable.name << ":" << variable.type << " = " << variable.value;
    }
}

ostream& operator << (ostream& out, Module const& module) {
    out << "module " << module.name << endl;
    out << endl;

    set<string> imports;
    for (auto& scope : module.scopes)
        for (auto& import : scope.modules)
            imports.insert(import->name);

    for (auto& import : imports)
        out << "use " << import << endl;
    out << endl;

    for (auto& variable : module.variables)
        out << variable << endl;
    return out << endl;
}

ostream& operator << (ostream& out, Ast const& ast) {
    for (auto& module : ast.modules) out << module;
    return out;
}
