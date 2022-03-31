//
// Created by Michael Brown on 06/03/2022.
//

#include "parser.h"
#include "methodbuilder.h"
#include "input.h"
#include "types.h"
#include <map>
#include <set>
#include <vector>
#include <sstream>
#include <variant>


class parser {
private:
    input& in;

    std::set<std::string> known_types { };
    std::map<std::string, ir::Type> global_types { };
    std::vector<std::pair<std::string, int>> method_bodies { };

    std::ostringstream targetOut;
    std::ostringstream typeOut;
    std::ostringstream globalOut;
    std::ostringstream actualOut;
    std::ostringstream dataOut;
    std::ostringstream methodOut;
    std::ostringstream flagsOut;

    size_t wordSize;


    enum {
        ATTR_CONST = 0x01,
        ATTR_INLINE = 0x02,
    };


    static constexpr size_t BAD_NUM = size_t(-1);
    static size_t atol(std::string const & str) {
        std::istringstream strin { str };
        size_t val = BAD_NUM; strin >> val;
        return strin.fail() ? BAD_NUM : val;
    }

    static size_t align_offset(size_t offset, size_t alignment) {
        return (offset + alignment - 1) / alignment * alignment;
    }

    std::tuple<std::string, std::string> split(std::string const & value, char chr) {
        auto index = value.find(chr);
        if (index == std::string::npos)
            fatal("missing separator");
        return {value.substr(0, index), value.substr(index+1)};
    }

    ir::Type parse_typestr(std::string const & typestr) {
        ir::Type type;
        if (!ir::parse_typestr(typestr, wordSize, type))
            fatal("invalid type");
        return type;
    }





    void emit_type_decl(ir::Type const & type) {
        auto llvm_name = ir::type_to_llvm_name(type);

        if (type.kind == ir::Type::DataPointer) {
            if (!type.members.empty())
                emit_type_decl(type.members.at(0));

        } else if (!llvm_name.empty() && llvm_name.at(0) == '%' && known_types.insert(llvm_name).second) {
            std::ostringstream llvm_typestr;

            llvm_typestr << llvm_name << " = type";
            if (type.kind == ir::Type::Struct) {
                llvm_typestr << " {";
                char const *comma = "";
                for (auto &memberType: type.members) {
                    emit_type_decl(memberType);
                    llvm_typestr << comma << ir::type_to_llvm_name(memberType);
                    comma = ", ";
                }
                llvm_typestr << "}";

            } else if (type.kind == ir::Type::Union) {
                llvm_typestr << " {";
                size_t biggest = 0;
                for (auto &memberType: type.members) {
                    emit_type_decl(memberType);
                    biggest = std::max(biggest, memberType.size);
                    llvm_typestr << " [0 x " << ir::type_to_llvm_name(memberType) << "], ";
                }
                llvm_typestr << "[" << biggest << " x i8]}";

            } else {
                auto const &elementType = type.members.at(0);
                emit_type_decl(elementType);
                llvm_typestr << " [" << type.count << " x " << ir::type_to_llvm_name(elementType) << "]";
            }

            typeOut << llvm_typestr.str() << std::endl;
        }
    }

    std::string actual_to_llvm_type_name(std::string const & name) {
        if (name.empty() || name.at(0) != '@') fatal("internal error");
        return "%actual." + name.substr(1);
    }

    std::string global_to_llvm_type_name(std::string const & name) {
        if (name.empty() || name.at(0) != '@') fatal("internal error");
        return "%global." + name.substr(1);
    }


    int pop_attributes() {
        int attributes = 0;

        for (std::string token; !(token = in.peek()).empty() && token.at(0) != '@'; ) {
            in.pop();

            if (token == "const") {
                attributes |= ATTR_CONST;
            } else if (token == "inline") {
                attributes |= ATTR_INLINE;
            } else {
                warn("unknown attribute");
            }
        }

        return attributes;
    }


