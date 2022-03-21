//
// Created by Michael Brown on 15/03/2022.
//

#include "methodbuilder.h"



methodbuilder::methodbuilder(input &in, std::ostream &out, std::map<std::string, ir::Type> const & global_types)
    : in(in), out(out), global_types(global_types) { }

ir::Type methodbuilder::get_variable_type(std::string const & name) {
    if (name.find('/') != std::string::npos) {
        return get_gep_info(name).type;

    } else {

        auto typeEntry = variables.find(name);
        if (typeEntry != variables.end())
            return typeEntry->second;

        auto globalEntry = global_types.find(name);
        if (globalEntry != global_types.end())
            return globalEntry->second;

        fatal("failed to find variable");
    }
}

void methodbuilder::begin_method(std::string const & name, ir::Type const & type) {
    if (name.size() < 2 || name.at(0) != '@') fatal("invalid method name");
    out << "define " << ir::type_to_llvm_name(type) << ' ' << name << '(';
    returnType = type;
}

void methodbuilder::declare_parameter(std::string const & name, ir::Type const & type) {
    if (name.size() < 2 || name.at(0) != '%') fatal("invalid parameter name");
    if (!allParamNames.empty()) out << ", ";
    out << ir::type_to_llvm_name(type) << ' ' << name << "_p";
    allParamNames.emplace_back(name, type);
    variables.insert_or_assign(name, type);
}

void methodbuilder::begin_variables() {
    out << ") #0 {" << std::endl;
    // Before variables, allocate space for parameters on the stack
    for (auto& [paramName, paramType] : allParamNames)
        out << "  " << paramName << " = alloca " << ir::type_to_llvm_name(paramType) << std::endl;
}

void methodbuilder::declare_variable(std::string const & name, ir::Type const & type) {
    // Emit the forward declaration of variable, uninitialised
    out << "  " << name << " = alloca " << ir::type_to_llvm_name(type) << std::endl;
    variables.insert_or_assign(name, type);
}

void methodbuilder::begin_body() {
    // Copy parameters to the allocated stack space
    for (auto& [paramName, paramType] : allParamNames) {
        auto llvmName = ir::type_to_llvm_name(paramType);
        out << "  store " << llvmName << ' ' << paramName << "_p, " << llvmName << "* " << paramName << std::endl;
    }
}

void methodbuilder::label(std::string const & name) {
    out << name.substr(1) << ':' << std::endl;
}


void methodbuilder::call(
        ir::Type const & resultType, std::string const & result,
        std::string const & method,
        std::vector<ir::Type> const & parameterTypes, std::vector<std::string> const & parameters) {

    if (resultType.kind == ir::Type::Void) {
        if (result != "-")
            fatal("result must be - if return type is void");
    } else {
        if (result.empty() || result.at(0) != '%')
            fatal("result must be a register");
    }

    if (parameterTypes.size() != parameters.size())
        fatal("parameter count and signature mismatch");

    std::vector<std::string> loaded_parameters;
    for (const auto & parameter : parameters)
        loaded_parameters.push_back(load_variable(parameter));

    auto reg = '%' + temp_register() + '_';
    auto resultName = reg + "result";

    out << "  ";
    if (resultType.kind != ir::Type::Void)
        out << resultName << " = ";

    out << "call " << ir::type_to_llvm_name(resultType) << ' ' << method << '(';
    for (int index = 0; index < parameters.size(); ++index) {
        if (index > 0) out << ", ";
        out << ir::type_to_llvm_name(parameterTypes.at(index)) << ' ' << loaded_parameters.at(index);
    }
    out << ')' << std::endl;

    if (resultType.kind != ir::Type::Void) {
        store_variable(result, resultName);
    }
}

