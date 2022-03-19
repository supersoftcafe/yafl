// Generated from /Users/mbrown/Projects/my/yafl/compiler/src/yafl.g4 by ANTLR 4.9.2
import org.antlr.v4.runtime.tree.ParseTreeListener;

/**
 * This interface defines a complete listener for a parse tree produced by
 * {@link yaflParser}.
 */
public interface yaflListener extends ParseTreeListener {
	/**
	 * Enter a parse tree produced by {@link yaflParser#simpleTypeName}.
	 * @param ctx the parse tree
	 */
	void enterSimpleTypeName(yaflParser.SimpleTypeNameContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#simpleTypeName}.
	 * @param ctx the parse tree
	 */
	void exitSimpleTypeName(yaflParser.SimpleTypeNameContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#genericParams}.
	 * @param ctx the parse tree
	 */
	void enterGenericParams(yaflParser.GenericParamsContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#genericParams}.
	 * @param ctx the parse tree
	 */
	void exitGenericParams(yaflParser.GenericParamsContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#namedType}.
	 * @param ctx the parse tree
	 */
	void enterNamedType(yaflParser.NamedTypeContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#namedType}.
	 * @param ctx the parse tree
	 */
	void exitNamedType(yaflParser.NamedTypeContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#tupleType}.
	 * @param ctx the parse tree
	 */
	void enterTupleType(yaflParser.TupleTypeContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#tupleType}.
	 * @param ctx the parse tree
	 */
	void exitTupleType(yaflParser.TupleTypeContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#type}.
	 * @param ctx the parse tree
	 */
	void enterType(yaflParser.TypeContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#type}.
	 * @param ctx the parse tree
	 */
	void exitType(yaflParser.TypeContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#parameter}.
	 * @param ctx the parse tree
	 */
	void enterParameter(yaflParser.ParameterContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#parameter}.
	 * @param ctx the parse tree
	 */
	void exitParameter(yaflParser.ParameterContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#whereExpr}.
	 * @param ctx the parse tree
	 */
	void enterWhereExpr(yaflParser.WhereExprContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#whereExpr}.
	 * @param ctx the parse tree
	 */
	void exitWhereExpr(yaflParser.WhereExprContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#alias}.
	 * @param ctx the parse tree
	 */
	void enterAlias(yaflParser.AliasContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#alias}.
	 * @param ctx the parse tree
	 */
	void exitAlias(yaflParser.AliasContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#var}.
	 * @param ctx the parse tree
	 */
	void enterVar(yaflParser.VarContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#var}.
	 * @param ctx the parse tree
	 */
	void exitVar(yaflParser.VarContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#fun}.
	 * @param ctx the parse tree
	 */
	void enterFun(yaflParser.FunContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#fun}.
	 * @param ctx the parse tree
	 */
	void exitFun(yaflParser.FunContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#data}.
	 * @param ctx the parse tree
	 */
	void enterData(yaflParser.DataContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#data}.
	 * @param ctx the parse tree
	 */
	void exitData(yaflParser.DataContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#namedParams}.
	 * @param ctx the parse tree
	 */
	void enterNamedParams(yaflParser.NamedParamsContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#namedParams}.
	 * @param ctx the parse tree
	 */
	void exitNamedParams(yaflParser.NamedParamsContext ctx);
	/**
	 * Enter a parse tree produced by the {@code compareExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterCompareExpression(yaflParser.CompareExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code compareExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitCompareExpression(yaflParser.CompareExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code dotExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterDotExpression(yaflParser.DotExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code dotExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitDotExpression(yaflParser.DotExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code stringExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterStringExpression(yaflParser.StringExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code stringExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitStringExpression(yaflParser.StringExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code namedValueExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterNamedValueExpression(yaflParser.NamedValueExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code namedValueExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitNamedValueExpression(yaflParser.NamedValueExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code addExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterAddExpression(yaflParser.AddExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code addExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitAddExpression(yaflParser.AddExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code ifExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterIfExpression(yaflParser.IfExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code ifExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitIfExpression(yaflParser.IfExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code integerExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterIntegerExpression(yaflParser.IntegerExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code integerExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitIntegerExpression(yaflParser.IntegerExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code invokeExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterInvokeExpression(yaflParser.InvokeExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code invokeExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitInvokeExpression(yaflParser.InvokeExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code parenthesisedExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterParenthesisedExpression(yaflParser.ParenthesisedExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code parenthesisedExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitParenthesisedExpression(yaflParser.ParenthesisedExpressionContext ctx);
	/**
	 * Enter a parse tree produced by the {@code mulExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterMulExpression(yaflParser.MulExpressionContext ctx);
	/**
	 * Exit a parse tree produced by the {@code mulExpression}
	 * labeled alternative in {@link yaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitMulExpression(yaflParser.MulExpressionContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#codeBlock}.
	 * @param ctx the parse tree
	 */
	void enterCodeBlock(yaflParser.CodeBlockContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#codeBlock}.
	 * @param ctx the parse tree
	 */
	void exitCodeBlock(yaflParser.CodeBlockContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#statements}.
	 * @param ctx the parse tree
	 */
	void enterStatements(yaflParser.StatementsContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#statements}.
	 * @param ctx the parse tree
	 */
	void exitStatements(yaflParser.StatementsContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#declarations}.
	 * @param ctx the parse tree
	 */
	void enterDeclarations(yaflParser.DeclarationsContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#declarations}.
	 * @param ctx the parse tree
	 */
	void exitDeclarations(yaflParser.DeclarationsContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#module}.
	 * @param ctx the parse tree
	 */
	void enterModule(yaflParser.ModuleContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#module}.
	 * @param ctx the parse tree
	 */
	void exitModule(yaflParser.ModuleContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#imports}.
	 * @param ctx the parse tree
	 */
	void enterImports(yaflParser.ImportsContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#imports}.
	 * @param ctx the parse tree
	 */
	void exitImports(yaflParser.ImportsContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#modules}.
	 * @param ctx the parse tree
	 */
	void enterModules(yaflParser.ModulesContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#modules}.
	 * @param ctx the parse tree
	 */
	void exitModules(yaflParser.ModulesContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#root}.
	 * @param ctx the parse tree
	 */
	void enterRoot(yaflParser.RootContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#root}.
	 * @param ctx the parse tree
	 */
	void exitRoot(yaflParser.RootContext ctx);
}