    void parse_target() {
        auto type = in.pop();

        targetOut << "target " << type;
        std::string param;
        for (std::string tmp; !(tmp = in.pop()).empty(); param = tmp)
            targetOut << ' ' << tmp;
        targetOut << std::endl;

        if (type == "datalayout") {
            std::istringstream ss { param };
            for (std::string tok; std::getline(ss, tok, '-'); ) {
                if (tok.rfind("i64:", 0) == 0 || tok.rfind("f64:", 0) == 0 || tok.rfind('p', 0) == 0) {
                    auto colon = tok.rfind(':', tok.length()-1);
                    if (colon != std::string::npos) {
                        auto value = atol(tok.substr(colon+1));
                        if (value != 32 && value != 64) fatal("invalid alignment");
                        wordSize = value / 8;
                    }
                }
            }
        }
    }


    std::tuple<std::string, std::string> to_data_decl(ir::Type const & type, size_t& offset) {
        if (type.kind == ir::Type::Struct) {
            std::string decl = "{", data = "{";
            offset = align_offset(offset, type.align);
            char const * comma = "";
            for (auto& member : type.members) {
                auto [memberDecl, memberData] = to_data_decl(member, offset);
                decl += comma; decl += memberDecl;
                data += comma; data += memberDecl; data += ' '; data += memberData;
                comma = ", ";
            }
            return {decl + '}', data + '}'};

        } else if (type.kind == ir::Type::Array) {
            if (type.count == 0) fatal("cannot have zero length array in data declaration");
            auto const & member = type.members.at(0);
            offset = align_offset(offset, type.align);
            ir::Type asArray { .align = type.align, .kind = ir::Type::Struct };
            for (auto index = 0; index < type.count; ++index)
                asArray.members.push_back(member);
            return to_data_decl(asArray, offset);

        } else {
            if (!in.getline()) fatal("missing data");
            auto typestr       = in.pop();
            auto value         = in.pop();
            if (!in.peek().empty()) warn("value line has excess tokens");

            switch (type.kind) {
                case ir::Type::Bool:
                    if (typestr != "b") fatal("type mismatch, bool expected");
                    offset += 1;
                    return { "i1", value };

                case ir::Type::Float:
                case ir::Type::AtomicCounter:
                case ir::Type::Size:
                case ir::Type::Int: {
                    if (typestr != type.name) fatal("type mismatch");
                    offset = align_offset(offset, type.align);
                    auto decl = ir::type_to_llvm_name(type);
                    return { decl, value };
                }

                case ir::Type::DataPointer:
                case ir::Type::MethodPointer: {
                    if (typestr != type.name) fatal("type mismatch, data pointer expected");
                    if (value.empty() || value.at(0) != '@') fatal("must be global reference");

                    std::string decl = ir::type_to_llvm_name(type);
                    std::string data = "bitcast (" + actual_to_llvm_type_name(value) + "* " + value + " to " + decl + ')';
                    offset = align_offset(offset, wordSize) + wordSize;
                    return { decl, data };
                }

                case ir::Type::Union: {
                    if (typestr != "u") fatal("type mismatch, union expected");
                    size_t unionSelector = atol(value);
                    if (unionSelector >= type.members.size()) fatal("bad union hint");
                    auto const &member = type.members.at(unionSelector);
                    offset = align_offset(offset, type.align);

                    auto [memberDecl, memberData] = to_data_decl(member, offset);
                    std::string alignment_token = "[0 x " + ir::type_to_llvm_name(type) + "]";
                    std::string decl = "{" + alignment_token + ", " + memberDecl;
                    std::string data = "{" + alignment_token + " undef, " + memberDecl + ' ' + memberData;

                    auto diff = type.size - member.size;
                    if (diff > 0) {
                        // Needs padding at the end
                        auto padding_type = ", [" + std::to_string(diff) + " x i8]";
                        decl += padding_type;
                        data += padding_type + " undef";
                        offset += diff;
                    }

                    return {decl + '}', data + '}'};
                }

                default:
                    fatal("internal error");
            }
        }
    }

