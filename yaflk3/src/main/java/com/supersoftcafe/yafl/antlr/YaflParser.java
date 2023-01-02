// Generated from /Users/mbrown/Projects/yafl/yaflk3/Yafl.g4 by ANTLR 4.10.1
package com.supersoftcafe.yafl.antlr;
import org.antlr.v4.runtime.atn.*;
import org.antlr.v4.runtime.dfa.DFA;
import org.antlr.v4.runtime.*;
import org.antlr.v4.runtime.misc.*;
import org.antlr.v4.runtime.tree.*;
import java.util.List;
import java.util.Iterator;
import java.util.ArrayList;

@SuppressWarnings({"all", "warnings", "unchecked", "unused", "cast"})
public class YaflParser extends Parser {
	static { RuntimeMetaData.checkVersion("4.10.1", RuntimeMetaData.VERSION); }

	protected static final DFA[] _decisionToDFA;
	protected static final PredictionContextCache _sharedContextCache =
		new PredictionContextCache();
	public static final int
		T__0=1, T__1=2, T__2=3, T__3=4, T__4=5, T__5=6, T__6=7, T__7=8, T__8=9, 
		T__9=10, T__10=11, T__11=12, T__12=13, T__13=14, T__14=15, T__15=16, T__16=17, 
		T__17=18, T__18=19, T__19=20, T__20=21, BUILTIN=22, LLVM_IR=23, PRIMITIVE=24, 
		MODULE=25, IMPORT=26, ALIAS=27, FUN=28, LET=29, INTERFACE=30, CLASS=31, 
		OBJECT=32, ENUM=33, LAZY=34, LAMBDA=35, PIPE_RIGHT=36, PIPE_MAYBE=37, 
		NAMESPACE=38, CMP_LE=39, CMP_GE=40, CMP_EQ=41, CMP_NE=42, SHL=43, SHR=44, 
		NAME=45, INTEGER=46, STRING=47, WS=48, COMMENT=49;
	public static final int
		RULE_qualifiedName = 0, RULE_exprOfTuplePart = 1, RULE_exprOfTuple = 2, 
		RULE_typeRef = 3, RULE_typePrimitive = 4, RULE_typeOfTuplePart = 5, RULE_typeOfTuple = 6, 
		RULE_typeOfLambda = 7, RULE_type = 8, RULE_attributes = 9, RULE_unpackTuplePart = 10, 
		RULE_unpackTuple = 11, RULE_letWithExpr = 12, RULE_function = 13, RULE_expression = 14, 
		RULE_extends = 15, RULE_module = 16, RULE_import_ = 17, RULE_interface = 18, 
		RULE_class = 19, RULE_enum = 20, RULE_alias = 21, RULE_declaration = 22, 
		RULE_classMember = 23, RULE_root = 24;
	private static String[] makeRuleNames() {
		return new String[] {
			"qualifiedName", "exprOfTuplePart", "exprOfTuple", "typeRef", "typePrimitive", 
			"typeOfTuplePart", "typeOfTuple", "typeOfLambda", "type", "attributes", 
			"unpackTuplePart", "unpackTuple", "letWithExpr", "function", "expression", 
			"extends", "module", "import_", "interface", "class", "enum", "alias", 
			"declaration", "classMember", "root"
		};
	}
	public static final String[] ruleNames = makeRuleNames();

	private static String[] makeLiteralNames() {
		return new String[] {
			null, "'('", "','", "')'", "':'", "'['", "']'", "'<'", "'>'", "'.'", 
			"'+'", "'-'", "'*'", "'/'", "'%'", "'&'", "'^'", "'|'", "'?'", "'{'", 
			"'}'", "';'", "'__builtin__'", "'__llvm_ir__'", "'__primitive__'", "'module'", 
			"'import'", "'alias'", "'fun'", "'let'", "'interface'", "'class'", "'object'", 
			"'enum'", "'lazy'", "'=>'", "'|>'", "'?>'", null, "'<='", "'>='", "'='", 
			"'!='", "'<<'", "'>>'"
		};
	}
	private static final String[] _LITERAL_NAMES = makeLiteralNames();
	private static String[] makeSymbolicNames() {
		return new String[] {
			null, null, null, null, null, null, null, null, null, null, null, null, 
			null, null, null, null, null, null, null, null, null, null, "BUILTIN", 
			"LLVM_IR", "PRIMITIVE", "MODULE", "IMPORT", "ALIAS", "FUN", "LET", "INTERFACE", 
			"CLASS", "OBJECT", "ENUM", "LAZY", "LAMBDA", "PIPE_RIGHT", "PIPE_MAYBE", 
			"NAMESPACE", "CMP_LE", "CMP_GE", "CMP_EQ", "CMP_NE", "SHL", "SHR", "NAME", 
			"INTEGER", "STRING", "WS", "COMMENT"
		};
	}
	private static final String[] _SYMBOLIC_NAMES = makeSymbolicNames();
	public static final Vocabulary VOCABULARY = new VocabularyImpl(_LITERAL_NAMES, _SYMBOLIC_NAMES);

	/**
	 * @deprecated Use {@link #VOCABULARY} instead.
	 */
	@Deprecated
	public static final String[] tokenNames;
	static {
		tokenNames = new String[_SYMBOLIC_NAMES.length];
		for (int i = 0; i < tokenNames.length; i++) {
			tokenNames[i] = VOCABULARY.getLiteralName(i);
			if (tokenNames[i] == null) {
				tokenNames[i] = VOCABULARY.getSymbolicName(i);
			}

			if (tokenNames[i] == null) {
				tokenNames[i] = "<INVALID>";
			}
		}
	}

	@Override
	@Deprecated
	public String[] getTokenNames() {
		return tokenNames;
	}

	@Override

	public Vocabulary getVocabulary() {
		return VOCABULARY;
	}

	@Override
	public String getGrammarFileName() { return "Yafl.g4"; }

	@Override
	public String[] getRuleNames() { return ruleNames; }

	@Override
	public String getSerializedATN() { return _serializedATN; }

	@Override
	public ATN getATN() { return _ATN; }

	public YaflParser(TokenStream input) {
		super(input);
		_interp = new ParserATNSimulator(this,_ATN,_decisionToDFA,_sharedContextCache);
	}

	public static class QualifiedNameContext extends ParserRuleContext {
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public List<TerminalNode> NAMESPACE() { return getTokens(YaflParser.NAMESPACE); }
		public TerminalNode NAMESPACE(int i) {
			return getToken(YaflParser.NAMESPACE, i);
		}
		public QualifiedNameContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_qualifiedName; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterQualifiedName(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitQualifiedName(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitQualifiedName(this);
			else return visitor.visitChildren(this);
		}
	}

	public final QualifiedNameContext qualifiedName() throws RecognitionException {
		QualifiedNameContext _localctx = new QualifiedNameContext(_ctx, getState());
		enterRule(_localctx, 0, RULE_qualifiedName);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(53);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==NAMESPACE) {
				{
				{
				setState(50);
				match(NAMESPACE);
				}
				}
				setState(55);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(56);
			match(NAME);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class ExprOfTuplePartContext extends ParserRuleContext {
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TerminalNode CMP_EQ() { return getToken(YaflParser.CMP_EQ, 0); }
		public ExprOfTuplePartContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_exprOfTuplePart; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterExprOfTuplePart(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitExprOfTuplePart(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitExprOfTuplePart(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ExprOfTuplePartContext exprOfTuplePart() throws RecognitionException {
		ExprOfTuplePartContext _localctx = new ExprOfTuplePartContext(_ctx, getState());
		enterRule(_localctx, 2, RULE_exprOfTuplePart);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(60);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,1,_ctx) ) {
			case 1:
				{
				setState(58);
				match(NAME);
				setState(59);
				match(CMP_EQ);
				}
				break;
			}
			setState(62);
			expression(0);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class ExprOfTupleContext extends ParserRuleContext {
		public List<ExprOfTuplePartContext> exprOfTuplePart() {
			return getRuleContexts(ExprOfTuplePartContext.class);
		}
		public ExprOfTuplePartContext exprOfTuplePart(int i) {
			return getRuleContext(ExprOfTuplePartContext.class,i);
		}
		public ExprOfTupleContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_exprOfTuple; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterExprOfTuple(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitExprOfTuple(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitExprOfTuple(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ExprOfTupleContext exprOfTuple() throws RecognitionException {
		ExprOfTupleContext _localctx = new ExprOfTupleContext(_ctx, getState());
		enterRule(_localctx, 4, RULE_exprOfTuple);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(64);
			match(T__0);
			setState(70);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,2,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(65);
					exprOfTuplePart();
					setState(66);
					match(T__1);
					}
					} 
				}
				setState(72);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,2,_ctx);
			}
			setState(74);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__0) | (1L << T__9) | (1L << T__10) | (1L << BUILTIN) | (1L << LLVM_IR) | (1L << FUN) | (1L << LET) | (1L << OBJECT) | (1L << NAMESPACE) | (1L << NAME) | (1L << INTEGER) | (1L << STRING))) != 0)) {
				{
				setState(73);
				exprOfTuplePart();
				}
			}

