// Generated from /Users/mbrown/Projects/my/yaflc/src/yafl.g4 by ANTLR 4.9.1
import org.antlr.v4.runtime.tree.ParseTreeVisitor;

/**
 * This interface defines a complete generic visitor for a parse tree produced
 * by {@link yaflParser}.
 *
 * @param <T> The return type of the visit operation. Use {@link Void} for
 * operations with no return type.
 */
public interface yaflVisitor<T> extends ParseTreeVisitor<T> {
	/**
	 * Visit a parse tree produced by {@link yaflParser#parameter}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitParameter(yaflParser.ParameterContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#parameters}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitParameters(yaflParser.ParametersContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#types}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTypes(yaflParser.TypesContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#named}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNamed(yaflParser.NamedContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#tuple}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTuple(yaflParser.TupleContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#function}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitFunction(yaflParser.FunctionContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#type}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitType(yaflParser.TypeContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#funDecl}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitFunDecl(yaflParser.FunDeclContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#funBody}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitFunBody(yaflParser.FunBodyContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#let}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitLet(yaflParser.LetContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#fun}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitFun(yaflParser.FunContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#data}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitData(yaflParser.DataContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#clazz}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitClazz(yaflParser.ClazzContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#clazzBody}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitClazzBody(yaflParser.ClazzBodyContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#namedParams}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNamedParams(yaflParser.NamedParamsContext ctx);
	/**
	 * Visit a parse tree produced by the {@code dotExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitDotExpression(yaflParser.DotExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code addExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitAddExpression(yaflParser.AddExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code namedValue}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNamedValue(yaflParser.NamedValueContext ctx);
	/**
	 * Visit a parse tree produced by the {@code ifExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitIfExpression(yaflParser.IfExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code integerExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitIntegerExpression(yaflParser.IntegerExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code invokeExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitInvokeExpression(yaflParser.InvokeExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code parenthesisedExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitParenthesisedExpression(yaflParser.ParenthesisedExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code mulExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitMulExpression(yaflParser.MulExpressionContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#codeBlock}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitCodeBlock(yaflParser.CodeBlockContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#statements}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitStatements(yaflParser.StatementsContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#declarations}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitDeclarations(yaflParser.DeclarationsContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#root}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitRoot(yaflParser.RootContext ctx);
}