void methodbuilder::binary_op(BINARY_OPS op, std::string const & target, std::string const & source1, std::string const & source2, std::string const & overflow_cond) {
    if (!overflow_cond.empty() && overflow_cond.at(0) != '%')
        fatal("overflow condition must be variable");

    auto type = get_variable_type(target);
    auto llvmName = ir::type_to_llvm_name(type);

    auto in1 = load_variable(source1);
    auto in2 = load_variable(source2);
    char const * intOpName;
    char const * intrinsicName;
    char const * floatOpName;

    switch (op) {
        case ADD: intOpName =   "add"; intrinsicName =  "sadd"; floatOpName = "fadd"; break;
        case SUB: intOpName =   "sub"; intrinsicName =  "ssub"; floatOpName = "fsub"; break;
        case MUL: intOpName =   "mul"; intrinsicName =  "smul"; floatOpName = "fmul"; break;
        case DIV: intOpName =  "sdiv"; intrinsicName = nullptr; floatOpName = "fdiv"; break;
        case REM: intOpName =  "srem"; intrinsicName = nullptr; floatOpName = "frem"; break;
        default: fatal("invalid op code");
    }

    auto tempRegName = temp_register() + '_';
    auto valueName = '%' + tempRegName + "value";

    if (type.kind == ir::Type::Float) {
        out << "  " << valueName << " = " << floatOpName << ' ' << llvmName << ' ' << in1 << ", " << in2 << std::endl;
        store_variable(target, valueName);

    } else if (overflow_cond.empty() || intrinsicName == nullptr) {
        if (!overflow_cond.empty())
            fatal("overflow not valid for this case");
        out << "  " << valueName << " = " << intOpName << ' ' << llvmName << ' ' << in1 << ", " << in2 << std::endl;
        store_variable(target, valueName);

    } else {
        auto overflowName = '%' + tempRegName + "overflow";
        out << "  %" << tempRegName << "result = call {" << llvmName << ", i1} @llvm.sadd.with.overflow." << llvmName << '(' << llvmName << ' ' << in1 << ", " << llvmName << ' ' << in2 << ')' << std::endl
            << "  " << valueName << " = extractvalue {" << llvmName << ", i1} %" << tempRegName << "result, 0" << std::endl
            << "  " << overflowName << " = extractvalue {" << llvmName << ", i1} %" << tempRegName << "result, 1" << std::endl;
        store_variable(overflow_cond, overflowName);
        store_variable(target, valueName);
    }
}

void methodbuilder::bitwise_op(BITWISE_OPS op, std::string const & target, std::string const & source1, std::string const & source2) {
    auto type = get_variable_type(target);
    if (type.kind != ir::Type::Int)
        fatal("parameters must have kind int");
    auto llvmName = ir::type_to_llvm_name(type);

    auto in1 = load_variable(source1);
    auto in2 = load_variable(source2);
    auto tempRegName = '%' + temp_register();

    auto emitRotate = [&](char const * opcode) {
        out << "  " << tempRegName << " = call " << llvmName << " @llvm." << opcode << '.' << llvmName << '(' << llvmName << ' ' << in1 << ", " << llvmName << ' ' << in1 << ", " << llvmName << ' ' << in2 << ')' << std::endl;
    };

    auto emitLogic = [&](char const * opcode) {
        out << "  " << tempRegName << " = " << opcode << llvmName << ' ' << in1 << ", " << in2 << std::endl;
    };

    switch (op) {
        case ROR: emitRotate("fshr"); break;
        case ROL: emitRotate("fshl"); break;
        case AND: emitLogic("and"); break;
        case  OR: emitLogic( "or"); break;
        case XOR: emitLogic("xor"); break;
        default: fatal("invalid op code");
    }

    store_variable(target, tempRegName);
}

void methodbuilder::unary_op(UNARY_OPS op, std::string const & target, std::string const & source) {
    if (op == UNARY_OPS::MOV) {
        auto tempReg = load_variable(source);
        store_variable(target, tempReg);
    } else {
        fatal("unknown unary op");
    }
}