			setState(76);
			match(T__2);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class TypeRefContext extends ParserRuleContext {
		public QualifiedNameContext qualifiedName() {
			return getRuleContext(QualifiedNameContext.class,0);
		}
		public TypeRefContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_typeRef; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTypeRef(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTypeRef(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTypeRef(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypeRefContext typeRef() throws RecognitionException {
		TypeRefContext _localctx = new TypeRefContext(_ctx, getState());
		enterRule(_localctx, 6, RULE_typeRef);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(78);
			qualifiedName();
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class TypePrimitiveContext extends ParserRuleContext {
		public TerminalNode PRIMITIVE() { return getToken(YaflParser.PRIMITIVE, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TypePrimitiveContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_typePrimitive; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTypePrimitive(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTypePrimitive(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTypePrimitive(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypePrimitiveContext typePrimitive() throws RecognitionException {
		TypePrimitiveContext _localctx = new TypePrimitiveContext(_ctx, getState());
		enterRule(_localctx, 8, RULE_typePrimitive);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(80);
			match(PRIMITIVE);
			setState(81);
			match(NAME);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class TypeOfTuplePartContext extends ParserRuleContext {
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TypeOfTuplePartContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_typeOfTuplePart; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTypeOfTuplePart(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTypeOfTuplePart(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTypeOfTuplePart(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypeOfTuplePartContext typeOfTuplePart() throws RecognitionException {
		TypeOfTuplePartContext _localctx = new TypeOfTuplePartContext(_ctx, getState());
		enterRule(_localctx, 10, RULE_typeOfTuplePart);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(85);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,4,_ctx) ) {
			case 1:
				{
				setState(83);
				match(NAME);
				setState(84);
				match(T__3);
				}
				break;
			}
			setState(87);
			type();
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class TypeOfTupleContext extends ParserRuleContext {
		public List<TypeOfTuplePartContext> typeOfTuplePart() {
			return getRuleContexts(TypeOfTuplePartContext.class);
		}
		public TypeOfTuplePartContext typeOfTuplePart(int i) {
			return getRuleContext(TypeOfTuplePartContext.class,i);
		}
		public TypeOfTupleContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_typeOfTuple; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTypeOfTuple(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTypeOfTuple(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTypeOfTuple(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypeOfTupleContext typeOfTuple() throws RecognitionException {
		TypeOfTupleContext _localctx = new TypeOfTupleContext(_ctx, getState());
		enterRule(_localctx, 12, RULE_typeOfTuple);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(89);
			match(T__0);
			setState(95);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,5,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(90);
					typeOfTuplePart();
					setState(91);
					match(T__1);
					}
					} 
				}
				setState(97);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,5,_ctx);
			}
			setState(99);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__0) | (1L << PRIMITIVE) | (1L << NAMESPACE) | (1L << NAME))) != 0)) {
				{
				setState(98);
				typeOfTuplePart();
				}
			}

			setState(101);
			match(T__2);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class TypeOfLambdaContext extends ParserRuleContext {
		public TypeOfTupleContext typeOfTuple() {
			return getRuleContext(TypeOfTupleContext.class,0);
		}
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public TypeOfLambdaContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_typeOfLambda; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTypeOfLambda(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTypeOfLambda(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTypeOfLambda(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypeOfLambdaContext typeOfLambda() throws RecognitionException {
		TypeOfLambdaContext _localctx = new TypeOfLambdaContext(_ctx, getState());
		enterRule(_localctx, 14, RULE_typeOfLambda);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(103);
			typeOfTuple();
			setState(104);
			match(T__3);
			setState(105);
			type();
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class TypeContext extends ParserRuleContext {
		public TypeContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_type; }
	 
		public TypeContext() { }
		public void copyFrom(TypeContext ctx) {
			super.copyFrom(ctx);
		}
	}
	public static class NamedTypeContext extends TypeContext {
		public TypeRefContext typeRef() {
			return getRuleContext(TypeRefContext.class,0);
		}
		public NamedTypeContext(TypeContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterNamedType(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitNamedType(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitNamedType(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class LambdaTypeContext extends TypeContext {
		public TypeOfLambdaContext typeOfLambda() {
			return getRuleContext(TypeOfLambdaContext.class,0);
		}
		public LambdaTypeContext(TypeContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterLambdaType(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitLambdaType(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitLambdaType(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class TupleTypeContext extends TypeContext {
		public TypeOfTupleContext typeOfTuple() {
			return getRuleContext(TypeOfTupleContext.class,0);
		}
		public TupleTypeContext(TypeContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTupleType(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTupleType(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTupleType(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class PrimitiveTypeContext extends TypeContext {
		public TypePrimitiveContext typePrimitive() {
			return getRuleContext(TypePrimitiveContext.class,0);
		}
		public PrimitiveTypeContext(TypeContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterPrimitiveType(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitPrimitiveType(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitPrimitiveType(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypeContext type() throws RecognitionException {
		TypeContext _localctx = new TypeContext(_ctx, getState());
		enterRule(_localctx, 16, RULE_type);
		try {
			setState(111);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,7,_ctx) ) {
			case 1:
				_localctx = new NamedTypeContext(_localctx);
				enterOuterAlt(_localctx, 1);
				{
				setState(107);
				typeRef();
				}
				break;
			case 2:
				_localctx = new PrimitiveTypeContext(_localctx);
				enterOuterAlt(_localctx, 2);
				{
				setState(108);
				typePrimitive();
				}
				break;
			case 3:
				_localctx = new TupleTypeContext(_localctx);
				enterOuterAlt(_localctx, 3);
				{
				setState(109);
				typeOfTuple();
				}
				break;
			case 4:
				_localctx = new LambdaTypeContext(_localctx);
				enterOuterAlt(_localctx, 4);
				{
				setState(110);
				typeOfLambda();
				}
				break;
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class AttributesContext extends ParserRuleContext {
		public List<TerminalNode> NAME() { return getTokens(YaflParser.NAME); }
		public TerminalNode NAME(int i) {
			return getToken(YaflParser.NAME, i);
		}
		public AttributesContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_attributes; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterAttributes(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitAttributes(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitAttributes(this);
			else return visitor.visitChildren(this);
		}
	}

	public final AttributesContext attributes() throws RecognitionException {
		AttributesContext _localctx = new AttributesContext(_ctx, getState());
		enterRule(_localctx, 18, RULE_attributes);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(113);
			match(T__4);
			setState(117);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==NAME) {
				{
				{
				setState(114);
				match(NAME);
				}
				}
				setState(119);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(120);
			match(T__5);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class UnpackTuplePartContext extends ParserRuleContext {
		public UnpackTupleContext unpackTuple() {
			return getRuleContext(UnpackTupleContext.class,0);
		}
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public TerminalNode CMP_EQ() { return getToken(YaflParser.CMP_EQ, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public UnpackTuplePartContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_unpackTuplePart; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterUnpackTuplePart(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitUnpackTuplePart(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitUnpackTuplePart(this);
			else return visitor.visitChildren(this);
		}
	}

	public final UnpackTuplePartContext unpackTuplePart() throws RecognitionException {
		UnpackTuplePartContext _localctx = new UnpackTuplePartContext(_ctx, getState());
		enterRule(_localctx, 20, RULE_unpackTuplePart);
		int _la;
		try {
			setState(132);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case T__0:
				enterOuterAlt(_localctx, 1);
				{
				setState(122);
				unpackTuple();
				}
				break;
			case NAME:
				enterOuterAlt(_localctx, 2);
				{
				{
				setState(123);
				match(NAME);
				setState(126);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__3) {
					{
					setState(124);
					match(T__3);
					setState(125);
					type();
					}
				}

				setState(130);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==CMP_EQ) {
					{
					setState(128);
					match(CMP_EQ);
					setState(129);
					expression(0);
					}
				}

				}
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class UnpackTupleContext extends ParserRuleContext {
		public List<UnpackTuplePartContext> unpackTuplePart() {
			return getRuleContexts(UnpackTuplePartContext.class);
		}
		public UnpackTuplePartContext unpackTuplePart(int i) {
			return getRuleContext(UnpackTuplePartContext.class,i);
		}
		public UnpackTupleContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_unpackTuple; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterUnpackTuple(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitUnpackTuple(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitUnpackTuple(this);
			else return visitor.visitChildren(this);
		}
	}

	public final UnpackTupleContext unpackTuple() throws RecognitionException {
		UnpackTupleContext _localctx = new UnpackTupleContext(_ctx, getState());
		enterRule(_localctx, 22, RULE_unpackTuple);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(134);
			match(T__0);
			setState(140);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,12,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(135);
					unpackTuplePart();
					setState(136);
					match(T__1);
					}
					} 
				}
				setState(142);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,12,_ctx);
			}
			setState(144);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__0 || _la==NAME) {
				{
				setState(143);
				unpackTuplePart();
				}
			}

			setState(146);
			match(T__2);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class LetWithExprContext extends ParserRuleContext {
		public TerminalNode LET() { return getToken(YaflParser.LET, 0); }
		public TerminalNode CMP_EQ() { return getToken(YaflParser.CMP_EQ, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public UnpackTupleContext unpackTuple() {
			return getRuleContext(UnpackTupleContext.class,0);
		}
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public LetWithExprContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_letWithExpr; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterLetWithExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitLetWithExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitLetWithExpr(this);
			else return visitor.visitChildren(this);
		}
	}

	public final LetWithExprContext letWithExpr() throws RecognitionException {
		LetWithExprContext _localctx = new LetWithExprContext(_ctx, getState());
		enterRule(_localctx, 24, RULE_letWithExpr);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(148);
			match(LET);
			setState(155);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case T__0:
				{
				setState(149);
				unpackTuple();
				}
				break;
			case NAME:
				{
				{
				setState(150);
				match(NAME);
				setState(153);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__3) {
					{
					setState(151);
					match(T__3);
					setState(152);
					type();
					}
				}

				}
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
			setState(157);
			match(CMP_EQ);
			setState(158);
			expression(0);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class FunctionContext extends ParserRuleContext {
		public TerminalNode FUN() { return getToken(YaflParser.FUN, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public AttributesContext attributes() {
			return getRuleContext(AttributesContext.class,0);
		}
		public UnpackTupleContext unpackTuple() {
			return getRuleContext(UnpackTupleContext.class,0);
		}
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public TerminalNode LAMBDA() { return getToken(YaflParser.LAMBDA, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public FunctionContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_function; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterFunction(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitFunction(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitFunction(this);
			else return visitor.visitChildren(this);
		}
	}

	public final FunctionContext function() throws RecognitionException {
		FunctionContext _localctx = new FunctionContext(_ctx, getState());
		enterRule(_localctx, 26, RULE_function);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(160);
			match(FUN);
			setState(162);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(161);
				attributes();
				}
			}

			setState(164);
			match(NAME);
			setState(166);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,17,_ctx) ) {
			case 1:
				{
				setState(165);
				unpackTuple();
				}
				break;
			}
			setState(170);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__3) {
				{
				setState(168);
				match(T__3);
				setState(169);
				type();
				}
			}

			setState(174);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==LAMBDA) {
				{
				setState(172);
				match(LAMBDA);
				setState(173);
				expression(0);
				}
			}

			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class ExpressionContext extends ParserRuleContext {
		public ExpressionContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_expression; }
	 
		public ExpressionContext() { }
		public void copyFrom(ExpressionContext ctx) {
			super.copyFrom(ctx);
		}
	}
	public static class DotExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public Token right;
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public DotExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterDotExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitDotExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitDotExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class ApplyExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public ExprOfTupleContext params;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public ExprOfTupleContext exprOfTuple() {
			return getRuleContext(ExprOfTupleContext.class,0);
		}
		public TerminalNode PIPE_RIGHT() { return getToken(YaflParser.PIPE_RIGHT, 0); }
		public TerminalNode PIPE_MAYBE() { return getToken(YaflParser.PIPE_MAYBE, 0); }
		public ApplyExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterApplyExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitApplyExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitApplyExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class BuiltinExprContext extends ExpressionContext {
		public ExprOfTupleContext params;
		public TerminalNode BUILTIN() { return getToken(YaflParser.BUILTIN, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public ExprOfTupleContext exprOfTuple() {
			return getRuleContext(ExprOfTupleContext.class,0);
		}
		public BuiltinExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterBuiltinExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitBuiltinExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitBuiltinExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class ObjectExprContext extends ExpressionContext {
		public TerminalNode OBJECT() { return getToken(YaflParser.OBJECT, 0); }
		public List<TypeRefContext> typeRef() {
			return getRuleContexts(TypeRefContext.class);
		}
		public TypeRefContext typeRef(int i) {
			return getRuleContext(TypeRefContext.class,i);
		}
		public List<FunctionContext> function() {
			return getRuleContexts(FunctionContext.class);
		}
		public FunctionContext function(int i) {
			return getRuleContext(FunctionContext.class,i);
		}
		public ObjectExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterObjectExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitObjectExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitObjectExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class IntegerExprContext extends ExpressionContext {
		public TerminalNode INTEGER() { return getToken(YaflParser.INTEGER, 0); }
		public IntegerExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterIntegerExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitIntegerExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitIntegerExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class LetExprContext extends ExpressionContext {
		public LetWithExprContext letWithExpr() {
			return getRuleContext(LetWithExprContext.class,0);
		}
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public LetExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterLetExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitLetExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitLetExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class NameExprContext extends ExpressionContext {
		public QualifiedNameContext qualifiedName() {
			return getRuleContext(QualifiedNameContext.class,0);
		}
		public NameExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterNameExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitNameExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitNameExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class BitXorExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public BitXorExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterBitXorExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitBitXorExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitBitXorExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class FunctionExprContext extends ExpressionContext {
		public FunctionContext function() {
			return getRuleContext(FunctionContext.class,0);
		}
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public FunctionExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterFunctionExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitFunctionExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitFunctionExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class ShiftExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public TerminalNode SHL() { return getToken(YaflParser.SHL, 0); }
		public TerminalNode SHR() { return getToken(YaflParser.SHR, 0); }
		public ShiftExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterShiftExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitShiftExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitShiftExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class StringExprContext extends ExpressionContext {
		public TerminalNode STRING() { return getToken(YaflParser.STRING, 0); }
		public StringExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterStringExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitStringExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitStringExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class BitOrExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public BitOrExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterBitOrExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitBitOrExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitBitOrExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class UnaryExprContext extends ExpressionContext {
		public Token operator;
		public ExpressionContext right;
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public UnaryExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterUnaryExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitUnaryExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitUnaryExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class ProductExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public ProductExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterProductExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitProductExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitProductExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class SumExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public SumExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterSumExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitSumExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitSumExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class LlvmirExprContext extends ExpressionContext {
		public Token pattern;
		public TerminalNode LLVM_IR() { return getToken(YaflParser.LLVM_IR, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public TerminalNode STRING() { return getToken(YaflParser.STRING, 0); }
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public LlvmirExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterLlvmirExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitLlvmirExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitLlvmirExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class LambdaExprContext extends ExpressionContext {
		public UnpackTupleContext unpackTuple() {
			return getRuleContext(UnpackTupleContext.class,0);
		}
		public TerminalNode LAMBDA() { return getToken(YaflParser.LAMBDA, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public LambdaExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterLambdaExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitLambdaExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitLambdaExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class IfExprContext extends ExpressionContext {
		public ExpressionContext condition;
		public ExpressionContext left;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public IfExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterIfExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitIfExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitIfExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class TupleExprContext extends ExpressionContext {
		public ExprOfTupleContext exprOfTuple() {
			return getRuleContext(ExprOfTupleContext.class,0);
		}
		public TupleExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTupleExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTupleExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTupleExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class BitAndExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public BitAndExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterBitAndExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitBitAndExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitBitAndExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class CallExprContext extends ExpressionContext {
		public ExpressionContext left;
		public ExprOfTupleContext params;
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public ExprOfTupleContext exprOfTuple() {
			return getRuleContext(ExprOfTupleContext.class,0);
		}
		public CallExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterCallExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitCallExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitCallExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class CompareExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public TerminalNode CMP_LE() { return getToken(YaflParser.CMP_LE, 0); }
		public TerminalNode CMP_GE() { return getToken(YaflParser.CMP_GE, 0); }
		public CompareExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterCompareExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitCompareExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitCompareExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class EqualExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public TerminalNode CMP_EQ() { return getToken(YaflParser.CMP_EQ, 0); }
		public TerminalNode CMP_NE() { return getToken(YaflParser.CMP_NE, 0); }
		public EqualExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterEqualExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitEqualExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitEqualExpr(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ExpressionContext expression() throws RecognitionException {
		return expression(0);
	}

	private ExpressionContext expression(int _p) throws RecognitionException {
		ParserRuleContext _parentctx = _ctx;
		int _parentState = getState();
		ExpressionContext _localctx = new ExpressionContext(_ctx, _parentState);
		ExpressionContext _prevctx = _localctx;
		int _startState = 28;
		enterRecursionRule(_localctx, 28, RULE_expression, _p);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(243);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,28,_ctx) ) {
			case 1:
				{
				_localctx = new BuiltinExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;

				setState(177);
				match(BUILTIN);
				setState(178);
				match(NAME);
				setState(180);
				_errHandler.sync(this);
				switch ( getInterpreter().adaptivePredict(_input,20,_ctx) ) {
				case 1:
					{
					setState(179);
					((BuiltinExprContext)_localctx).params = exprOfTuple();
					}
					break;
				}
				}
				break;
			case 2:
				{
				_localctx = new LlvmirExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(182);
				match(LLVM_IR);
				setState(183);
				match(T__6);
				setState(184);
				type();
				setState(185);
				match(T__7);
				setState(186);
				match(T__0);
				setState(187);
				((LlvmirExprContext)_localctx).pattern = match(STRING);
				setState(192);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==T__1) {
					{
					{
					setState(188);
					match(T__1);
					setState(189);
					expression(0);
					}
					}
					setState(194);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(195);
				match(T__2);
				}
				break;
			case 3:
				{
				_localctx = new UnaryExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(197);
				((UnaryExprContext)_localctx).operator = _input.LT(1);
				_la = _input.LA(1);
				if ( !(_la==T__9 || _la==T__10) ) {
					((UnaryExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
				}
				else {
					if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
					_errHandler.reportMatch(this);
					consume();
				}
				setState(198);
				((UnaryExprContext)_localctx).right = expression(18);
				}
				break;
			case 4:
				{
				_localctx = new TupleExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(199);
				exprOfTuple();
				}
				break;
			case 5:
				{
				_localctx = new ObjectExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(200);
				match(OBJECT);
				setState(201);
				match(T__3);
				setState(202);
				typeRef();
				setState(207);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,22,_ctx);
				while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
					if ( _alt==1 ) {
						{
						{
						setState(203);
						match(T__16);
						setState(204);
						typeRef();
						}
						} 
					}
					setState(209);
					_errHandler.sync(this);
					_alt = getInterpreter().adaptivePredict(_input,22,_ctx);
				}
				setState(218);
				_errHandler.sync(this);
				switch ( getInterpreter().adaptivePredict(_input,24,_ctx) ) {
				case 1:
					{
					setState(210);
					match(T__18);
					setState(214);
					_errHandler.sync(this);
					_la = _input.LA(1);
					while (_la==FUN) {
						{
						{
						setState(211);
						function();
						}
						}
						setState(216);
						_errHandler.sync(this);
						_la = _input.LA(1);
					}
					setState(217);
					match(T__19);
					}
					break;
				}
				}
				break;
			case 6:
				{
				_localctx = new LetExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(220);
				letWithExpr();
				setState(222);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__20) {
					{
					setState(221);
					match(T__20);
					}
				}

				setState(224);
				expression(6);
				}
				break;
			case 7:
				{
				_localctx = new FunctionExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(226);
				function();
				setState(228);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__20) {
					{
					setState(227);
					match(T__20);
					}
				}

				setState(230);
				expression(5);
				}
				break;
			case 8:
				{
				_localctx = new LambdaExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(232);
				unpackTuple();
				setState(235);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__3) {
					{
					setState(233);
					match(T__3);
					setState(234);
					type();
					}
				}

				setState(237);
				match(LAMBDA);
				setState(238);
				expression(4);
				}
				break;
			case 9:
				{
				_localctx = new StringExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(240);
				match(STRING);
				}
				break;
			case 10:
				{
				_localctx = new IntegerExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(241);
				match(INTEGER);
				}
				break;
			case 11:
				{
				_localctx = new NameExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(242);
				qualifiedName();
				}
				break;
			}
			_ctx.stop = _input.LT(-1);
			setState(287);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,30,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					if ( _parseListeners!=null ) triggerExitRuleEvent();
					_prevctx = _localctx;
					{
					setState(285);
					_errHandler.sync(this);
					switch ( getInterpreter().adaptivePredict(_input,29,_ctx) ) {
					case 1:
						{
						_localctx = new ProductExprContext(new ExpressionContext(_parentctx, _parentState));
						((ProductExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(245);
						if (!(precpred(_ctx, 17))) throw new FailedPredicateException(this, "precpred(_ctx, 17)");
						setState(246);
						((ProductExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__11) | (1L << T__12) | (1L << T__13))) != 0)) ) {
							((ProductExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(247);
						((ProductExprContext)_localctx).right = expression(18);
						}
						break;
					case 2:
						{
						_localctx = new SumExprContext(new ExpressionContext(_parentctx, _parentState));
						((SumExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(248);
						if (!(precpred(_ctx, 16))) throw new FailedPredicateException(this, "precpred(_ctx, 16)");
						setState(249);
						((SumExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !(_la==T__9 || _la==T__10) ) {
							((SumExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(250);
						((SumExprContext)_localctx).right = expression(17);
						}
						break;
					case 3:
						{
						_localctx = new ShiftExprContext(new ExpressionContext(_parentctx, _parentState));
						((ShiftExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(251);
						if (!(precpred(_ctx, 15))) throw new FailedPredicateException(this, "precpred(_ctx, 15)");
						setState(252);
						((ShiftExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !(_la==SHL || _la==SHR) ) {
							((ShiftExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(253);
						((ShiftExprContext)_localctx).right = expression(16);
						}
						break;
					case 4:
						{
						_localctx = new CompareExprContext(new ExpressionContext(_parentctx, _parentState));
						((CompareExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(254);
						if (!(precpred(_ctx, 14))) throw new FailedPredicateException(this, "precpred(_ctx, 14)");
						setState(255);
						((CompareExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__6) | (1L << T__7) | (1L << CMP_LE) | (1L << CMP_GE))) != 0)) ) {
							((CompareExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(256);
						((CompareExprContext)_localctx).right = expression(15);
						}
						break;
					case 5:
						{
						_localctx = new EqualExprContext(new ExpressionContext(_parentctx, _parentState));
						((EqualExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(257);
						if (!(precpred(_ctx, 13))) throw new FailedPredicateException(this, "precpred(_ctx, 13)");
						setState(258);
						((EqualExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !(_la==CMP_EQ || _la==CMP_NE) ) {
							((EqualExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(259);
						((EqualExprContext)_localctx).right = expression(14);
						}
						break;
					case 6:
						{
						_localctx = new BitAndExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitAndExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(260);
						if (!(precpred(_ctx, 12))) throw new FailedPredicateException(this, "precpred(_ctx, 12)");
						setState(261);
						((BitAndExprContext)_localctx).operator = match(T__14);
						setState(262);
						((BitAndExprContext)_localctx).right = expression(13);
						}
						break;
					case 7:
						{
						_localctx = new BitXorExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitXorExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(263);
						if (!(precpred(_ctx, 11))) throw new FailedPredicateException(this, "precpred(_ctx, 11)");
						setState(264);
						((BitXorExprContext)_localctx).operator = match(T__15);
						setState(265);
						((BitXorExprContext)_localctx).right = expression(12);
						}
						break;
					case 8:
						{
						_localctx = new BitOrExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitOrExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(266);
						if (!(precpred(_ctx, 10))) throw new FailedPredicateException(this, "precpred(_ctx, 10)");
						setState(267);
						((BitOrExprContext)_localctx).operator = match(T__16);
						setState(268);
						((BitOrExprContext)_localctx).right = expression(11);
						}
						break;
					case 9:
						{
						_localctx = new IfExprContext(new ExpressionContext(_parentctx, _parentState));
						((IfExprContext)_localctx).condition = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(269);
						if (!(precpred(_ctx, 9))) throw new FailedPredicateException(this, "precpred(_ctx, 9)");
						setState(270);
						match(T__17);
						setState(271);
						((IfExprContext)_localctx).left = expression(0);
						setState(272);
						match(T__3);
						setState(273);
						((IfExprContext)_localctx).right = expression(10);
						}
						break;
					case 10:
						{
						_localctx = new DotExprContext(new ExpressionContext(_parentctx, _parentState));
						((DotExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(275);
						if (!(precpred(_ctx, 21))) throw new FailedPredicateException(this, "precpred(_ctx, 21)");
						setState(276);
						((DotExprContext)_localctx).operator = match(T__8);
						setState(277);
						((DotExprContext)_localctx).right = match(NAME);
						}
						break;
					case 11:
						{
						_localctx = new CallExprContext(new ExpressionContext(_parentctx, _parentState));
						((CallExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(278);
						if (!(precpred(_ctx, 20))) throw new FailedPredicateException(this, "precpred(_ctx, 20)");
						setState(279);
						((CallExprContext)_localctx).params = exprOfTuple();
						}
						break;
					case 12:
						{
						_localctx = new ApplyExprContext(new ExpressionContext(_parentctx, _parentState));
						((ApplyExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(280);
						if (!(precpred(_ctx, 19))) throw new FailedPredicateException(this, "precpred(_ctx, 19)");
						setState(281);
						((ApplyExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !(_la==PIPE_RIGHT || _la==PIPE_MAYBE) ) {
							((ApplyExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(282);
						((ApplyExprContext)_localctx).right = expression(0);
						setState(283);
						((ApplyExprContext)_localctx).params = exprOfTuple();
						}
						break;
					}
					} 
				}
				setState(289);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,30,_ctx);
			}
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			unrollRecursionContexts(_parentctx);
		}
		return _localctx;
	}

	public static class ExtendsContext extends ParserRuleContext {
		public List<TypeRefContext> typeRef() {
			return getRuleContexts(TypeRefContext.class);
		}
		public TypeRefContext typeRef(int i) {
			return getRuleContext(TypeRefContext.class,i);
		}
		public ExtendsContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_extends; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterExtends(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitExtends(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitExtends(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ExtendsContext extends_() throws RecognitionException {
		ExtendsContext _localctx = new ExtendsContext(_ctx, getState());
		enterRule(_localctx, 30, RULE_extends);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(290);
			match(T__3);
			setState(291);
			typeRef();
			setState(296);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==T__1) {
				{
				{
				setState(292);
				match(T__1);
				setState(293);
				typeRef();
				}
				}
				setState(298);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class ModuleContext extends ParserRuleContext {
		public TerminalNode MODULE() { return getToken(YaflParser.MODULE, 0); }
		public TypeRefContext typeRef() {
			return getRuleContext(TypeRefContext.class,0);
		}
		public ModuleContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_module; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterModule(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitModule(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitModule(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ModuleContext module() throws RecognitionException {
		ModuleContext _localctx = new ModuleContext(_ctx, getState());
		enterRule(_localctx, 32, RULE_module);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(299);
			match(MODULE);
			setState(300);
			typeRef();
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class Import_Context extends ParserRuleContext {
		public TerminalNode IMPORT() { return getToken(YaflParser.IMPORT, 0); }
		public TypeRefContext typeRef() {
			return getRuleContext(TypeRefContext.class,0);
		}
		public Import_Context(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_import_; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterImport_(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitImport_(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitImport_(this);
			else return visitor.visitChildren(this);
		}
	}

	public final Import_Context import_() throws RecognitionException {
		Import_Context _localctx = new Import_Context(_ctx, getState());
		enterRule(_localctx, 34, RULE_import_);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(302);
			match(IMPORT);
			setState(303);
			typeRef();
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class InterfaceContext extends ParserRuleContext {
		public TerminalNode INTERFACE() { return getToken(YaflParser.INTERFACE, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public ExtendsContext extends_() {
			return getRuleContext(ExtendsContext.class,0);
		}
		public List<FunctionContext> function() {
			return getRuleContexts(FunctionContext.class);
		}
		public FunctionContext function(int i) {
			return getRuleContext(FunctionContext.class,i);
		}
		public InterfaceContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_interface; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterInterface(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitInterface(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitInterface(this);
			else return visitor.visitChildren(this);
		}
	}

	public final InterfaceContext interface_() throws RecognitionException {
		InterfaceContext _localctx = new InterfaceContext(_ctx, getState());
		enterRule(_localctx, 36, RULE_interface);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(305);
			match(INTERFACE);
			setState(306);
			match(NAME);
			setState(308);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__3) {
				{
				setState(307);
				extends_();
				}
			}

			setState(318);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__18) {
				{
				setState(310);
				match(T__18);
				setState(314);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN) {
					{
					{
					setState(311);
					function();
					}
					}
					setState(316);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(317);
				match(T__19);
				}
			}

			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class ClassContext extends ParserRuleContext {
		public TerminalNode CLASS() { return getToken(YaflParser.CLASS, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public UnpackTupleContext unpackTuple() {
			return getRuleContext(UnpackTupleContext.class,0);
		}
		public ExtendsContext extends_() {
			return getRuleContext(ExtendsContext.class,0);
		}
		public List<ClassMemberContext> classMember() {
			return getRuleContexts(ClassMemberContext.class);
		}
		public ClassMemberContext classMember(int i) {
			return getRuleContext(ClassMemberContext.class,i);
		}
		public ClassContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_class; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterClass(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitClass(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitClass(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ClassContext class_() throws RecognitionException {
		ClassContext _localctx = new ClassContext(_ctx, getState());
		enterRule(_localctx, 38, RULE_class);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(320);
			match(CLASS);
			setState(321);
			match(NAME);
			setState(323);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__0) {
				{
				setState(322);
				unpackTuple();
				}
			}

			setState(326);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__3) {
				{
				setState(325);
				extends_();
				}
			}

			setState(336);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__18) {
				{
				setState(328);
				match(T__18);
				setState(332);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN) {
					{
					{
					setState(329);
					classMember();
					}
					}
					setState(334);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(335);
				match(T__19);
				}
			}

			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class EnumContext extends ParserRuleContext {
		public TerminalNode ENUM() { return getToken(YaflParser.ENUM, 0); }
		public List<TerminalNode> NAME() { return getTokens(YaflParser.NAME); }
		public TerminalNode NAME(int i) {
			return getToken(YaflParser.NAME, i);
		}
		public List<FunctionContext> function() {
			return getRuleContexts(FunctionContext.class);
		}
		public FunctionContext function(int i) {
			return getRuleContext(FunctionContext.class,i);
		}
		public List<UnpackTupleContext> unpackTuple() {
			return getRuleContexts(UnpackTupleContext.class);
		}
		public UnpackTupleContext unpackTuple(int i) {
			return getRuleContext(UnpackTupleContext.class,i);
		}
		public EnumContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_enum; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterEnum(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitEnum(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitEnum(this);
			else return visitor.visitChildren(this);
		}
	}

	public final EnumContext enum_() throws RecognitionException {
		EnumContext _localctx = new EnumContext(_ctx, getState());
		enterRule(_localctx, 40, RULE_enum);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(338);
			match(ENUM);
			setState(339);
			match(NAME);
			setState(352);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__18) {
				{
				setState(340);
				match(T__18);
				setState(348);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN || _la==NAME) {
					{
					setState(346);
					_errHandler.sync(this);
					switch (_input.LA(1)) {
					case NAME:
						{
						{
						setState(341);
						match(NAME);
						setState(343);
						_errHandler.sync(this);
						_la = _input.LA(1);
						if (_la==T__0) {
							{
							setState(342);
							unpackTuple();
							}
						}

						}
						}
						break;
					case FUN:
						{
						setState(345);
						function();
						}
						break;
					default:
						throw new NoViableAltException(this);
					}
					}
					setState(350);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(351);
				match(T__19);
				}
			}

			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class AliasContext extends ParserRuleContext {
		public TerminalNode ALIAS() { return getToken(YaflParser.ALIAS, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public AliasContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_alias; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterAlias(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitAlias(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitAlias(this);
			else return visitor.visitChildren(this);
		}
	}

	public final AliasContext alias() throws RecognitionException {
		AliasContext _localctx = new AliasContext(_ctx, getState());
		enterRule(_localctx, 42, RULE_alias);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(354);
			match(ALIAS);
			setState(355);
			match(NAME);
			setState(356);
			match(T__3);
			setState(357);
			type();
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class DeclarationContext extends ParserRuleContext {
		public LetWithExprContext letWithExpr() {
			return getRuleContext(LetWithExprContext.class,0);
		}
		public FunctionContext function() {
			return getRuleContext(FunctionContext.class,0);
		}
		public InterfaceContext interface_() {
			return getRuleContext(InterfaceContext.class,0);
		}
		public ClassContext class_() {
			return getRuleContext(ClassContext.class,0);
		}
		public EnumContext enum_() {
			return getRuleContext(EnumContext.class,0);
		}
		public AliasContext alias() {
			return getRuleContext(AliasContext.class,0);
		}
		public DeclarationContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_declaration; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterDeclaration(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitDeclaration(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitDeclaration(this);
			else return visitor.visitChildren(this);
		}
	}

	public final DeclarationContext declaration() throws RecognitionException {
		DeclarationContext _localctx = new DeclarationContext(_ctx, getState());
		enterRule(_localctx, 44, RULE_declaration);
		try {
			setState(365);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case LET:
				enterOuterAlt(_localctx, 1);
				{
				setState(359);
				letWithExpr();
				}
				break;
			case FUN:
				enterOuterAlt(_localctx, 2);
				{
				setState(360);
				function();
				}
				break;
			case INTERFACE:
				enterOuterAlt(_localctx, 3);
				{
				setState(361);
				interface_();
				}
				break;
			case CLASS:
				enterOuterAlt(_localctx, 4);
				{
				setState(362);
				class_();
				}
				break;
			case ENUM:
				enterOuterAlt(_localctx, 5);
				{
				setState(363);
				enum_();
				}
				break;
			case ALIAS:
				enterOuterAlt(_localctx, 6);
				{
				setState(364);
				alias();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class ClassMemberContext extends ParserRuleContext {
		public FunctionContext function() {
			return getRuleContext(FunctionContext.class,0);
		}
		public ClassMemberContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_classMember; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterClassMember(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitClassMember(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitClassMember(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ClassMemberContext classMember() throws RecognitionException {
		ClassMemberContext _localctx = new ClassMemberContext(_ctx, getState());
		enterRule(_localctx, 46, RULE_classMember);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(367);
			function();
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class RootContext extends ParserRuleContext {
		public ModuleContext module() {
			return getRuleContext(ModuleContext.class,0);
		}
		public TerminalNode EOF() { return getToken(YaflParser.EOF, 0); }
		public List<Import_Context> import_() {
			return getRuleContexts(Import_Context.class);
		}
		public Import_Context import_(int i) {
			return getRuleContext(Import_Context.class,i);
		}
		public List<DeclarationContext> declaration() {
			return getRuleContexts(DeclarationContext.class);
		}
		public DeclarationContext declaration(int i) {
			return getRuleContext(DeclarationContext.class,i);
		}
		public RootContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_root; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterRoot(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitRoot(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitRoot(this);
			else return visitor.visitChildren(this);
		}
	}

	public final RootContext root() throws RecognitionException {
		RootContext _localctx = new RootContext(_ctx, getState());
		enterRule(_localctx, 48, RULE_root);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(369);
			module();
			setState(373);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==IMPORT) {
				{
				{
				setState(370);
				import_();
				}
				}
				setState(375);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(379);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << ALIAS) | (1L << FUN) | (1L << LET) | (1L << INTERFACE) | (1L << CLASS) | (1L << ENUM))) != 0)) {
				{
				{
				setState(376);
				declaration();
				}
				}
				setState(381);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(382);
			match(EOF);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public boolean sempred(RuleContext _localctx, int ruleIndex, int predIndex) {
		switch (ruleIndex) {
		case 14:
			return expression_sempred((ExpressionContext)_localctx, predIndex);
		}
		return true;
	}
	private boolean expression_sempred(ExpressionContext _localctx, int predIndex) {
		switch (predIndex) {
		case 0:
			return precpred(_ctx, 17);
		case 1:
			return precpred(_ctx, 16);
		case 2:
			return precpred(_ctx, 15);
		case 3:
			return precpred(_ctx, 14);
		case 4:
			return precpred(_ctx, 13);
		case 5:
			return precpred(_ctx, 12);
		case 6:
			return precpred(_ctx, 11);
		case 7:
			return precpred(_ctx, 10);
		case 8:
			return precpred(_ctx, 9);
		case 9:
			return precpred(_ctx, 21);
		case 10:
			return precpred(_ctx, 20);
		case 11:
			return precpred(_ctx, 19);
		}
		return true;
	}

	public static final String _serializedATN =
		"\u0004\u00011\u0181\u0002\u0000\u0007\u0000\u0002\u0001\u0007\u0001\u0002"+
		"\u0002\u0007\u0002\u0002\u0003\u0007\u0003\u0002\u0004\u0007\u0004\u0002"+
		"\u0005\u0007\u0005\u0002\u0006\u0007\u0006\u0002\u0007\u0007\u0007\u0002"+
		"\b\u0007\b\u0002\t\u0007\t\u0002\n\u0007\n\u0002\u000b\u0007\u000b\u0002"+
		"\f\u0007\f\u0002\r\u0007\r\u0002\u000e\u0007\u000e\u0002\u000f\u0007\u000f"+
		"\u0002\u0010\u0007\u0010\u0002\u0011\u0007\u0011\u0002\u0012\u0007\u0012"+
		"\u0002\u0013\u0007\u0013\u0002\u0014\u0007\u0014\u0002\u0015\u0007\u0015"+
		"\u0002\u0016\u0007\u0016\u0002\u0017\u0007\u0017\u0002\u0018\u0007\u0018"+
		"\u0001\u0000\u0005\u00004\b\u0000\n\u0000\f\u00007\t\u0000\u0001\u0000"+
		"\u0001\u0000\u0001\u0001\u0001\u0001\u0003\u0001=\b\u0001\u0001\u0001"+
		"\u0001\u0001\u0001\u0002\u0001\u0002\u0001\u0002\u0001\u0002\u0005\u0002"+
		"E\b\u0002\n\u0002\f\u0002H\t\u0002\u0001\u0002\u0003\u0002K\b\u0002\u0001"+
		"\u0002\u0001\u0002\u0001\u0003\u0001\u0003\u0001\u0004\u0001\u0004\u0001"+
		"\u0004\u0001\u0005\u0001\u0005\u0003\u0005V\b\u0005\u0001\u0005\u0001"+
		"\u0005\u0001\u0006\u0001\u0006\u0001\u0006\u0001\u0006\u0005\u0006^\b"+
		"\u0006\n\u0006\f\u0006a\t\u0006\u0001\u0006\u0003\u0006d\b\u0006\u0001"+
		"\u0006\u0001\u0006\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001"+
		"\b\u0001\b\u0001\b\u0001\b\u0003\bp\b\b\u0001\t\u0001\t\u0005\tt\b\t\n"+
		"\t\f\tw\t\t\u0001\t\u0001\t\u0001\n\u0001\n\u0001\n\u0001\n\u0003\n\u007f"+
		"\b\n\u0001\n\u0001\n\u0003\n\u0083\b\n\u0003\n\u0085\b\n\u0001\u000b\u0001"+
		"\u000b\u0001\u000b\u0001\u000b\u0005\u000b\u008b\b\u000b\n\u000b\f\u000b"+
		"\u008e\t\u000b\u0001\u000b\u0003\u000b\u0091\b\u000b\u0001\u000b\u0001"+
		"\u000b\u0001\f\u0001\f\u0001\f\u0001\f\u0001\f\u0003\f\u009a\b\f\u0003"+
		"\f\u009c\b\f\u0001\f\u0001\f\u0001\f\u0001\r\u0001\r\u0003\r\u00a3\b\r"+
		"\u0001\r\u0001\r\u0003\r\u00a7\b\r\u0001\r\u0001\r\u0003\r\u00ab\b\r\u0001"+
		"\r\u0001\r\u0003\r\u00af\b\r\u0001\u000e\u0001\u000e\u0001\u000e\u0001"+
		"\u000e\u0003\u000e\u00b5\b\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001"+
		"\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0005\u000e\u00bf"+
		"\b\u000e\n\u000e\f\u000e\u00c2\t\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0005\u000e\u00ce\b\u000e\n\u000e\f\u000e\u00d1\t\u000e\u0001"+
		"\u000e\u0001\u000e\u0005\u000e\u00d5\b\u000e\n\u000e\f\u000e\u00d8\t\u000e"+
		"\u0001\u000e\u0003\u000e\u00db\b\u000e\u0001\u000e\u0001\u000e\u0003\u000e"+
		"\u00df\b\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0003\u000e"+
		"\u00e5\b\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0003\u000e\u00ec\b\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0003\u000e\u00f4\b\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0005\u000e\u011e\b\u000e\n\u000e\f\u000e\u0121"+
		"\t\u000e\u0001\u000f\u0001\u000f\u0001\u000f\u0001\u000f\u0005\u000f\u0127"+
		"\b\u000f\n\u000f\f\u000f\u012a\t\u000f\u0001\u0010\u0001\u0010\u0001\u0010"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0012\u0001\u0012\u0001\u0012"+
		"\u0003\u0012\u0135\b\u0012\u0001\u0012\u0001\u0012\u0005\u0012\u0139\b"+
		"\u0012\n\u0012\f\u0012\u013c\t\u0012\u0001\u0012\u0003\u0012\u013f\b\u0012"+
		"\u0001\u0013\u0001\u0013\u0001\u0013\u0003\u0013\u0144\b\u0013\u0001\u0013"+
		"\u0003\u0013\u0147\b\u0013\u0001\u0013\u0001\u0013\u0005\u0013\u014b\b"+
		"\u0013\n\u0013\f\u0013\u014e\t\u0013\u0001\u0013\u0003\u0013\u0151\b\u0013"+
		"\u0001\u0014\u0001\u0014\u0001\u0014\u0001\u0014\u0001\u0014\u0003\u0014"+
		"\u0158\b\u0014\u0001\u0014\u0005\u0014\u015b\b\u0014\n\u0014\f\u0014\u015e"+
		"\t\u0014\u0001\u0014\u0003\u0014\u0161\b\u0014\u0001\u0015\u0001\u0015"+
		"\u0001\u0015\u0001\u0015\u0001\u0015\u0001\u0016\u0001\u0016\u0001\u0016"+
		"\u0001\u0016\u0001\u0016\u0001\u0016\u0003\u0016\u016e\b\u0016\u0001\u0017"+
		"\u0001\u0017\u0001\u0018\u0001\u0018\u0005\u0018\u0174\b\u0018\n\u0018"+
		"\f\u0018\u0177\t\u0018\u0001\u0018\u0005\u0018\u017a\b\u0018\n\u0018\f"+
		"\u0018\u017d\t\u0018\u0001\u0018\u0001\u0018\u0001\u0018\u0000\u0001\u001c"+
		"\u0019\u0000\u0002\u0004\u0006\b\n\f\u000e\u0010\u0012\u0014\u0016\u0018"+
		"\u001a\u001c\u001e \"$&(*,.0\u0000\u0006\u0001\u0000\n\u000b\u0001\u0000"+
		"\f\u000e\u0001\u0000+,\u0002\u0000\u0007\b\'(\u0001\u0000)*\u0001\u0000"+
		"$%\u01ae\u00005\u0001\u0000\u0000\u0000\u0002<\u0001\u0000\u0000\u0000"+
		"\u0004@\u0001\u0000\u0000\u0000\u0006N\u0001\u0000\u0000\u0000\bP\u0001"+
		"\u0000\u0000\u0000\nU\u0001\u0000\u0000\u0000\fY\u0001\u0000\u0000\u0000"+
		"\u000eg\u0001\u0000\u0000\u0000\u0010o\u0001\u0000\u0000\u0000\u0012q"+
		"\u0001\u0000\u0000\u0000\u0014\u0084\u0001\u0000\u0000\u0000\u0016\u0086"+
		"\u0001\u0000\u0000\u0000\u0018\u0094\u0001\u0000\u0000\u0000\u001a\u00a0"+
		"\u0001\u0000\u0000\u0000\u001c\u00f3\u0001\u0000\u0000\u0000\u001e\u0122"+
		"\u0001\u0000\u0000\u0000 \u012b\u0001\u0000\u0000\u0000\"\u012e\u0001"+
		"\u0000\u0000\u0000$\u0131\u0001\u0000\u0000\u0000&\u0140\u0001\u0000\u0000"+
		"\u0000(\u0152\u0001\u0000\u0000\u0000*\u0162\u0001\u0000\u0000\u0000,"+
		"\u016d\u0001\u0000\u0000\u0000.\u016f\u0001\u0000\u0000\u00000\u0171\u0001"+
		"\u0000\u0000\u000024\u0005&\u0000\u000032\u0001\u0000\u0000\u000047\u0001"+
		"\u0000\u0000\u000053\u0001\u0000\u0000\u000056\u0001\u0000\u0000\u0000"+
		"68\u0001\u0000\u0000\u000075\u0001\u0000\u0000\u000089\u0005-\u0000\u0000"+
		"9\u0001\u0001\u0000\u0000\u0000:;\u0005-\u0000\u0000;=\u0005)\u0000\u0000"+
		"<:\u0001\u0000\u0000\u0000<=\u0001\u0000\u0000\u0000=>\u0001\u0000\u0000"+
		"\u0000>?\u0003\u001c\u000e\u0000?\u0003\u0001\u0000\u0000\u0000@F\u0005"+
		"\u0001\u0000\u0000AB\u0003\u0002\u0001\u0000BC\u0005\u0002\u0000\u0000"+
		"CE\u0001\u0000\u0000\u0000DA\u0001\u0000\u0000\u0000EH\u0001\u0000\u0000"+
		"\u0000FD\u0001\u0000\u0000\u0000FG\u0001\u0000\u0000\u0000GJ\u0001\u0000"+
		"\u0000\u0000HF\u0001\u0000\u0000\u0000IK\u0003\u0002\u0001\u0000JI\u0001"+
		"\u0000\u0000\u0000JK\u0001\u0000\u0000\u0000KL\u0001\u0000\u0000\u0000"+
		"LM\u0005\u0003\u0000\u0000M\u0005\u0001\u0000\u0000\u0000NO\u0003\u0000"+
		"\u0000\u0000O\u0007\u0001\u0000\u0000\u0000PQ\u0005\u0018\u0000\u0000"+
		"QR\u0005-\u0000\u0000R\t\u0001\u0000\u0000\u0000ST\u0005-\u0000\u0000"+
		"TV\u0005\u0004\u0000\u0000US\u0001\u0000\u0000\u0000UV\u0001\u0000\u0000"+
		"\u0000VW\u0001\u0000\u0000\u0000WX\u0003\u0010\b\u0000X\u000b\u0001\u0000"+
		"\u0000\u0000Y_\u0005\u0001\u0000\u0000Z[\u0003\n\u0005\u0000[\\\u0005"+
		"\u0002\u0000\u0000\\^\u0001\u0000\u0000\u0000]Z\u0001\u0000\u0000\u0000"+
		"^a\u0001\u0000\u0000\u0000_]\u0001\u0000\u0000\u0000_`\u0001\u0000\u0000"+
		"\u0000`c\u0001\u0000\u0000\u0000a_\u0001\u0000\u0000\u0000bd\u0003\n\u0005"+
		"\u0000cb\u0001\u0000\u0000\u0000cd\u0001\u0000\u0000\u0000de\u0001\u0000"+
		"\u0000\u0000ef\u0005\u0003\u0000\u0000f\r\u0001\u0000\u0000\u0000gh\u0003"+
		"\f\u0006\u0000hi\u0005\u0004\u0000\u0000ij\u0003\u0010\b\u0000j\u000f"+
		"\u0001\u0000\u0000\u0000kp\u0003\u0006\u0003\u0000lp\u0003\b\u0004\u0000"+
		"mp\u0003\f\u0006\u0000np\u0003\u000e\u0007\u0000ok\u0001\u0000\u0000\u0000"+
		"ol\u0001\u0000\u0000\u0000om\u0001\u0000\u0000\u0000on\u0001\u0000\u0000"+
		"\u0000p\u0011\u0001\u0000\u0000\u0000qu\u0005\u0005\u0000\u0000rt\u0005"+
		"-\u0000\u0000sr\u0001\u0000\u0000\u0000tw\u0001\u0000\u0000\u0000us\u0001"+
		"\u0000\u0000\u0000uv\u0001\u0000\u0000\u0000vx\u0001\u0000\u0000\u0000"+
		"wu\u0001\u0000\u0000\u0000xy\u0005\u0006\u0000\u0000y\u0013\u0001\u0000"+
		"\u0000\u0000z\u0085\u0003\u0016\u000b\u0000{~\u0005-\u0000\u0000|}\u0005"+
		"\u0004\u0000\u0000}\u007f\u0003\u0010\b\u0000~|\u0001\u0000\u0000\u0000"+
		"~\u007f\u0001\u0000\u0000\u0000\u007f\u0082\u0001\u0000\u0000\u0000\u0080"+
		"\u0081\u0005)\u0000\u0000\u0081\u0083\u0003\u001c\u000e\u0000\u0082\u0080"+
		"\u0001\u0000\u0000\u0000\u0082\u0083\u0001\u0000\u0000\u0000\u0083\u0085"+
		"\u0001\u0000\u0000\u0000\u0084z\u0001\u0000\u0000\u0000\u0084{\u0001\u0000"+
		"\u0000\u0000\u0085\u0015\u0001\u0000\u0000\u0000\u0086\u008c\u0005\u0001"+
		"\u0000\u0000\u0087\u0088\u0003\u0014\n\u0000\u0088\u0089\u0005\u0002\u0000"+
		"\u0000\u0089\u008b\u0001\u0000\u0000\u0000\u008a\u0087\u0001\u0000\u0000"+
		"\u0000\u008b\u008e\u0001\u0000\u0000\u0000\u008c\u008a\u0001\u0000\u0000"+
		"\u0000\u008c\u008d\u0001\u0000\u0000\u0000\u008d\u0090\u0001\u0000\u0000"+
		"\u0000\u008e\u008c\u0001\u0000\u0000\u0000\u008f\u0091\u0003\u0014\n\u0000"+
		"\u0090\u008f\u0001\u0000\u0000\u0000\u0090\u0091\u0001\u0000\u0000\u0000"+
		"\u0091\u0092\u0001\u0000\u0000\u0000\u0092\u0093\u0005\u0003\u0000\u0000"+
		"\u0093\u0017\u0001\u0000\u0000\u0000\u0094\u009b\u0005\u001d\u0000\u0000"+
		"\u0095\u009c\u0003\u0016\u000b\u0000\u0096\u0099\u0005-\u0000\u0000\u0097"+
		"\u0098\u0005\u0004\u0000\u0000\u0098\u009a\u0003\u0010\b\u0000\u0099\u0097"+
		"\u0001\u0000\u0000\u0000\u0099\u009a\u0001\u0000\u0000\u0000\u009a\u009c"+
		"\u0001\u0000\u0000\u0000\u009b\u0095\u0001\u0000\u0000\u0000\u009b\u0096"+
		"\u0001\u0000\u0000\u0000\u009c\u009d\u0001\u0000\u0000\u0000\u009d\u009e"+
		"\u0005)\u0000\u0000\u009e\u009f\u0003\u001c\u000e\u0000\u009f\u0019\u0001"+
		"\u0000\u0000\u0000\u00a0\u00a2\u0005\u001c\u0000\u0000\u00a1\u00a3\u0003"+
		"\u0012\t\u0000\u00a2\u00a1\u0001\u0000\u0000\u0000\u00a2\u00a3\u0001\u0000"+
		"\u0000\u0000\u00a3\u00a4\u0001\u0000\u0000\u0000\u00a4\u00a6\u0005-\u0000"+
		"\u0000\u00a5\u00a7\u0003\u0016\u000b\u0000\u00a6\u00a5\u0001\u0000\u0000"+
		"\u0000\u00a6\u00a7\u0001\u0000\u0000\u0000\u00a7\u00aa\u0001\u0000\u0000"+
		"\u0000\u00a8\u00a9\u0005\u0004\u0000\u0000\u00a9\u00ab\u0003\u0010\b\u0000"+
		"\u00aa\u00a8\u0001\u0000\u0000\u0000\u00aa\u00ab\u0001\u0000\u0000\u0000"+
		"\u00ab\u00ae\u0001\u0000\u0000\u0000\u00ac\u00ad\u0005#\u0000\u0000\u00ad"+
		"\u00af\u0003\u001c\u000e\u0000\u00ae\u00ac\u0001\u0000\u0000\u0000\u00ae"+
		"\u00af\u0001\u0000\u0000\u0000\u00af\u001b\u0001\u0000\u0000\u0000\u00b0"+
		"\u00b1\u0006\u000e\uffff\uffff\u0000\u00b1\u00b2\u0005\u0016\u0000\u0000"+
		"\u00b2\u00b4\u0005-\u0000\u0000\u00b3\u00b5\u0003\u0004\u0002\u0000\u00b4"+
		"\u00b3\u0001\u0000\u0000\u0000\u00b4\u00b5\u0001\u0000\u0000\u0000\u00b5"+
		"\u00f4\u0001\u0000\u0000\u0000\u00b6\u00b7\u0005\u0017\u0000\u0000\u00b7"+
		"\u00b8\u0005\u0007\u0000\u0000\u00b8\u00b9\u0003\u0010\b\u0000\u00b9\u00ba"+
		"\u0005\b\u0000\u0000\u00ba\u00bb\u0005\u0001\u0000\u0000\u00bb\u00c0\u0005"+
		"/\u0000\u0000\u00bc\u00bd\u0005\u0002\u0000\u0000\u00bd\u00bf\u0003\u001c"+
		"\u000e\u0000\u00be\u00bc\u0001\u0000\u0000\u0000\u00bf\u00c2\u0001\u0000"+
		"\u0000\u0000\u00c0\u00be\u0001\u0000\u0000\u0000\u00c0\u00c1\u0001\u0000"+
		"\u0000\u0000\u00c1\u00c3\u0001\u0000\u0000\u0000\u00c2\u00c0\u0001\u0000"+
		"\u0000\u0000\u00c3\u00c4\u0005\u0003\u0000\u0000\u00c4\u00f4\u0001\u0000"+
		"\u0000\u0000\u00c5\u00c6\u0007\u0000\u0000\u0000\u00c6\u00f4\u0003\u001c"+
		"\u000e\u0012\u00c7\u00f4\u0003\u0004\u0002\u0000\u00c8\u00c9\u0005 \u0000"+
		"\u0000\u00c9\u00ca\u0005\u0004\u0000\u0000\u00ca\u00cf\u0003\u0006\u0003"+
		"\u0000\u00cb\u00cc\u0005\u0011\u0000\u0000\u00cc\u00ce\u0003\u0006\u0003"+
		"\u0000\u00cd\u00cb\u0001\u0000\u0000\u0000\u00ce\u00d1\u0001\u0000\u0000"+
		"\u0000\u00cf\u00cd\u0001\u0000\u0000\u0000\u00cf\u00d0\u0001\u0000\u0000"+
		"\u0000\u00d0\u00da\u0001\u0000\u0000\u0000\u00d1\u00cf\u0001\u0000\u0000"+
		"\u0000\u00d2\u00d6\u0005\u0013\u0000\u0000\u00d3\u00d5\u0003\u001a\r\u0000"+
		"\u00d4\u00d3\u0001\u0000\u0000\u0000\u00d5\u00d8\u0001\u0000\u0000\u0000"+
		"\u00d6\u00d4\u0001\u0000\u0000\u0000\u00d6\u00d7\u0001\u0000\u0000\u0000"+
		"\u00d7\u00d9\u0001\u0000\u0000\u0000\u00d8\u00d6\u0001\u0000\u0000\u0000"+
		"\u00d9\u00db\u0005\u0014\u0000\u0000\u00da\u00d2\u0001\u0000\u0000\u0000"+
		"\u00da\u00db\u0001\u0000\u0000\u0000\u00db\u00f4\u0001\u0000\u0000\u0000"+
		"\u00dc\u00de\u0003\u0018\f\u0000\u00dd\u00df\u0005\u0015\u0000\u0000\u00de"+
		"\u00dd\u0001\u0000\u0000\u0000\u00de\u00df\u0001\u0000\u0000\u0000\u00df"+
		"\u00e0\u0001\u0000\u0000\u0000\u00e0\u00e1\u0003\u001c\u000e\u0006\u00e1"+
		"\u00f4\u0001\u0000\u0000\u0000\u00e2\u00e4\u0003\u001a\r\u0000\u00e3\u00e5"+
		"\u0005\u0015\u0000\u0000\u00e4\u00e3\u0001\u0000\u0000\u0000\u00e4\u00e5"+
		"\u0001\u0000\u0000\u0000\u00e5\u00e6\u0001\u0000\u0000\u0000\u00e6\u00e7"+
		"\u0003\u001c\u000e\u0005\u00e7\u00f4\u0001\u0000\u0000\u0000\u00e8\u00eb"+
		"\u0003\u0016\u000b\u0000\u00e9\u00ea\u0005\u0004\u0000\u0000\u00ea\u00ec"+
		"\u0003\u0010\b\u0000\u00eb\u00e9\u0001\u0000\u0000\u0000\u00eb\u00ec\u0001"+
		"\u0000\u0000\u0000\u00ec\u00ed\u0001\u0000\u0000\u0000\u00ed\u00ee\u0005"+
		"#\u0000\u0000\u00ee\u00ef\u0003\u001c\u000e\u0004\u00ef\u00f4\u0001\u0000"+
		"\u0000\u0000\u00f0\u00f4\u0005/\u0000\u0000\u00f1\u00f4\u0005.\u0000\u0000"+
		"\u00f2\u00f4\u0003\u0000\u0000\u0000\u00f3\u00b0\u0001\u0000\u0000\u0000"+
		"\u00f3\u00b6\u0001\u0000\u0000\u0000\u00f3\u00c5\u0001\u0000\u0000\u0000"+
		"\u00f3\u00c7\u0001\u0000\u0000\u0000\u00f3\u00c8\u0001\u0000\u0000\u0000"+
		"\u00f3\u00dc\u0001\u0000\u0000\u0000\u00f3\u00e2\u0001\u0000\u0000\u0000"+
		"\u00f3\u00e8\u0001\u0000\u0000\u0000\u00f3\u00f0\u0001\u0000\u0000\u0000"+
		"\u00f3\u00f1\u0001\u0000\u0000\u0000\u00f3\u00f2\u0001\u0000\u0000\u0000"+
		"\u00f4\u011f\u0001\u0000\u0000\u0000\u00f5\u00f6\n\u0011\u0000\u0000\u00f6"+
		"\u00f7\u0007\u0001\u0000\u0000\u00f7\u011e\u0003\u001c\u000e\u0012\u00f8"+
		"\u00f9\n\u0010\u0000\u0000\u00f9\u00fa\u0007\u0000\u0000\u0000\u00fa\u011e"+
		"\u0003\u001c\u000e\u0011\u00fb\u00fc\n\u000f\u0000\u0000\u00fc\u00fd\u0007"+
		"\u0002\u0000\u0000\u00fd\u011e\u0003\u001c\u000e\u0010\u00fe\u00ff\n\u000e"+
		"\u0000\u0000\u00ff\u0100\u0007\u0003\u0000\u0000\u0100\u011e\u0003\u001c"+
		"\u000e\u000f\u0101\u0102\n\r\u0000\u0000\u0102\u0103\u0007\u0004\u0000"+
		"\u0000\u0103\u011e\u0003\u001c\u000e\u000e\u0104\u0105\n\f\u0000\u0000"+
		"\u0105\u0106\u0005\u000f\u0000\u0000\u0106\u011e\u0003\u001c\u000e\r\u0107"+
		"\u0108\n\u000b\u0000\u0000\u0108\u0109\u0005\u0010\u0000\u0000\u0109\u011e"+
		"\u0003\u001c\u000e\f\u010a\u010b\n\n\u0000\u0000\u010b\u010c\u0005\u0011"+
		"\u0000\u0000\u010c\u011e\u0003\u001c\u000e\u000b\u010d\u010e\n\t\u0000"+
		"\u0000\u010e\u010f\u0005\u0012\u0000\u0000\u010f\u0110\u0003\u001c\u000e"+
		"\u0000\u0110\u0111\u0005\u0004\u0000\u0000\u0111\u0112\u0003\u001c\u000e"+
		"\n\u0112\u011e\u0001\u0000\u0000\u0000\u0113\u0114\n\u0015\u0000\u0000"+
		"\u0114\u0115\u0005\t\u0000\u0000\u0115\u011e\u0005-\u0000\u0000\u0116"+
		"\u0117\n\u0014\u0000\u0000\u0117\u011e\u0003\u0004\u0002\u0000\u0118\u0119"+
		"\n\u0013\u0000\u0000\u0119\u011a\u0007\u0005\u0000\u0000\u011a\u011b\u0003"+
		"\u001c\u000e\u0000\u011b\u011c\u0003\u0004\u0002\u0000\u011c\u011e\u0001"+
		"\u0000\u0000\u0000\u011d\u00f5\u0001\u0000\u0000\u0000\u011d\u00f8\u0001"+
		"\u0000\u0000\u0000\u011d\u00fb\u0001\u0000\u0000\u0000\u011d\u00fe\u0001"+
		"\u0000\u0000\u0000\u011d\u0101\u0001\u0000\u0000\u0000\u011d\u0104\u0001"+
		"\u0000\u0000\u0000\u011d\u0107\u0001\u0000\u0000\u0000\u011d\u010a\u0001"+
		"\u0000\u0000\u0000\u011d\u010d\u0001\u0000\u0000\u0000\u011d\u0113\u0001"+
		"\u0000\u0000\u0000\u011d\u0116\u0001\u0000\u0000\u0000\u011d\u0118\u0001"+
		"\u0000\u0000\u0000\u011e\u0121\u0001\u0000\u0000\u0000\u011f\u011d\u0001"+
		"\u0000\u0000\u0000\u011f\u0120\u0001\u0000\u0000\u0000\u0120\u001d\u0001"+
		"\u0000\u0000\u0000\u0121\u011f\u0001\u0000\u0000\u0000\u0122\u0123\u0005"+
		"\u0004\u0000\u0000\u0123\u0128\u0003\u0006\u0003\u0000\u0124\u0125\u0005"+
		"\u0002\u0000\u0000\u0125\u0127\u0003\u0006\u0003\u0000\u0126\u0124\u0001"+
		"\u0000\u0000\u0000\u0127\u012a\u0001\u0000\u0000\u0000\u0128\u0126\u0001"+
		"\u0000\u0000\u0000\u0128\u0129\u0001\u0000\u0000\u0000\u0129\u001f\u0001"+
		"\u0000\u0000\u0000\u012a\u0128\u0001\u0000\u0000\u0000\u012b\u012c\u0005"+
		"\u0019\u0000\u0000\u012c\u012d\u0003\u0006\u0003\u0000\u012d!\u0001\u0000"+
		"\u0000\u0000\u012e\u012f\u0005\u001a\u0000\u0000\u012f\u0130\u0003\u0006"+
		"\u0003\u0000\u0130#\u0001\u0000\u0000\u0000\u0131\u0132\u0005\u001e\u0000"+
		"\u0000\u0132\u0134\u0005-\u0000\u0000\u0133\u0135\u0003\u001e\u000f\u0000"+
		"\u0134\u0133\u0001\u0000\u0000\u0000\u0134\u0135\u0001\u0000\u0000\u0000"+
		"\u0135\u013e\u0001\u0000\u0000\u0000\u0136\u013a\u0005\u0013\u0000\u0000"+
		"\u0137\u0139\u0003\u001a\r\u0000\u0138\u0137\u0001\u0000\u0000\u0000\u0139"+
		"\u013c\u0001\u0000\u0000\u0000\u013a\u0138\u0001\u0000\u0000\u0000\u013a"+
		"\u013b\u0001\u0000\u0000\u0000\u013b\u013d\u0001\u0000\u0000\u0000\u013c"+
		"\u013a\u0001\u0000\u0000\u0000\u013d\u013f\u0005\u0014\u0000\u0000\u013e"+
		"\u0136\u0001\u0000\u0000\u0000\u013e\u013f\u0001\u0000\u0000\u0000\u013f"+
		"%\u0001\u0000\u0000\u0000\u0140\u0141\u0005\u001f\u0000\u0000\u0141\u0143"+
		"\u0005-\u0000\u0000\u0142\u0144\u0003\u0016\u000b\u0000\u0143\u0142\u0001"+
		"\u0000\u0000\u0000\u0143\u0144\u0001\u0000\u0000\u0000\u0144\u0146\u0001"+
		"\u0000\u0000\u0000\u0145\u0147\u0003\u001e\u000f\u0000\u0146\u0145\u0001"+
		"\u0000\u0000\u0000\u0146\u0147\u0001\u0000\u0000\u0000\u0147\u0150\u0001"+
		"\u0000\u0000\u0000\u0148\u014c\u0005\u0013\u0000\u0000\u0149\u014b\u0003"+
		".\u0017\u0000\u014a\u0149\u0001\u0000\u0000\u0000\u014b\u014e\u0001\u0000"+
		"\u0000\u0000\u014c\u014a\u0001\u0000\u0000\u0000\u014c\u014d\u0001\u0000"+
		"\u0000\u0000\u014d\u014f\u0001\u0000\u0000\u0000\u014e\u014c\u0001\u0000"+
		"\u0000\u0000\u014f\u0151\u0005\u0014\u0000\u0000\u0150\u0148\u0001\u0000"+
		"\u0000\u0000\u0150\u0151\u0001\u0000\u0000\u0000\u0151\'\u0001\u0000\u0000"+
		"\u0000\u0152\u0153\u0005!\u0000\u0000\u0153\u0160\u0005-\u0000\u0000\u0154"+
		"\u015c\u0005\u0013\u0000\u0000\u0155\u0157\u0005-\u0000\u0000\u0156\u0158"+
		"\u0003\u0016\u000b\u0000\u0157\u0156\u0001\u0000\u0000\u0000\u0157\u0158"+
		"\u0001\u0000\u0000\u0000\u0158\u015b\u0001\u0000\u0000\u0000\u0159\u015b"+
		"\u0003\u001a\r\u0000\u015a\u0155\u0001\u0000\u0000\u0000\u015a\u0159\u0001"+
		"\u0000\u0000\u0000\u015b\u015e\u0001\u0000\u0000\u0000\u015c\u015a\u0001"+
		"\u0000\u0000\u0000\u015c\u015d\u0001\u0000\u0000\u0000\u015d\u015f\u0001"+
		"\u0000\u0000\u0000\u015e\u015c\u0001\u0000\u0000\u0000\u015f\u0161\u0005"+
		"\u0014\u0000\u0000\u0160\u0154\u0001\u0000\u0000\u0000\u0160\u0161\u0001"+
		"\u0000\u0000\u0000\u0161)\u0001\u0000\u0000\u0000\u0162\u0163\u0005\u001b"+
		"\u0000\u0000\u0163\u0164\u0005-\u0000\u0000\u0164\u0165\u0005\u0004\u0000"+
		"\u0000\u0165\u0166\u0003\u0010\b\u0000\u0166+\u0001\u0000\u0000\u0000"+
		"\u0167\u016e\u0003\u0018\f\u0000\u0168\u016e\u0003\u001a\r\u0000\u0169"+
		"\u016e\u0003$\u0012\u0000\u016a\u016e\u0003&\u0013\u0000\u016b\u016e\u0003"+
		"(\u0014\u0000\u016c\u016e\u0003*\u0015\u0000\u016d\u0167\u0001\u0000\u0000"+
		"\u0000\u016d\u0168\u0001\u0000\u0000\u0000\u016d\u0169\u0001\u0000\u0000"+
		"\u0000\u016d\u016a\u0001\u0000\u0000\u0000\u016d\u016b\u0001\u0000\u0000"+
		"\u0000\u016d\u016c\u0001\u0000\u0000\u0000\u016e-\u0001\u0000\u0000\u0000"+
		"\u016f\u0170\u0003\u001a\r\u0000\u0170/\u0001\u0000\u0000\u0000\u0171"+
		"\u0175\u0003 \u0010\u0000\u0172\u0174\u0003\"\u0011\u0000\u0173\u0172"+
		"\u0001\u0000\u0000\u0000\u0174\u0177\u0001\u0000\u0000\u0000\u0175\u0173"+
		"\u0001\u0000\u0000\u0000\u0175\u0176\u0001\u0000\u0000\u0000\u0176\u017b"+
		"\u0001\u0000\u0000\u0000\u0177\u0175\u0001\u0000\u0000\u0000\u0178\u017a"+
		"\u0003,\u0016\u0000\u0179\u0178\u0001\u0000\u0000\u0000\u017a\u017d\u0001"+
		"\u0000\u0000\u0000\u017b\u0179\u0001\u0000\u0000\u0000\u017b\u017c\u0001"+
		"\u0000\u0000\u0000\u017c\u017e\u0001\u0000\u0000\u0000\u017d\u017b\u0001"+
		"\u0000\u0000\u0000\u017e\u017f\u0005\u0000\u0000\u0001\u017f1\u0001\u0000"+
		"\u0000\u0000.5<FJU_cou~\u0082\u0084\u008c\u0090\u0099\u009b\u00a2\u00a6"+
		"\u00aa\u00ae\u00b4\u00c0\u00cf\u00d6\u00da\u00de\u00e4\u00eb\u00f3\u011d"+
		"\u011f\u0128\u0134\u013a\u013e\u0143\u0146\u014c\u0150\u0157\u015a\u015c"+
		"\u0160\u016d\u0175\u017b";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}