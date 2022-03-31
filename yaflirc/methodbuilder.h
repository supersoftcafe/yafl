//
// Created by Michael Brown on 15/03/2022.
//

#ifndef YAFLIRC_METHODBUILDER_H
#define YAFLIRC_METHODBUILDER_H

#include "types.h"
#include "input.h"
#include <ostream>
#include <string>
#include <tuple>
#include <vector>
#include <map>

class methodbuilder {
private:
    input& in;
    std::ostream& out;
    std::map<std::string, ir::Type> const & global_types;

    std::map<std::string, ir::Type> variables;
    std::vector<std::tuple<std::string, ir::Type>> allParamNames;
    ir::Type returnType;
    int nextRegister = 0;

    struct gep_info {
        std::vector<std::pair<std::string, ir::Type>> path;
        std::vector<ir::Type> structs;
        std::string sourceRegister;
        ir::Type sourceType { .kind = ir::Type::Void };
        ir::Type type { .kind = ir::Type::Void };
    };

    gep_info get_gep_info(std::string const & input);

    std::string load(std::string const & value, ir::Type const & type);
    void store(std::string const & targetVar, std::string const & sourceReg, ir::Type const & type);
    std::pair<std::string, ir::Type> getelementptr(std::string const & input);
    std::string bitcast(std::string const & targetLlvmName, std::string const & sourceLlvmName, std::string const & sourceReg);

    std::string load_variable(std::string const & reference);
    void store_variable(std::string const & reference, std::string const & value);

    ir::Type get_variable_type(std::string const & name);
    std::string temp_register();

public:
    methodbuilder(input& in, std::ostream& out, std::map<std::string, ir::Type> const & global_types);

    void begin_method(std::string const & name, ir::Type const & type);
    void declare_parameter(std::string const & name, ir::Type const & type);

    void begin_variables();
    void declare_variable(std::string const & name, ir::Type const & type);

    void begin_body();
    void label(std::string const & name);

    // Any binary operation that takes parameters and returns values of all the same type
    enum BINARY_OPS { ADD, SUB, MUL, DIV, REM };
    void binary_op(BINARY_OPS op, std::string const & target, std::string const & source1, std::string const & source2, std::string const & overflow_cond);

    enum BITWISE_OPS { ROL, ROR, SHL, LSHR, ASHR, AND, OR, XOR };
    void bitwise_op(BITWISE_OPS op, std::string const & target, std::string const & source1, std::string const & source2);

    enum UNARY_OPS { MOV };
    void unary_op(UNARY_OPS op, std::string const & target, std::string const & source);

    enum COMPARE_OPS { EQ, NE, GT, GE, LT, LE };
    void compare_op(COMPARE_OPS op, std::string const & target, std::string const & source1, std::string const & source2);
    void switch_on(std::string const & condition, std::string const & label_for_default, std::vector<std::pair<int32_t, std::string>> const & labels);
    void branch_if(std::string const & condition, std::string const & label_if_true, std::string const & label_if_false);
    void jump(std::string const & label);

    void acquire(std::string const & countRef);
    void release(std::string const & countRef, std::string const & zero_cond);
    void malloc(std::string const & pointerVariable, ir::Type const & type, std::string const & arrayLength);
    void free(std::string const & pointerVariable);

    void call(ir::Type const & resultType, std::string const & result,
              std::string const & method,
              std::vector<ir::Type> const & parameterTypes, std::vector<std::string> const & parameters);
    void ret(std::string const & value);

    void end();
};


#endif //YAFLIRC_METHODBUILDER_H