    void parse_data() {
        // Deal with tokens parameter
        int attributes = pop_attributes();

        // @Name extraction, with colon type
        auto [name, typestr] = split(in.pop(), ':');
        if (!in.peek().empty()) warn("data line has excess tokens");
        if (name.size() < 2 || name.at(0) != '@') fatal("invalid data name");
        auto type = parse_typestr(typestr);

        // Add to global lookups
        emit_type_decl(type);
        global_types.insert_or_assign(name, type);

        // Parse methodOut the actual data
        size_t offset = 0;
        auto [decl, data] = to_data_decl(type, offset);
        if (!in.getline() || in.peek() != "end")
            fatal("should have end here");

        // Write it methodOut
        dataOut << name << " = internal " << ((attributes&ATTR_CONST) ? "constant " : "global ");
        dataOut << actual_to_llvm_type_name(name) << ' ' << data << std::endl;
        dataOut << std::endl;

        // Write 'reference' declaration and 'global' declaration.
        // 'reference' is to help when referencing the type, because we have to know the structure.
        // 'global' is how we want to access it, which is different to how we initialise it.

        // Create forward decl. Resolves recursive references and complex chains.
        actualOut << actual_to_llvm_type_name(name) << " = type " << decl << std::endl;
        globalOut << global_to_llvm_type_name(name) << " = type " << ir::type_to_llvm_name(type) << std::endl;
    }

    std::tuple<std::string, ir::Type> split_name_and_type(std::string const & token) {
        auto [name, typestr] = split(token, ':');
        if (typestr.rfind("p.", 0) == 0) {
            auto type = parse_typestr("p");
            type.members.push_back(parse_typestr(typestr.substr(2)));
            return { name, type };
        }
        return { name, parse_typestr(typestr) };
    }

    void copy_method() {
        std::ostringstream body;
        int lineNumber = in.linenumber;

        body << in.line << std::endl;
        while (in.getline()) {
            body << in.line << std::endl;
            if (in.peek() == "end") break;
        }

        method_bodies.emplace_back(body.str(), lineNumber);
    }

    void instrRet(methodbuilder& builder) {
        auto returnValue = in.pop();
        if (!in.pop().empty()) warn("excess tokens");
        builder.ret(returnValue);
    }

    void instrBinary(methodbuilder& builder, methodbuilder::BINARY_OPS op) {
        auto target = in.pop(); if (target.empty()) fatal("missing target");
        auto input1 = in.pop(); if (input1.empty()) fatal("missing input 1");
        auto input2 = in.pop(); if (input2.empty()) fatal("missing input 2");
        auto overflowCond = in.pop();
        if (!in.pop().empty()) warn("excess tokens");

        builder.binary_op(op, target, input1, input2, overflowCond);
    }

    void instrBitwise(methodbuilder& builder, methodbuilder::BITWISE_OPS op) {
        auto target = in.pop(); if (target.empty()) fatal("missing target");
        auto input1 = in.pop(); if (input1.empty()) fatal("missing input 1");
        auto input2 = in.pop(); if (input2.empty()) fatal("missing input 2");
        if (!in.pop().empty()) warn("excess tokens");

        builder.bitwise_op(op, target, input1, input2);
    }

    void instrUnary(methodbuilder& builder, methodbuilder::UNARY_OPS op) {
        auto target = in.pop(); if (target.empty()) fatal("missing target");
        auto input  = in.pop(); if (input .empty()) fatal("missing input");
        if (!in.pop().empty()) warn("excess tokens");

        builder.unary_op(op, target, input);
    }

