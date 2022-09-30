// Generated from /home/mbrown/Projects/yafl/yaflk3/Yafl.g4 by ANTLR 4.10.1
package com.supersoftcafe.yafl.antlr;
import org.antlr.v4.runtime.tree.ParseTreeListener;

/**
 * This interface defines a complete listener for a parse tree produced by
 * {@link YaflParser}.
 */
public interface YaflListener extends ParseTreeListener {
	/**
	 * Enter a parse tree produced by {@link YaflParser#exprOfTuplePart}.
	 * @param ctx the parse tree
	 */
	void enterExprOfTuplePart(YaflParser.ExprOfTuplePartContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#exprOfTuplePart}.
	 * @param ctx the parse tree
	 */
	void exitExprOfTuplePart(YaflParser.ExprOfTuplePartContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#exprOfTuple}.
	 * @param ctx the parse tree
	 */
	void enterExprOfTuple(YaflParser.ExprOfTupleContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#exprOfTuple}.
	 * @param ctx the parse tree
	 */
	void exitExprOfTuple(YaflParser.ExprOfTupleContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#typeRef}.
	 * @param ctx the parse tree
	 */
	void enterTypeRef(YaflParser.TypeRefContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#typeRef}.
	 * @param ctx the parse tree
	 */
	void exitTypeRef(YaflParser.TypeRefContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#typeOfTuplePart}.
	 * @param ctx the parse tree
	 */
	void enterTypeOfTuplePart(YaflParser.TypeOfTuplePartContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#typeOfTuplePart}.
	 * @param ctx the parse tree
	 */
	void exitTypeOfTuplePart(YaflParser.TypeOfTuplePartContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#typeOfTuple}.
	 * @param ctx the parse tree
	 */
	void enterTypeOfTuple(YaflParser.TypeOfTupleContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#typeOfTuple}.
	 * @param ctx the parse tree
	 */
	void exitTypeOfTuple(YaflParser.TypeOfTupleContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#typeOfLambda}.
	 * @param ctx the parse tree
	 */
	void enterTypeOfLambda(YaflParser.TypeOfLambdaContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#typeOfLambda}.
	 * @param ctx the parse tree
	 */
	void exitTypeOfLambda(YaflParser.TypeOfLambdaContext ctx);
	/**
	 * Enter a parse tree produced by the {@code namedType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 */
	void enterNamedType(YaflParser.NamedTypeContext ctx);
	/**
	 * Exit a parse tree produced by the {@code namedType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 */
	void exitNamedType(YaflParser.NamedTypeContext ctx);
	/**
	 * Enter a parse tree produced by the {@code tupleType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 */
	void enterTupleType(YaflParser.TupleTypeContext ctx);
	/**
	 * Exit a parse tree produced by the {@code tupleType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 */
	void exitTupleType(YaflParser.TupleTypeContext ctx);
	/**
	 * Enter a parse tree produced by the {@code lambdaType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 */
	void enterLambdaType(YaflParser.LambdaTypeContext ctx);
	/**
	 * Exit a parse tree produced by the {@code lambdaType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 */
	void exitLambdaType(YaflParser.LambdaTypeContext ctx);
	/**
	 * Enter a parse tree produced by the {@code dotExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterDotExpr(YaflParser.DotExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code dotExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitDotExpr(YaflParser.DotExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code applyExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterApplyExpr(YaflParser.ApplyExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code applyExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitApplyExpr(YaflParser.ApplyExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code objectExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterObjectExpr(YaflParser.ObjectExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code objectExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitObjectExpr(YaflParser.ObjectExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code integerExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterIntegerExpr(YaflParser.IntegerExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code integerExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitIntegerExpr(YaflParser.IntegerExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code nameExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterNameExpr(YaflParser.NameExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code nameExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitNameExpr(YaflParser.NameExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code stringExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterStringExpr(YaflParser.StringExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code stringExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitStringExpr(YaflParser.StringExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code productExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterProductExpr(YaflParser.ProductExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code productExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitProductExpr(YaflParser.ProductExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code sumExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterSumExpr(YaflParser.SumExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code sumExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitSumExpr(YaflParser.SumExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code lambdaExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterLambdaExpr(YaflParser.LambdaExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code lambdaExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitLambdaExpr(YaflParser.LambdaExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code ifExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterIfExpr(YaflParser.IfExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code ifExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitIfExpr(YaflParser.IfExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code tupleExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterTupleExpr(YaflParser.TupleExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code tupleExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitTupleExpr(YaflParser.TupleExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code callExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterCallExpr(YaflParser.CallExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code callExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitCallExpr(YaflParser.CallExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code compareExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterCompareExpr(YaflParser.CompareExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code compareExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitCompareExpr(YaflParser.CompareExprContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#module}.
	 * @param ctx the parse tree
	 */
	void enterModule(YaflParser.ModuleContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#module}.
	 * @param ctx the parse tree
	 */
	void exitModule(YaflParser.ModuleContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#using}.
	 * @param ctx the parse tree
	 */
	void enterUsing(YaflParser.UsingContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#using}.
	 * @param ctx the parse tree
	 */
	void exitUsing(YaflParser.UsingContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#function}.
	 * @param ctx the parse tree
	 */
	void enterFunction(YaflParser.FunctionContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#function}.
	 * @param ctx the parse tree
	 */
	void exitFunction(YaflParser.FunctionContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#letWithExpr}.
	 * @param ctx the parse tree
	 */
	void enterLetWithExpr(YaflParser.LetWithExprContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#letWithExpr}.
	 * @param ctx the parse tree
	 */
	void exitLetWithExpr(YaflParser.LetWithExprContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#interface}.
	 * @param ctx the parse tree
	 */
	void enterInterface(YaflParser.InterfaceContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#interface}.
	 * @param ctx the parse tree
	 */
	void exitInterface(YaflParser.InterfaceContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#class}.
	 * @param ctx the parse tree
	 */
	void enterClass(YaflParser.ClassContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#class}.
	 * @param ctx the parse tree
	 */
	void exitClass(YaflParser.ClassContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#struct}.
	 * @param ctx the parse tree
	 */
	void enterStruct(YaflParser.StructContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#struct}.
	 * @param ctx the parse tree
	 */
	void exitStruct(YaflParser.StructContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#enum}.
	 * @param ctx the parse tree
	 */
	void enterEnum(YaflParser.EnumContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#enum}.
	 * @param ctx the parse tree
	 */
	void exitEnum(YaflParser.EnumContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#declaration}.
	 * @param ctx the parse tree
	 */
	void enterDeclaration(YaflParser.DeclarationContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#declaration}.
	 * @param ctx the parse tree
	 */
	void exitDeclaration(YaflParser.DeclarationContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#root}.
	 * @param ctx the parse tree
	 */
	void enterRoot(YaflParser.RootContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#root}.
	 * @param ctx the parse tree
	 */
	void exitRoot(YaflParser.RootContext ctx);
}