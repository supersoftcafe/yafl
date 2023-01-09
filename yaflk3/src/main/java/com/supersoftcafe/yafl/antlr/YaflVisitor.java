// Generated from /Users/mbrown/Projects/yafl/yaflk3/Yafl.g4 by ANTLR 4.10.1
package com.supersoftcafe.yafl.antlr;
import org.antlr.v4.runtime.tree.ParseTreeVisitor;

/**
 * This interface defines a complete generic visitor for a parse tree produced
 * by {@link YaflParser}.
 *
 * @param <T> The return type of the visit operation. Use {@link Void} for
 * operations with no return type.
 */
public interface YaflVisitor<T> extends ParseTreeVisitor<T> {
	/**
	 * Visit a parse tree produced by {@link YaflParser#qualifiedName}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitQualifiedName(YaflParser.QualifiedNameContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#exprOfTuplePart}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitExprOfTuplePart(YaflParser.ExprOfTuplePartContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#exprOfTuple}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitExprOfTuple(YaflParser.ExprOfTupleContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#typeRef}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTypeRef(YaflParser.TypeRefContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#typePrimitive}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTypePrimitive(YaflParser.TypePrimitiveContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#typeOfTuplePart}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTypeOfTuplePart(YaflParser.TypeOfTuplePartContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#typeOfTuple}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTypeOfTuple(YaflParser.TypeOfTupleContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#typeOfLambda}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTypeOfLambda(YaflParser.TypeOfLambdaContext ctx);
	/**
	 * Visit a parse tree produced by the {@code namedType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNamedType(YaflParser.NamedTypeContext ctx);
	/**
	 * Visit a parse tree produced by the {@code lambdaType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitLambdaType(YaflParser.LambdaTypeContext ctx);
	/**
	 * Visit a parse tree produced by the {@code arrayType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitArrayType(YaflParser.ArrayTypeContext ctx);
	/**
	 * Visit a parse tree produced by the {@code tupleType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTupleType(YaflParser.TupleTypeContext ctx);
	/**
	 * Visit a parse tree produced by the {@code primitiveType}
	 * labeled alternative in {@link YaflParser#type}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitPrimitiveType(YaflParser.PrimitiveTypeContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#attributes}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitAttributes(YaflParser.AttributesContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#unpackTuplePart}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitUnpackTuplePart(YaflParser.UnpackTuplePartContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#unpackTuple}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitUnpackTuple(YaflParser.UnpackTupleContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#letWithExpr}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitLetWithExpr(YaflParser.LetWithExprContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#function}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitFunction(YaflParser.FunctionContext ctx);
	/**
	 * Visit a parse tree produced by the {@code dotExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitDotExpr(YaflParser.DotExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code applyExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitApplyExpr(YaflParser.ApplyExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code objectExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitObjectExpr(YaflParser.ObjectExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code integerExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitIntegerExpr(YaflParser.IntegerExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code letExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitLetExpr(YaflParser.LetExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code nameExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNameExpr(YaflParser.NameExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code bitXorExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitBitXorExpr(YaflParser.BitXorExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code functionExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitFunctionExpr(YaflParser.FunctionExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code shiftExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitShiftExpr(YaflParser.ShiftExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code stringExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitStringExpr(YaflParser.StringExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code bitOrExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitBitOrExpr(YaflParser.BitOrExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code unaryExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitUnaryExpr(YaflParser.UnaryExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code productExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitProductExpr(YaflParser.ProductExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code sumExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitSumExpr(YaflParser.SumExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code llvmirExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitLlvmirExpr(YaflParser.LlvmirExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code lambdaExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitLambdaExpr(YaflParser.LambdaExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code ifExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitIfExpr(YaflParser.IfExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code arrayLookupExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitArrayLookupExpr(YaflParser.ArrayLookupExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code tupleExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitTupleExpr(YaflParser.TupleExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code bitAndExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitBitAndExpr(YaflParser.BitAndExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code callExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitCallExpr(YaflParser.CallExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code newArrayExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitNewArrayExpr(YaflParser.NewArrayExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code compareExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitCompareExpr(YaflParser.CompareExprContext ctx);
	/**
	 * Visit a parse tree produced by the {@code equalExpr}
	 * labeled alternative in {@link YaflParser#expression}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitEqualExpr(YaflParser.EqualExprContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#extends}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitExtends(YaflParser.ExtendsContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#module}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitModule(YaflParser.ModuleContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#import_}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitImport_(YaflParser.Import_Context ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#interface}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitInterface(YaflParser.InterfaceContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#class}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitClass(YaflParser.ClassContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#enum}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitEnum(YaflParser.EnumContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#alias}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitAlias(YaflParser.AliasContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#declaration}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitDeclaration(YaflParser.DeclarationContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#classMember}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitClassMember(YaflParser.ClassMemberContext ctx);
	/**
	 * Visit a parse tree produced by {@link YaflParser#root}.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	T visitRoot(YaflParser.RootContext ctx);
}