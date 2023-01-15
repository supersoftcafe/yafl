// Generated from /Users/mbrown/Projects/yafl/yaflk3/Yafl.g4 by ANTLR 4.10.1
package com.supersoftcafe.yafl.antlr;
import org.antlr.v4.runtime.tree.ParseTreeListener;

/**
 * This interface defines a complete listener for a parse tree produced by
 * {@link YaflParser}.
 */
public interface YaflListener extends ParseTreeListener {
	/**
	 * Enter a parse tree produced by {@link YaflParser#qualifiedName}.
	 * @param ctx the parse tree
	 */
	void enterQualifiedName(YaflParser.QualifiedNameContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#qualifiedName}.
	 * @param ctx the parse tree
	 */
	void exitQualifiedName(YaflParser.QualifiedNameContext ctx);
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
	 * Enter a parse tree produced by {@link YaflParser#typePrimitive}.
	 * @param ctx the parse tree
	 */
	void enterTypePrimitive(YaflParser.TypePrimitiveContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#typePrimitive}.
	 * @param ctx the parse tree
	 */
	void exitTypePrimitive(YaflParser.TypePrimitiveContext ctx);
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
	 * Enter a parse tree produced by the {@code primitiveType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 */
	void enterPrimitiveType(YaflParser.PrimitiveTypeContext ctx);
	/**
	 * Exit a parse tree produced by the {@code primitiveType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 */
	void exitPrimitiveType(YaflParser.PrimitiveTypeContext ctx);
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
	 * Enter a parse tree produced by {@link YaflParser#attributes}.
	 * @param ctx the parse tree
	 */
	void enterAttributes(YaflParser.AttributesContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#attributes}.
	 * @param ctx the parse tree
	 */
	void exitAttributes(YaflParser.AttributesContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#unpackTuplePart}.
	 * @param ctx the parse tree
	 */
	void enterUnpackTuplePart(YaflParser.UnpackTuplePartContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#unpackTuplePart}.
	 * @param ctx the parse tree
	 */
	void exitUnpackTuplePart(YaflParser.UnpackTuplePartContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#unpackTuple}.
	 * @param ctx the parse tree
	 */
	void enterUnpackTuple(YaflParser.UnpackTupleContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#unpackTuple}.
	 * @param ctx the parse tree
	 */
	void exitUnpackTuple(YaflParser.UnpackTupleContext ctx);
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
	 * Enter a parse tree produced by the {@code assertExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterAssertExpr(YaflParser.AssertExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code assertExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitAssertExpr(YaflParser.AssertExprContext ctx);
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
	 * Enter a parse tree produced by the {@code letExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterLetExpr(YaflParser.LetExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code letExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitLetExpr(YaflParser.LetExprContext ctx);
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
	 * Enter a parse tree produced by the {@code bitXorExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterBitXorExpr(YaflParser.BitXorExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code bitXorExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitBitXorExpr(YaflParser.BitXorExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code functionExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterFunctionExpr(YaflParser.FunctionExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code functionExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitFunctionExpr(YaflParser.FunctionExprContext ctx);
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
	 * Enter a parse tree produced by the {@code unaryExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterUnaryExpr(YaflParser.UnaryExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code unaryExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitUnaryExpr(YaflParser.UnaryExprContext ctx);
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
	 * Enter a parse tree produced by the {@code bitAndExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterBitAndExpr(YaflParser.BitAndExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code bitAndExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitBitAndExpr(YaflParser.BitAndExprContext ctx);
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
	 * Enter a parse tree produced by the {@code newArrayExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterNewArrayExpr(YaflParser.NewArrayExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code newArrayExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitNewArrayExpr(YaflParser.NewArrayExprContext ctx);
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
	 * Enter a parse tree produced by the {@code shiftExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterShiftExpr(YaflParser.ShiftExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code shiftExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitShiftExpr(YaflParser.ShiftExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code bitOrExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterBitOrExpr(YaflParser.BitOrExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code bitOrExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitBitOrExpr(YaflParser.BitOrExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code llvmirExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterLlvmirExpr(YaflParser.LlvmirExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code llvmirExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitLlvmirExpr(YaflParser.LlvmirExprContext ctx);
	/**
	 * Enter a parse tree produced by the {@code arrayLookupExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterArrayLookupExpr(YaflParser.ArrayLookupExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code arrayLookupExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitArrayLookupExpr(YaflParser.ArrayLookupExprContext ctx);
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
	 * Enter a parse tree produced by the {@code equalExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void enterEqualExpr(YaflParser.EqualExprContext ctx);
	/**
	 * Exit a parse tree produced by the {@code equalExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 */
	void exitEqualExpr(YaflParser.EqualExprContext ctx);
	/**
	 * Enter a parse tree produced by {@link YaflParser#extends}.
	 * @param ctx the parse tree
	 */
	void enterExtends(YaflParser.ExtendsContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#extends}.
	 * @param ctx the parse tree
	 */
	void exitExtends(YaflParser.ExtendsContext ctx);
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
	 * Enter a parse tree produced by {@link YaflParser#import_}.
	 * @param ctx the parse tree
	 */
	void enterImport_(YaflParser.Import_Context ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#import_}.
	 * @param ctx the parse tree
	 */
	void exitImport_(YaflParser.Import_Context ctx);
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
	 * Enter a parse tree produced by {@link YaflParser#alias}.
	 * @param ctx the parse tree
	 */
	void enterAlias(YaflParser.AliasContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#alias}.
	 * @param ctx the parse tree
	 */
	void exitAlias(YaflParser.AliasContext ctx);
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
	 * Enter a parse tree produced by {@link YaflParser#classMember}.
	 * @param ctx the parse tree
	 */
	void enterClassMember(YaflParser.ClassMemberContext ctx);
	/**
	 * Exit a parse tree produced by {@link YaflParser#classMember}.
	 * @param ctx the parse tree
	 */
	void exitClassMember(YaflParser.ClassMemberContext ctx);
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