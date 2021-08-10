// Generated from /Users/mbrown/Projects/my/yafl/compiler/src/yafl.g4 by ANTLR 4.9.1
import org.antlr.v4.runtime.tree.ParseTreeListener;

/**
 * This interface defines a complete listener for a parse tree produced by
 * {@link yaflParser}.
 */
public interface yaflListener extends ParseTreeListener {
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
	 * Enter a parse tree produced by {@link yaflParser#parameters}.
	 * @param ctx the parse tree
	 */
	void enterParameters(yaflParser.ParametersContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#parameters}.
	 * @param ctx the parse tree
	 */
	void exitParameters(yaflParser.ParametersContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#types}.
	 * @param ctx the parse tree
	 */
	void enterTypes(yaflParser.TypesContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#types}.
	 * @param ctx the parse tree
	 */
	void exitTypes(yaflParser.TypesContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#named}.
	 * @param ctx the parse tree
	 */
	void enterNamed(yaflParser.NamedContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#named}.
	 * @param ctx the parse tree
	 */
	void exitNamed(yaflParser.NamedContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#tuple}.
	 * @param ctx the parse tree
	 */
	void enterTuple(yaflParser.TupleContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#tuple}.
	 * @param ctx the parse tree
	 */
	void exitTuple(yaflParser.TupleContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#function}.
	 * @param ctx the parse tree
	 */
	void enterFunction(yaflParser.FunctionContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#function}.
	 * @param ctx the parse tree
	 */
	void exitFunction(yaflParser.FunctionContext ctx);
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
	 * Enter a parse tree produced by {@link yaflParser#funDecl}.
	 * @param ctx the parse tree
	 */
	void enterFunDecl(yaflParser.FunDeclContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#funDecl}.
	 * @param ctx the parse tree
	 */
	void exitFunDecl(yaflParser.FunDeclContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#funBody}.
	 * @param ctx the parse tree
	 */
	void enterFunBody(yaflParser.FunBodyContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#funBody}.
	 * @param ctx the parse tree
	 */
	void exitFunBody(yaflParser.FunBodyContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#let}.
	 * @param ctx the parse tree
	 */
	void enterLet(yaflParser.LetContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#let}.
	 * @param ctx the parse tree
	 */
	void exitLet(yaflParser.LetContext ctx);
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
	 * Enter a parse tree produced by {@link yaflParser#clazz}.
	 * @param ctx the parse tree
	 */
	void enterClazz(yaflParser.ClazzContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#clazz}.
	 * @param ctx the parse tree
	 */
	void exitClazz(yaflParser.ClazzContext ctx);
	/**
	 * Enter a parse tree produced by {@link yaflParser#clazzBody}.
	 * @param ctx the parse tree
	 */
	void enterClazzBody(yaflParser.ClazzBodyContext ctx);
	/**
	 * Exit a parse tree produced by {@link yaflParser#clazzBody}.
	 * @param ctx the parse tree
	 */
	void exitClazzBody(yaflParser.ClazzBodyContext ctx);
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