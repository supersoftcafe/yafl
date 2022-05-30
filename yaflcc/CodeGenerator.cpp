//
// Created by Michael Brown on 27/03/2022.
//

#include <iostream>
#include <sstream>

#include "CodeGenerator.h"

using namespace ast;
using namespace std;


static void fatal [[ noreturn ]]  (char const* message) {
    cerr << message << endl;
    ::exit(1);
}

struct CodeGen {
    Ast& ast;
    ostream& out;



    string typeToIrType(Type const& type) {
        if (type == ast.typeBool) return "b";
        if (type == ast.typeInt8) return "i1";
        if (type == ast.typeInt16) return "i2";
        if (type == ast.typeInt32) return "i4";
        if (type == ast.typeInt64) return "i8";
        if (type == ast.typeFloat32) return "f4";
        if (type == ast.typeFloat64) return "f8";

        if (auto f = type.asFunction()) {
            fatal("function types are not supported yet");
        } else if (auto t = type.asTuple()) {
            fatal("tuple types are not supported yet");
        } else {
            auto n = type.asNamed();
            fatal("named types are not supported yet");
        }
    }

    static string lambdaName(Lambda const& lambda, string const& baseName) {
        return baseName + '_' + to_string(uint32_t(size_t(&lambda)));
    }


    // For now we only support generating static lambdas
    void gen(Expression const& expr, Lambda const& lambda, string const& baseName) {
        auto name = lambdaName(lambda, baseName);
        auto fun = expr.type.asFunction();

        assert(fun != nullptr); // Must be function
        assert(distance(begin(lambda.parameters), end(lambda.parameters)) == size(fun->parameter.parameters)); // Type must match actual parameters

        out << "method @" << name << ':' << typeToIrType(fun->result.front());
        int variableNumber = 0;
        for (auto& parameter : lambda.parameters) {
            out << "%v" << variableNumber++ << ':' << typeToIrType(parameter.type);
        }
        out << endl;

        ostringstream body;

        // TODO: Emit code to 'body' writing variable declarations to 'out' as we go
        function<string(Type const&)> declVar = [&](Type const& type) {
            out << "  %v" << variableNumber << ':' << typeToIrType(type) << endl;
            return "%v" + to_string(variableNumber++);
        };

        writeExpression();

        out << "begin" << endl << body.str() << "end" << endl;
    }



    void writeHeader() {
        out << "target datalayout = \"e-m:o-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128\"" << endl;
        out << "target triple = \"x86_64-apple-macosx12.0.0\"" << endl;
        out << endl;
    }

    void gen(Variable const& variable) {
        if (variable.isFunction()) {
            // Treat it as a function
            MethodGen methodGen { .ast = ast, .out = out };
            methodGen.gen(variable);
        } else {
            // TODO: Treat is as data
        }
    }

    void gen(Module const& module) {
        for (auto& variable : module.variables)
            gen(variable);
    }

    void gen() {
        for (auto& module : ast.modules)
            gen(module);
    }
};



void generateTheCode(Ast& ast, ostream& out) {
    CodeGen codegen { .ast = ast, .out = out };
    codegen.gen();
}