void methodbuilder::compare_op(COMPARE_OPS op, std::string const & target, std::string const & source1, std::string const & source2) {
    auto type = get_variable_type(target);
    if (type.kind != ir::Type::Bool)
        fatal("target must have kind bool");

    auto fc1 = source1.at(0); auto type1 = fc1!='%' && fc1!='@' ? ir::Type{.kind=ir::Type::Void} : get_variable_type(source1);
    auto fc2 = source2.at(0); auto type2 = fc2!='%' && fc2!='@' ? ir::Type{.kind=ir::Type::Void} : get_variable_type(source2);

    bool isFloat;
    std::string llvmName;
    if (type1.kind != ir::Type::Void) {
        isFloat = type1.kind == ir::Type::Float;
        llvmName = ir::type_to_llvm_name(type1);
    } else if (type2.kind != ir::Type::Void) {
        isFloat = type2.kind == ir::Type::Float;
        llvmName = ir::type_to_llvm_name(type2);
    } else {
        fatal("at least one parameter must be a variable");
    }

    char const * intOp;
    char const * floatOp;

    switch (op) {
        case EQ: intOp =  "eq"; floatOp = "oeq"; break;
        case NE: intOp =  "ne"; floatOp = "one"; break;
        case GT: intOp = "sgt"; floatOp = "ogt"; break;
        case GE: intOp = "sge"; floatOp = "oge"; break;
        case LT: intOp = "slt"; floatOp = "olt"; break;
        case LE: intOp = "sle"; floatOp = "ole"; break;
        default: fatal("invalid op code");
    }

    auto in1 = load_variable(source1);
    auto in2 = load_variable(source2);
    auto tempRegName = '%' + temp_register();

    out << "  " << tempRegName << " = ";
    if (isFloat) out << "fcmp " << floatOp;
    else out << "icmp " << intOp;

    out << ' ' << llvmName << ' ' << in1 << ", " << in2 << std::endl;
    store_variable(target, tempRegName);
}

void methodbuilder::switch_on(std::string const & condition, std::string const & label_for_default, std::vector<std::pair<int32_t, std::string>> const & labels) {
    if (label_for_default.at(0) != ':')
        fatal("invalid label");

    auto llvmName = ir::type_to_llvm_name(get_variable_type(condition));
    auto condReg = load_variable(condition);

    out << "  switch " << llvmName << ' ' << condReg << ", label %" << label_for_default.substr(1) << " [";
    for (auto [value, label] : labels) {
        if (label.at(0) != ':')
            fatal("invalid label");
        out << std::endl << "          " << llvmName << ' ' << value << ", label %" << label.substr(1) << ' ';
    }
    out << "]" << std::endl;
}

void methodbuilder::branch_if(std::string const & condition, std::string const & label_if_true, std::string const & label_if_false) {
    if (label_if_true.at(0) != ':')
        fatal("invalid label");
    if (label_if_false.at(0) != ':')
        fatal("invalid label");
    auto condReg = load_variable(condition);
    out << "  br i1 " << condReg << ", label %" << label_if_true.substr(1) << ", label %" << label_if_false.substr(1) << std::endl;
}

void methodbuilder::jump(std::string const & label) {
    if (label.at(0) != ':')
        fatal("invalid label");
    out << "  br label %" << label.substr(1) << std::endl;
}

void methodbuilder::acquire(std::string const & countRef) {
    if (countRef.empty() || countRef.at(0) != '%')
        fatal("acquire requires a pointer parameter");

    auto oldValue = '%' + temp_register();

    if (countRef.find('/') != std::string::npos) {
        auto [reg, type] = getelementptr(countRef);
        auto llvmName = ir::type_to_llvm_name(type);

        out << "  " << oldValue << " = atomicrmw add " << llvmName << "* " << reg << ", " << llvmName << " 1 seq_cst" << std::endl;

    } else {
        auto type = get_variable_type(countRef);
        if (type.kind != ir::Type::DataPointer)
            fatal("acquire requires a pointer parameter");
        if (type.members.empty())
            fatal("acquire requires a typed pointer");

        type = type.members.front();
        auto llvmName = ir::type_to_llvm_name(type);
        auto reg = load_variable(countRef);

        out << "  " << oldValue << " = atomicrmw add " << llvmName << "* " << reg << ", " << llvmName << " 1 seq_cst" << std::endl;
    }
}

