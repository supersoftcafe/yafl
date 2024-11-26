
using System
using System.Collections.Generic

namespace Ast;


enum Op : char {
    MUL = '*'
    DIV = '/'

};


public abstract class Expression()
public record BinaryOp(Expression left, Op op, Expression right) : Expression()
public record Tuple(List<(string? name, Expression value)> values) : Expression()


