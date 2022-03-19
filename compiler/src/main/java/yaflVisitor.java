// Generated from /Users/mbrown/Projects/my/yafl/compiler/src/yafl.g4 by ANTLR 4.9.2
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
	 * Visit a parse tree produced by {@link yaflParser#simpleTypeName}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitSimpleTypeName(yaflParser.SimpleTypeNameContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#genericParams}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitGenericParams(yaflParser.GenericParamsContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#namedType}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNamedType(yaflParser.NamedTypeContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#tupleType}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTupleType(yaflParser.TupleTypeContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#type}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitType(yaflParser.TypeContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#parameter}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitParameter(yaflParser.ParameterContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#whereExpr}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitWhereExpr(yaflParser.WhereExprContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#alias}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitAlias(yaflParser.AliasContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#var}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitVar(yaflParser.VarContext ctx);
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
	 * Visit a parse tree produced by {@link yaflParser#namedParams}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNamedParams(yaflParser.NamedParamsContext ctx);
	/**
	 * Visit a parse tree produced by the {@code compareExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitCompareExpression(yaflParser.CompareExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code dotExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitDotExpression(yaflParser.DotExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code stringExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitStringExpression(yaflParser.StringExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code namedValueExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNamedValueExpression(yaflParser.NamedValueExpressionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code addExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitAddExpression(yaflParser.AddExpressionContext ctx);
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
	 * Visit a parse tree produced by {@link yaflParser#module}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitModule(yaflParser.ModuleContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#imports}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitImports(yaflParser.ImportsContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#modules}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitModules(yaflParser.ModulesContext ctx);
	/**
	 * Visit a parse tree produced by {@link yaflParser#root}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitRoot(yaflParser.RootContext ctx);
}