void methodbuilder::release(std::string const & countRef, std::string const & zero_cond) {
    if (countRef.empty() || countRef.at(0) != '%')
        fatal("release requires a pointer parameter");

    std::string llvmName;
    auto oldValue = '%' + temp_register();

    if (countRef.find('/') != std::string::npos) {
        auto [reg, type] = getelementptr(countRef);
        llvmName = ir::type_to_llvm_name(type);

        out << "  " << oldValue << " = atomicrmw sub " << llvmName << "* " << reg << ", " << llvmName << " 1 seq_cst" << std::endl;

    } else {
        auto type = get_variable_type(countRef);
        if (type.kind != ir::Type::DataPointer)
            fatal("acquire requires a pointer parameter");
        if (type.members.empty())
            fatal("acquire requires a typed pointer");

        type = type.members.front();
        llvmName = ir::type_to_llvm_name(type);
        auto reg = load_variable(countRef);

        out << "  " << oldValue << " = atomicrmw sub " << llvmName << "* " << reg << ", " << llvmName << " 1 seq_cst" << std::endl;
    }

    auto result = '%' + temp_register();
    out << "  " << result << " = icmp eq " << llvmName << ' ' << oldValue << ", 1" << std::endl;
    store_variable(zero_cond, result);
}

void methodbuilder::malloc(std::string const & pointerVariable, ir::Type const & type, std::string const & arrayLength) {
    auto tmp1 = '%' + temp_register();
    auto tmp2 = '%' + temp_register();
    auto llvmName = ir::type_to_llvm_name(type);

    if (arrayLength.empty()) {
        out << "  " << tmp1 << " = getelementptr " << llvmName << ", " << llvmName << "* null, %size_t 1" << std::endl;
        out << "  " << tmp2 << " = ptrtoint " << llvmName << "* " << tmp1 << " to %size_t" << std::endl;

    } else {
        if (type.kind != ir::Type::Struct && type.members.back().kind != ir::Type::Array || type.members.back().size != 0)
            fatal("array allocation must be against a structured type with a final element of array length 0");

        std::string lengthLlvmName, lengthReg;
        if (arrayLength.front() == '%' || arrayLength.front() == '@') {
            lengthLlvmName = ir::type_to_llvm_name(get_variable_type(arrayLength));
            lengthReg = load_variable(arrayLength);
        } else {
            lengthLlvmName = "i32";
            lengthReg = arrayLength;
        }

        auto arrayLlvmName = ir::type_to_llvm_name(type.members.back().members.back());
        out << "  " << tmp1 << " = getelementptr " << llvmName << ", " << llvmName << "* null, %size_t 0, i32 " << (type.members.size()-1) << ", " << lengthLlvmName << ' ' << lengthReg << std::endl;
        out << "  " << tmp2 << " = ptrtoint " << arrayLlvmName << "* " << tmp1 << " to %size_t" << std::endl;
    }

    auto reg = '%' + temp_register();
    out << "  " << reg << " = call i8* @malloc(%size_t " << tmp2 << ')' << std::endl;
    store_variable(pointerVariable, reg);
}

void methodbuilder::free(std::string const & pointerVariable) {
    auto reg = load_variable(pointerVariable);
    out << "  call void @free(i8* " << reg << ')' << std::endl;
}




void methodbuilder::ret(std::string const & value) {
    if (returnType.kind == ir::Type::Void) {
        if (value != "void") fatal("return from void must be void");
        out << "  ret " << value << std::endl;
    } else {
        auto loadedValue = load_variable(value);
        auto llvmName = ir::type_to_llvm_name(returnType);
        out << "  ret " << llvmName << ' ' << loadedValue << std::endl;
    }
}

std::string methodbuilder::load(std::string const & value, ir::Type const & type) {
    auto tempRegName = '%' + temp_register();
    auto llvmName = ir::type_to_llvm_name(type);
    out << "  " << tempRegName << " = load " << llvmName << ", " << llvmName << "* " << value << std::endl;
    return tempRegName;
}

void methodbuilder::store(std::string const & targetVar, std::string const & sourceReg, ir::Type const & type) {
    if (targetVar.at(0) != '%' && targetVar.at(0) != '@')
        fatal("target must be variable");
    if (sourceReg.at(0) != '%')
        fatal("source must be register");

    auto llvmName = ir::type_to_llvm_name(type);
    out << "  store " << llvmName << " " << sourceReg << ", " << llvmName << "* " << targetVar << std::endl;
}