    void instrCompare(methodbuilder& builder, methodbuilder::COMPARE_OPS op) {
        auto target = in.pop(); if (target.empty()) fatal("missing target");
        auto input1 = in.pop(); if (input1.empty()) fatal("missing input 1");
        auto input2 = in.pop(); if (input2.empty()) fatal("missing input 2");
        if (!in.pop().empty()) warn("excess tokens");

        builder.compare_op(op, target, input1, input2);
    }

    void instrBranch(methodbuilder& builder) {
        auto cond = in.pop();
        auto label_if_true = in.pop();
        auto label_if_false = in.pop();
        if (cond.empty())
            fatal("missing condition variable");
        if (label_if_true.empty() || label_if_false.empty())
            fatal("missing label");
        builder.branch_if(cond, label_if_true, label_if_false);
    }

    void instrJump(methodbuilder& builder) {
        auto label = in.pop();
        builder.jump(label);
    }

    void instrSwitch(methodbuilder& builder) {
        auto cond = in.pop();
        auto label_for_default = in.pop();
        if (cond.empty())
            fatal("missing condition variable");
        if (label_for_default.empty())
            fatal("missing label");

        std::vector<std::pair<int32_t, std::string>> labels;
        for (std::string token = in.pop(); !token.empty(); token = in.pop()) {
            auto [valueStr, label] = split(token, ':');
            auto chr = valueStr.empty() ? '\0' : valueStr.at(0);
            if (chr < '0' || chr > '9')
                fatal("invalid conditional value");
            int32_t value = std::stoi(valueStr);
            labels.emplace_back(value, ':' + label);
        }
        builder.switch_on(cond, label_for_default, labels);
    }

    void instrCall(methodbuilder& builder) {
        auto[resultStr, paramStr] = split(in.pop(), '.');
        auto resultType = parse_typestr(resultStr);
        auto paramTypes = parse_typestr(paramStr);
        auto result = in.pop();
        auto method = in.pop();

        if (method.empty()) fatal("missing parameters");
        if (paramTypes.kind != ir::Type::Struct) fatal("param type must be struct");

        std::vector<std::string> parameters;
        for (std::string value = in.pop(); !value.empty(); value = in.pop())
            parameters.push_back(value);

        builder.call(resultType, result, method, paramTypes.members, parameters);
    }

    void instrAcquire(methodbuilder& builder) {
        auto countRef = in.pop();
        if (countRef.empty()) fatal("missing parameters");
        builder.acquire(countRef);
    }

    void instrRelease(methodbuilder& builder) {
        auto countRef = in.pop();
        auto zeroCond = in.pop();
        if (countRef.empty()) fatal("missing parameters");
        if (zeroCond.empty()) fatal("missing parameters");
        builder.release(countRef, zeroCond);
    }

    void instrMalloc(methodbuilder& builder) {
        auto pointerRef = in.pop();
        auto type = parse_typestr(in.pop());
        auto arrayLength = in.pop();

        emit_type_decl(type);
        builder.malloc(pointerRef, type, arrayLength);
    }

    void instrFree(methodbuilder& builder) {
        auto pointerRef = in.pop();
        if (pointerRef.empty()) fatal("missing parameters");
        builder.free(pointerRef);
    }

