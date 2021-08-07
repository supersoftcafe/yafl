package converter

import model.*
import java.lang.IllegalArgumentException


//fun yaflParser.LetContext.toModel(): Declaration.Let {
//    return Declaration.Let(NAME().text, expression().toModel())
//}
//
//fun yaflParser.FunctionContext.toModel(): Type.Function {
//    return Type.Function(tuple().toModel(), type().toModel())
//}
//
//fun yaflParser.TupleContext.toModel(): Type.Tuple {
//    return Type.Tuple(parameters().toModel())
//}

//fun yaflParser.NamedContext.toModel(): Type.Named {
//    val tail = named()?.toModel()
//    val fqn = listOf(NAME().text) + (tail?.fqn ?: emptyList())
//    return when (fqn.joinToString(".")) {
//        "int" -> BuiltInTypes.int
//        "long" -> BuiltInTypes.long
//        "float" -> BuiltInTypes.float
//        "double" -> BuiltInTypes.double
//        else -> Type.Named(fqn)
//    }
//}

//fun yaflParser.TypeContext.toModel(): Type {
//    return function()?.toModel() ?: tuple()?.toModel() ?: named().toModel()
//}
//
//fun yaflParser.ParameterContext.toModel(): Parameter {
//    return Parameter(NAME().text, type()?.toModel(), expression()?.toModel())
//}
//
//fun yaflParser.ParametersContext.toModel(): List<Parameter> {
//    val head = parameter().toModel()
//    return listOf(head) + (parameters()?.toModel() ?: emptyList())
//}
//
//fun yaflParser.FunContext.toModel(): Declaration.Fun {
//    val decl = funDecl()
//    val body = funBody()
//    val codeBlock = Expression.CodeBlock(body.statements()?.toModel() ?: emptyList(), body.expression().toModel())
//    return Declaration.Fun(decl.NAME().text, decl.tuple()?.toModel(), decl.type().toModel(), codeBlock)
//}
//
//fun String.toOperator(): Operator {
//    return when (this) {
//        "*" -> Operator.MULTIPLY
//        "/" -> Operator.DIVIDE
//        "%" -> Operator.MODULUS
//        "+" -> Operator.ADD
//        "-" -> Operator.SUBTRACT
//        else -> throw IllegalArgumentException()
//    }
//}
//
//fun yaflParser.StatementsContext.toModel(): List<Declaration> {
//    val head = let()?.toModel() ?: `fun`().toModel()
//    return listOf(head) + (statements()?.toModel() ?: emptyList())
//}
//
//fun yaflParser.CodeBlockContext.toModel(): Expression.CodeBlock {
//    return Expression.CodeBlock(statements()?.toModel() ?: emptyList(), expression().toModel())
//}
//
//fun yaflParser.NamedParamsContext.toModel(): List<NamedParam> {
//    val tail = namedParams()?.toModel() ?: emptyList()
//    return listOf(NamedParam(NAME().text, expression().toModel())) + tail
//}
//
//fun yaflParser.ExpressionContext.toModel(): Expression {
//    return when (this) {
//        is yaflParser.DotExpressionContext -> Expression.Dot(expression().toModel(), NAME().text)
//        is yaflParser.MulExpressionContext -> Expression.BinaryOp(MULTDIV().text.toOperator(), expression(0).toModel(), expression(1).toModel())
//        is yaflParser.AddExpressionContext -> Expression.BinaryOp(ADDSUB().text.toOperator(), expression(0).toModel(), expression(1).toModel())
//        is yaflParser.IfExpressionContext -> Expression.If(expression().toModel(), codeBlock(0).toModel(), codeBlock(1).toModel())
//        is yaflParser.ParenthesisedExpressionContext -> codeBlock().toModel()
//        is yaflParser.InvokeExpressionContext -> Expression.Invoke(expression().toModel(), namedParams().toModel())
//        is yaflParser.IntegerExpressionContext -> Expression.IntLiteral(java.lang.Integer.decode(INTEGER().text))
//        is yaflParser.NamedContext -> Expression.Named(NAME().text)
//        else -> throw IllegalArgumentException()
//    }
//}
//
//fun yaflParser.DeclarationsContext.toModel(): List<Declaration> {
//    val tail = declarations()?.toModel() ?: emptyList()
//    return listOf(let()?.toModel() ?: `fun`().toModel()) + tail
//}
//
//fun yaflParser.RootContext.toModel(): Root {
//    return Root( declarations()?.toModel() ?: emptyList() )
//}