auto methodbuilder::get_gep_info(std::string const & input) -> gep_info {
    gep_info info;

    std::istringstream ss{input};
    for (std::string token; std::getline(ss, token, '/'); ) {
        auto firstchr = token.at(0);
        info.path.emplace_back(token, firstchr == '%' || firstchr == '@'
                                      ? get_variable_type(token)
                                      : ir::Type{.name = "i4", .size = 4, .kind = ir::Type::Int});
    }

    auto firstElement = info.path.at(0);
    info.sourceRegister = firstElement.first;
    info.sourceType = firstElement.second;
    info.path.erase(info.path.begin());

    if (info.sourceType.kind == ir::Type::DataPointer) {
        if (info.sourceType.members.empty())
            fatal("target type is required on pointer variable declaration");
        info.type = info.sourceType.members.at(0);
    } else {
        info.type = info.sourceType;
    }

    for (auto& [element, _] : info.path) {
        char firstChr = element.at(0);
        info.structs.push_back(info.type);
        ir::Type intermediateCopy;

        if (firstChr == '%' || info.type.kind == ir::Type::Array) {
            if (info.type.kind != ir::Type::Array)
                fatal("dynamic index can only be used on array");
            intermediateCopy = info.type.members.at(0);

        } else if (info.type.kind == ir::Type::Struct || info.type.kind == ir::Type::Union) {
            if (firstChr < '0' || firstChr > '9')
                fatal("invalid index value");
            size_t endOffset;
            auto number = std::stoi(element, &endOffset);
            if (number < 0 || number >= info.type.members.size() || endOffset != element.size())
                fatal("invalid index value");
            intermediateCopy = info.type.members.at(number);

        } else {
            fatal("attempt to index non structured type");
        }

        info.type = intermediateCopy; // Assigning through an intermediate variable fixes a corruption bug in C++
    }

    return info;
}

// Only used if '/' appears in token, otherwise it has confusing semantic meaning
std::pair<std::string, ir::Type> methodbuilder::getelementptr(std::string const & input) {
    auto info = get_gep_info(input);

    std::string basePtr;
    if (info.sourceType.kind == ir::Type::DataPointer) {
        basePtr = load(info.sourceRegister, info.sourceType);
    } else {
        basePtr = info.sourceRegister;
    }

    auto resultReg = '%' + temp_register();
    auto llvmName = ir::type_to_llvm_name(info.structs.at(0));

    if (basePtr.at(0) == '@')
        basePtr = bitcast(llvmName + '*', "%actual." + basePtr.substr(1) + "*", basePtr);
    else
        basePtr = bitcast(llvmName + '*', "i8*", basePtr);

    auto gep = "  " + resultReg + " = getelementptr " + llvmName + ", " + llvmName + "* " + basePtr + ", i32 0";

    for (int index = 0; index < info.path.size(); ++index) {
        auto [element, elementType] = info.path.at(index);

        if (element.at(0) == '%')
            element = load(element, elementType);
        gep += ", " + ir::type_to_llvm_name(elementType) + ' ' + element;

        if (info.structs.at(index).kind == ir::Type::Union)
            gep += ", i32 0"; // Union members are synthesized as 0 length arrays. The hack requires an extra subscript in GEP parameters.
    }

    out << gep << std::endl;

    return { resultReg, info.type };
}

std::string methodbuilder::bitcast(std::string const & targetLlvmName, std::string const & sourceLlvmName, std::string const & sourceReg) {
    auto target = '%' + temp_register();
    out << "  " << target << " = bitcast " << sourceLlvmName << ' ' << sourceReg << " to " << targetLlvmName << std::endl;
    return target;
}

std::string methodbuilder::load_variable(std::string const & reference) {
    auto firstchr = reference.at(0);
    if (firstchr != '%' && firstchr != '@') {
        return reference;
    } else if (reference.find('/') != std::string::npos) {
        auto [tmpReg, type] = getelementptr(reference);
        return load(tmpReg, type);
    } else {
        auto type = get_variable_type(reference);
        return load(reference, type);
    }
}

void methodbuilder::store_variable(std::string const & reference, std::string const & value) {
    auto firstchr = reference.at(0);
    if (firstchr != '%' && firstchr != '@') {
        fatal("target must be variable");
    } else if (reference.find('/') != std::string::npos) {
        auto [tmpReg, type] = getelementptr(reference);
        store(tmpReg, value, type);
    } else {
        auto type = get_variable_type(reference);
        store(reference, value, type);
    }
}

std::string methodbuilder::temp_register() {
    return "tmp_" + std::to_string(nextRegister++);
}


void methodbuilder::end() {
    out << "}" << std::endl;
}