    void parse_method() {
        methodbuilder builder { in, methodOut, global_types };

        // @Name extraction, with colon type
        int attributes = pop_attributes();
        auto [methodName, returnType] = split_name_and_type(in.pop());
        emit_type_decl(returnType);
        builder.begin_method(methodName, returnType);

        // Accumulate the IR type declaration here
        auto forwardDeclStr = ir::type_to_llvm_name(returnType) + '(';

        // %Parameters extraction, with colon types
        std::vector<std::tuple<std::string, std::string>> allParamNames;
        for (std::string param; !(param = in.pop()).empty(); ) {
            auto [paramName, paramType] = split_name_and_type(param);
            auto paramTypeName = ir::type_to_llvm_name(paramType);

            if (forwardDeclStr.back() != '(') forwardDeclStr += ", ";
            forwardDeclStr += paramTypeName;
            builder.declare_parameter(paramName, paramType);

            emit_type_decl(paramType);
        }
        forwardDeclStr += ')';

        // Parse the variable declarations
        builder.begin_variables();
        while (in.getline()) {
            auto token = in.pop();

            if (token == "begin") {
                break;
            } else if (token == "end") {
                fatal("premature termination of method");
            } else {
                auto [varName, varType] = split_name_and_type(token);
                if (!in.pop().empty()) warn("extra tokens at end of line");
                builder.declare_variable(varName, varType);

                emit_type_decl(varType);
            }
        }

        // Parse instructions and basic blocks delimited by labels
        builder.begin_body();
        while (in.getline()) {
            auto token = in.pop();

            if (token == "end") {
                if (!in.pop().empty()) warn("excess tokens");
                break;

            } else if (!token.empty() && token.at(0) == ':') {
                if (!in.pop().empty()) warn("excess tokens");
                builder.label(token);

            }

            else if (token == "ret") instrRet(builder);
            else if (token == "add") instrBinary(builder, methodbuilder::ADD);
            else if (token == "sub") instrBinary(builder, methodbuilder::SUB);
            else if (token == "mul") instrBinary(builder, methodbuilder::MUL);
            else if (token == "div") instrBinary(builder, methodbuilder::DIV);
            else if (token == "rem") instrBinary(builder, methodbuilder::REM);
            else if (token == "rol") instrBitwise(builder, methodbuilder::ROL);
            else if (token == "ror") instrBitwise(builder, methodbuilder::ROR);
            else if (token == "shl") instrBitwise(builder, methodbuilder::SHL);
            else if (token =="lshr") instrBitwise(builder, methodbuilder::LSHR);
            else if (token =="ashr") instrBitwise(builder, methodbuilder::ASHR);
            else if (token == "and") instrBitwise(builder, methodbuilder::AND);
            else if (token == "xor") instrBitwise(builder, methodbuilder::XOR);
            else if (token ==  "or") instrBitwise(builder, methodbuilder::OR );
            else if (token == "mov") instrUnary(builder, methodbuilder::MOV);
            else if (token == "eq") instrCompare(builder, methodbuilder::EQ);
            else if (token == "ne") instrCompare(builder, methodbuilder::NE);
            else if (token == "gt") instrCompare(builder, methodbuilder::GT);
            else if (token == "ge") instrCompare(builder, methodbuilder::GE);
            else if (token == "lt") instrCompare(builder, methodbuilder::LT);
            else if (token == "le") instrCompare(builder, methodbuilder::LE);
            else if (token == "br") instrBranch(builder);
            else if (token == "jmp") instrJump(builder);
            else if (token == "switch") instrSwitch(builder);
            else if (token == "call") instrCall(builder);
            else if (token == "acquire") instrAcquire(builder);
            else if (token == "release") instrRelease(builder);
            else if (token == "malloc") instrMalloc(builder);
            else if (token == "free") instrFree(builder);

            else fatal("unknown instruction");
        }

        builder.end();
        methodOut << std::endl;

        // Write out a type definition to match this method's signature. It helps with bitcast usage later.
        actualOut << actual_to_llvm_type_name(methodName) << " = type " << forwardDeclStr << std::endl;
    }

public:
    parser(input& in, size_t wordSize) : in(in), wordSize(wordSize) { }

    void pass1() {
        flagsOut << "attributes #0 = { noinline nounwind ssp uwtable \"darwin-stkchk-strong-link\" \"disable-tail-calls\"=\"false\" \"less-precise-fpmad\"=\"false\" \"min-legal-vector-width\"=\"0\" \"no-infs-fp-math\"=\"false\" \"no-jump-tables\"=\"false\" \"no-nans-fp-math\"=\"false\" \"no-signed-zeros-fp-math\"=\"false\" \"no-trapping-math\"=\"true\" \"probe-stack\"=\"___chkstk_darwin\" \"stack-protector-buffer-size\"=\"8\" \"target-cpu\"=\"penryn\" \"target-features\"=\"+cx16,+cx8,+fxsr,+mmx,+sahf,+sse,+sse2,+sse3,+sse4.1,+ssse3,+x87\" \"tune-cpu\"=\"generic\" \"unsafe-fp-math\"=\"false\" \"use-soft-float\"=\"false\" }\n"
                    "\n"
                    "!llvm.module.flags = !{!0, !1, !2}\n"
                    "!llvm.ident = !{!3}\n"
                    "\n"
                    "!0 = !{i32 2, !\"SDK Version\", [2 x i32] [i32 12, i32 1]}\n"
                    "!1 = !{i32 1, !\"wchar_size\", i32 4}\n"
                    "!2 = !{i32 7, !\"PIC Level\", i32 2}\n"
                    "!3 = !{!\"Apple clang version 13.0.0 (clang-1300.0.29.30)\"}\n"
                    ""
                    "declare {i8 , i1} @llvm.sadd.with.overflow.i8 (i8  %a, i8  %b)\n"
                    "declare {i16, i1} @llvm.sadd.with.overflow.i16(i16 %a, i16 %b)\n"
                    "declare {i32, i1} @llvm.sadd.with.overflow.i32(i32 %a, i32 %b)\n"
                    "declare {i64, i1} @llvm.sadd.with.overflow.i64(i64 %a, i64 %b)\n"
                    "\n"
                    "declare i8  @llvm.fshl.i8  (i8  %a, i8  %b, i8  %c)\n"
                    "declare i16 @llvm.fshl.i16 (i16 %a, i16 %b, i16 %c)\n"
                    "declare i32 @llvm.fshl.i32 (i32 %a, i32 %b, i32 %c)\n"
                    "declare i64 @llvm.fshl.i64 (i64 %a, i64 %b, i64 %c)\n"
                    "\n"
                    "declare i8  @llvm.fshr.i8  (i8  %a, i8  %b, i8  %c)\n"
                    "declare i16 @llvm.fshr.i16 (i16 %a, i16 %b, i16 %c)\n"
                    "declare i32 @llvm.fshr.i32 (i32 %a, i32 %b, i32 %c)\n"
                    "declare i64 @llvm.fshr.i64 (i64 %a, i64 %b, i64 %c)\n"
                    "\n"
                    "declare align 16 i8* @malloc(%size_t)\n"
                    "declare void @free(i8*)\n"
                    "\n";

        typeOut << "%size_t = type " << ir::type_to_llvm_name(parse_typestr("is")) << std::endl;

        while (in.getline()) {
            auto first = in.pop();

            if (first == "method") {
                copy_method();

            } else if (first == "data") {
                parse_data();

            } else if (first == "target") {
                parse_target();

            } else {
                fatal(": invalid first token");
            }
        }
    }

    void pass2() {
        for (auto& [method_body, first_line] : method_bodies) {
            in.reset(method_body, first_line);
            in.getline(); // Pre-fill the first line
            in.pop(); // Skip the first "method" token

            parse_method();
        }
    }

    void write(std::ostream& out) {
        out <<  targetOut.str() << std::endl;
        out <<    typeOut.str() << std::endl;
        out <<  globalOut.str() << std::endl;
        out <<  actualOut.str() << std::endl;
        out <<    dataOut.str() << std::endl;
        out <<  methodOut.str() << std::endl;
        out <<   flagsOut.str() << std::endl;
    }
};


void convert_yaflir_to_llvmir(std::istream& instream, std::ostream& out) {
    std::string str { std::istreambuf_iterator<char>(instream), std::istreambuf_iterator<char>() };

    input in;
    in.reset(str, 0);
    parser p { in, 8 };

    p.pass1();
    p.pass2();
    p.write(out);
}

