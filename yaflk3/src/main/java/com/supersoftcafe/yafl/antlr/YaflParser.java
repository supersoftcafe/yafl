// Generated from /home/mbrown/Projects/yafl/yaflk3/Yafl.g4 by ANTLR 4.10.1
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
		MODULE=18, USING=19, FUN=20, LET=21, STRUCT=22, INTERFACE=23, CLASS=24, 
		OBJECT=25, ENUM=26, LAZY=27, DASH_ARROW=28, APPLY=29, NAME=30, INTEGER=31, 
		STRING=32, WS=33, COMMENT=34;
	public static final int
		RULE_exprOfTuplePart = 0, RULE_exprOfTuple = 1, RULE_typeRef = 2, RULE_typeOfTuplePart = 3, 
		RULE_typeOfTuple = 4, RULE_typeOfLambda = 5, RULE_type = 6, RULE_expression = 7, 
		RULE_module = 8, RULE_using = 9, RULE_function = 10, RULE_letWithExpr = 11, 
		RULE_interface = 12, RULE_class = 13, RULE_struct = 14, RULE_enum = 15, 
		RULE_declaration = 16, RULE_root = 17;
	private static String[] makeRuleNames() {
		return new String[] {
			"exprOfTuplePart", "exprOfTuple", "typeRef", "typeOfTuplePart", "typeOfTuple", 
			"typeOfLambda", "type", "expression", "module", "using", "function", 
			"letWithExpr", "interface", "class", "struct", "enum", "declaration", 
			"root"
		};
	}
	public static final String[] ruleNames = makeRuleNames();

	private static String[] makeLiteralNames() {
		return new String[] {
			null, "'='", "'('", "','", "')'", "'.'", "':'", "'*'", "'/'", "'%'", 
			"'+'", "'-'", "'<'", "'>'", "'?'", "'|'", "'{'", "'}'", "'module'", "'using'", 
			"'fun'", "'let'", "'struct'", "'interface'", "'class'", "'object'", "'enum'", 
			"'lazy'", "'->'", "'|>'"
		};
	}
	private static final String[] _LITERAL_NAMES = makeLiteralNames();
	private static String[] makeSymbolicNames() {
		return new String[] {
			null, null, null, null, null, null, null, null, null, null, null, null, 
			null, null, null, null, null, null, "MODULE", "USING", "FUN", "LET", 
			"STRUCT", "INTERFACE", "CLASS", "OBJECT", "ENUM", "LAZY", "DASH_ARROW", 
			"APPLY", "NAME", "INTEGER", "STRING", "WS", "COMMENT"
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

	public static class ExprOfTuplePartContext extends ParserRuleContext {
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
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
		enterRule(_localctx, 0, RULE_exprOfTuplePart);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(38);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,0,_ctx) ) {
			case 1:
				{
				setState(36);
				match(NAME);
				setState(37);
				match(T__0);
				}
				break;
			}
			setState(40);
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
		enterRule(_localctx, 2, RULE_exprOfTuple);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(42);
			match(T__1);
			setState(48);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,1,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(43);
					exprOfTuplePart();
					setState(44);
					match(T__2);
					}
					} 
				}
				setState(50);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,1,_ctx);
			}
			setState(52);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__1) | (1L << OBJECT) | (1L << NAME) | (1L << INTEGER) | (1L << STRING))) != 0)) {
				{
				setState(51);
				exprOfTuplePart();
				}
			}

			setState(54);
			match(T__3);
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
		public List<TerminalNode> NAME() { return getTokens(YaflParser.NAME); }
		public TerminalNode NAME(int i) {
			return getToken(YaflParser.NAME, i);
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
		enterRule(_localctx, 4, RULE_typeRef);
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(56);
			match(NAME);
			setState(61);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,3,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(57);
					match(T__4);
					setState(58);
					match(NAME);
					}
					} 
				}
				setState(63);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,3,_ctx);
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

	public static class TypeOfTuplePartContext extends ParserRuleContext {
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
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
		enterRule(_localctx, 6, RULE_typeOfTuplePart);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(64);
			match(NAME);
			setState(67);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__5) {
				{
				setState(65);
				match(T__5);
				setState(66);
				type();
				}
			}

			setState(71);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__0) {
				{
				setState(69);
				match(T__0);
				setState(70);
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
		enterRule(_localctx, 8, RULE_typeOfTuple);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(73);
			match(T__1);
			setState(79);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,6,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(74);
					typeOfTuplePart();
					setState(75);
					match(T__2);
					}
					} 
				}
				setState(81);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,6,_ctx);
			}
			setState(83);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==NAME) {
				{
				setState(82);
				typeOfTuplePart();
				}
			}

			setState(85);
			match(T__3);
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
		public TerminalNode DASH_ARROW() { return getToken(YaflParser.DASH_ARROW, 0); }
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
		enterRule(_localctx, 10, RULE_typeOfLambda);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(87);
			typeOfTuple();
			setState(88);
			match(DASH_ARROW);
			setState(89);
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

	public final TypeContext type() throws RecognitionException {
		TypeContext _localctx = new TypeContext(_ctx, getState());
		enterRule(_localctx, 12, RULE_type);
		try {
			setState(94);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,8,_ctx) ) {
			case 1:
				_localctx = new NamedTypeContext(_localctx);
				enterOuterAlt(_localctx, 1);
				{
				setState(91);
				typeRef();
				}
				break;
			case 2:
				_localctx = new TupleTypeContext(_localctx);
				enterOuterAlt(_localctx, 2);
				{
				setState(92);
				typeOfTuple();
				}
				break;
			case 3:
				_localctx = new LambdaTypeContext(_localctx);
				enterOuterAlt(_localctx, 3);
				{
				setState(93);
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
		public Token name;
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
		public ExpressionContext right;
		public ExprOfTupleContext params;
		public TerminalNode APPLY() { return getToken(YaflParser.APPLY, 0); }
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public ExprOfTupleContext exprOfTuple() {
			return getRuleContext(ExprOfTupleContext.class,0);
		}
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
	public static class NameExprContext extends ExpressionContext {
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
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
	public static class LambdaExprContext extends ExpressionContext {
		public TypeOfTupleContext typeOfTuple() {
			return getRuleContext(TypeOfTupleContext.class,0);
		}
		public TerminalNode DASH_ARROW() { return getToken(YaflParser.DASH_ARROW, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
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

	public final ExpressionContext expression() throws RecognitionException {
		return expression(0);
	}

	private ExpressionContext expression(int _p) throws RecognitionException {
		ParserRuleContext _parentctx = _ctx;
		int _parentState = getState();
		ExpressionContext _localctx = new ExpressionContext(_ctx, _parentState);
		ExpressionContext _prevctx = _localctx;
		int _startState = 14;
		enterRecursionRule(_localctx, 14, RULE_expression, _p);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(125);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,12,_ctx) ) {
			case 1:
				{
				_localctx = new TupleExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;

				setState(97);
				exprOfTuple();
				}
				break;
			case 2:
				{
				_localctx = new ObjectExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(98);
				match(OBJECT);
				setState(99);
				match(T__5);
				setState(100);
				typeRef();
				setState(105);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,9,_ctx);
				while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
					if ( _alt==1 ) {
						{
						{
						setState(101);
						match(T__14);
						setState(102);
						typeRef();
						}
						} 
					}
					setState(107);
					_errHandler.sync(this);
					_alt = getInterpreter().adaptivePredict(_input,9,_ctx);
				}
				setState(116);
				_errHandler.sync(this);
				switch ( getInterpreter().adaptivePredict(_input,11,_ctx) ) {
				case 1:
					{
					setState(108);
					match(T__15);
					setState(112);
					_errHandler.sync(this);
					_la = _input.LA(1);
					while (_la==FUN) {
						{
						{
						setState(109);
						function();
						}
						}
						setState(114);
						_errHandler.sync(this);
						_la = _input.LA(1);
					}
					setState(115);
					match(T__16);
					}
					break;
				}
				}
				break;
			case 3:
				{
				_localctx = new LambdaExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(118);
				typeOfTuple();
				setState(119);
				match(DASH_ARROW);
				setState(120);
				expression(4);
				}
				break;
			case 4:
				{
				_localctx = new StringExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(122);
				match(STRING);
				}
				break;
			case 5:
				{
				_localctx = new IntegerExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(123);
				match(INTEGER);
				}
				break;
			case 6:
				{
				_localctx = new NameExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(124);
				match(NAME);
				}
				break;
			}
			_ctx.stop = _input.LT(-1);
			setState(154);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,14,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					if ( _parseListeners!=null ) triggerExitRuleEvent();
					_prevctx = _localctx;
					{
					setState(152);
					_errHandler.sync(this);
					switch ( getInterpreter().adaptivePredict(_input,13,_ctx) ) {
					case 1:
						{
						_localctx = new ProductExprContext(new ExpressionContext(_parentctx, _parentState));
						((ProductExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(127);
						if (!(precpred(_ctx, 10))) throw new FailedPredicateException(this, "precpred(_ctx, 10)");
						setState(128);
						((ProductExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__6) | (1L << T__7) | (1L << T__8))) != 0)) ) {
							((ProductExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(129);
						((ProductExprContext)_localctx).right = expression(11);
						}
						break;
					case 2:
						{
						_localctx = new SumExprContext(new ExpressionContext(_parentctx, _parentState));
						((SumExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(130);
						if (!(precpred(_ctx, 9))) throw new FailedPredicateException(this, "precpred(_ctx, 9)");
						setState(131);
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
						setState(132);
						((SumExprContext)_localctx).right = expression(10);
						}
						break;
					case 3:
						{
						_localctx = new CompareExprContext(new ExpressionContext(_parentctx, _parentState));
						((CompareExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(133);
						if (!(precpred(_ctx, 8))) throw new FailedPredicateException(this, "precpred(_ctx, 8)");
						setState(134);
						((CompareExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__0) | (1L << T__11) | (1L << T__12))) != 0)) ) {
							((CompareExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(135);
						((CompareExprContext)_localctx).right = expression(9);
						}
						break;
					case 4:
						{
						_localctx = new IfExprContext(new ExpressionContext(_parentctx, _parentState));
						((IfExprContext)_localctx).condition = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(136);
						if (!(precpred(_ctx, 7))) throw new FailedPredicateException(this, "precpred(_ctx, 7)");
						setState(137);
						match(T__13);
						setState(138);
						((IfExprContext)_localctx).left = expression(0);
						setState(139);
						match(T__5);
						setState(140);
						((IfExprContext)_localctx).right = expression(8);
						}
						break;
					case 5:
						{
						_localctx = new DotExprContext(new ExpressionContext(_parentctx, _parentState));
						((DotExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(142);
						if (!(precpred(_ctx, 13))) throw new FailedPredicateException(this, "precpred(_ctx, 13)");
						setState(143);
						((DotExprContext)_localctx).operator = match(T__4);
						setState(144);
						((DotExprContext)_localctx).name = match(NAME);
						}
						break;
					case 6:
						{
						_localctx = new CallExprContext(new ExpressionContext(_parentctx, _parentState));
						((CallExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(145);
						if (!(precpred(_ctx, 12))) throw new FailedPredicateException(this, "precpred(_ctx, 12)");
						setState(146);
						((CallExprContext)_localctx).params = exprOfTuple();
						}
						break;
					case 7:
						{
						_localctx = new ApplyExprContext(new ExpressionContext(_parentctx, _parentState));
						((ApplyExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(147);
						if (!(precpred(_ctx, 11))) throw new FailedPredicateException(this, "precpred(_ctx, 11)");
						setState(148);
						match(APPLY);
						setState(149);
						((ApplyExprContext)_localctx).right = expression(0);
						setState(150);
						((ApplyExprContext)_localctx).params = exprOfTuple();
						}
						break;
					}
					} 
				}
				setState(156);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,14,_ctx);
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
		enterRule(_localctx, 16, RULE_module);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(157);
			match(MODULE);
			setState(158);
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

	public static class UsingContext extends ParserRuleContext {
		public TerminalNode USING() { return getToken(YaflParser.USING, 0); }
		public TypeRefContext typeRef() {
			return getRuleContext(TypeRefContext.class,0);
		}
		public UsingContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_using; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterUsing(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitUsing(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitUsing(this);
			else return visitor.visitChildren(this);
		}
	}

	public final UsingContext using() throws RecognitionException {
		UsingContext _localctx = new UsingContext(_ctx, getState());
		enterRule(_localctx, 18, RULE_using);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(160);
			match(USING);
			setState(161);
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

	public static class FunctionContext extends ParserRuleContext {
		public TerminalNode FUN() { return getToken(YaflParser.FUN, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TypeOfTupleContext typeOfTuple() {
			return getRuleContext(TypeOfTupleContext.class,0);
		}
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
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
		enterRule(_localctx, 20, RULE_function);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(163);
			match(FUN);
			setState(164);
			match(NAME);
			setState(166);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__1) {
				{
				setState(165);
				typeOfTuple();
				}
			}

			setState(170);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__5) {
				{
				setState(168);
				match(T__5);
				setState(169);
				type();
				}
			}

			setState(174);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__0) {
				{
				setState(172);
				match(T__0);
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

	public static class LetWithExprContext extends ParserRuleContext {
		public TerminalNode LET() { return getToken(YaflParser.LET, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
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
		enterRule(_localctx, 22, RULE_letWithExpr);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(176);
			match(LET);
			setState(177);
			match(NAME);
			setState(180);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__5) {
				{
				setState(178);
				match(T__5);
				setState(179);
				type();
				}
			}

			setState(182);
			match(T__0);
			setState(183);
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

	public static class InterfaceContext extends ParserRuleContext {
		public TerminalNode INTERFACE() { return getToken(YaflParser.INTERFACE, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
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
		enterRule(_localctx, 24, RULE_interface);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(185);
			match(INTERFACE);
			setState(186);
			match(NAME);
			setState(196);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__5) {
				{
				setState(187);
				match(T__5);
				setState(188);
				typeRef();
				setState(193);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==T__14) {
					{
					{
					setState(189);
					match(T__14);
					setState(190);
					typeRef();
					}
					}
					setState(195);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				}
			}

			setState(206);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__15) {
				{
				setState(198);
				match(T__15);
				setState(200); 
				_errHandler.sync(this);
				_la = _input.LA(1);
				do {
					{
					{
					setState(199);
					function();
					}
					}
					setState(202); 
					_errHandler.sync(this);
					_la = _input.LA(1);
				} while ( _la==FUN );
				setState(204);
				match(T__16);
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
		public TypeOfTupleContext typeOfTuple() {
			return getRuleContext(TypeOfTupleContext.class,0);
		}
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
		enterRule(_localctx, 26, RULE_class);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(208);
			match(CLASS);
			setState(209);
			match(NAME);
			setState(211);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__1) {
				{
				setState(210);
				typeOfTuple();
				}
			}

			setState(222);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__5) {
				{
				setState(213);
				match(T__5);
				setState(214);
				typeRef();
				setState(219);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==T__14) {
					{
					{
					setState(215);
					match(T__14);
					setState(216);
					typeRef();
					}
					}
					setState(221);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				}
			}

			setState(232);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__15) {
				{
				setState(224);
				match(T__15);
				setState(228);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN) {
					{
					{
					setState(225);
					function();
					}
					}
					setState(230);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(231);
				match(T__16);
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

	public static class StructContext extends ParserRuleContext {
		public TerminalNode STRUCT() { return getToken(YaflParser.STRUCT, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TypeOfTupleContext typeOfTuple() {
			return getRuleContext(TypeOfTupleContext.class,0);
		}
		public List<FunctionContext> function() {
			return getRuleContexts(FunctionContext.class);
		}
		public FunctionContext function(int i) {
			return getRuleContext(FunctionContext.class,i);
		}
		public StructContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_struct; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterStruct(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitStruct(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitStruct(this);
			else return visitor.visitChildren(this);
		}
	}

	public final StructContext struct() throws RecognitionException {
		StructContext _localctx = new StructContext(_ctx, getState());
		enterRule(_localctx, 28, RULE_struct);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(234);
			match(STRUCT);
			setState(235);
			match(NAME);
			setState(236);
			typeOfTuple();
			setState(245);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__15) {
				{
				setState(237);
				match(T__15);
				setState(241);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN) {
					{
					{
					setState(238);
					function();
					}
					}
					setState(243);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(244);
				match(T__16);
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
		public List<TypeOfTupleContext> typeOfTuple() {
			return getRuleContexts(TypeOfTupleContext.class);
		}
		public TypeOfTupleContext typeOfTuple(int i) {
			return getRuleContext(TypeOfTupleContext.class,i);
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
		enterRule(_localctx, 30, RULE_enum);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(247);
			match(ENUM);
			setState(248);
			match(NAME);
			setState(261);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__15) {
				{
				setState(249);
				match(T__15);
				setState(257);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN || _la==NAME) {
					{
					setState(255);
					_errHandler.sync(this);
					switch (_input.LA(1)) {
					case NAME:
						{
						{
						setState(250);
						match(NAME);
						setState(252);
						_errHandler.sync(this);
						_la = _input.LA(1);
						if (_la==T__1) {
							{
							setState(251);
							typeOfTuple();
							}
						}

						}
						}
						break;
					case FUN:
						{
						setState(254);
						function();
						}
						break;
					default:
						throw new NoViableAltException(this);
					}
					}
					setState(259);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(260);
				match(T__16);
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
		public StructContext struct() {
			return getRuleContext(StructContext.class,0);
		}
		public EnumContext enum_() {
			return getRuleContext(EnumContext.class,0);
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
		enterRule(_localctx, 32, RULE_declaration);
		try {
			setState(269);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case LET:
				enterOuterAlt(_localctx, 1);
				{
				setState(263);
				letWithExpr();
				}
				break;
			case FUN:
				enterOuterAlt(_localctx, 2);
				{
				setState(264);
				function();
				}
				break;
			case INTERFACE:
				enterOuterAlt(_localctx, 3);
				{
				setState(265);
				interface_();
				}
				break;
			case CLASS:
				enterOuterAlt(_localctx, 4);
				{
				setState(266);
				class_();
				}
				break;
			case STRUCT:
				enterOuterAlt(_localctx, 5);
				{
				setState(267);
				struct();
				}
				break;
			case ENUM:
				enterOuterAlt(_localctx, 6);
				{
				setState(268);
				enum_();
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

	public static class RootContext extends ParserRuleContext {
		public ModuleContext module() {
			return getRuleContext(ModuleContext.class,0);
		}
		public TerminalNode EOF() { return getToken(YaflParser.EOF, 0); }
		public List<UsingContext> using() {
			return getRuleContexts(UsingContext.class);
		}
		public UsingContext using(int i) {
			return getRuleContext(UsingContext.class,i);
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
		enterRule(_localctx, 34, RULE_root);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(271);
			module();
			setState(275);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==USING) {
				{
				{
				setState(272);
				using();
				}
				}
				setState(277);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(281);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << FUN) | (1L << LET) | (1L << STRUCT) | (1L << INTERFACE) | (1L << CLASS) | (1L << ENUM))) != 0)) {
				{
				{
				setState(278);
				declaration();
				}
				}
				setState(283);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(284);
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
		case 7:
			return expression_sempred((ExpressionContext)_localctx, predIndex);
		}
		return true;
	}
	private boolean expression_sempred(ExpressionContext _localctx, int predIndex) {
		switch (predIndex) {
		case 0:
			return precpred(_ctx, 10);
		case 1:
			return precpred(_ctx, 9);
		case 2:
			return precpred(_ctx, 8);
		case 3:
			return precpred(_ctx, 7);
		case 4:
			return precpred(_ctx, 13);
		case 5:
			return precpred(_ctx, 12);
		case 6:
			return precpred(_ctx, 11);
		}
		return true;
	}

	public static final String _serializedATN =
		"\u0004\u0001\"\u011f\u0002\u0000\u0007\u0000\u0002\u0001\u0007\u0001\u0002"+
		"\u0002\u0007\u0002\u0002\u0003\u0007\u0003\u0002\u0004\u0007\u0004\u0002"+
		"\u0005\u0007\u0005\u0002\u0006\u0007\u0006\u0002\u0007\u0007\u0007\u0002"+
		"\b\u0007\b\u0002\t\u0007\t\u0002\n\u0007\n\u0002\u000b\u0007\u000b\u0002"+
		"\f\u0007\f\u0002\r\u0007\r\u0002\u000e\u0007\u000e\u0002\u000f\u0007\u000f"+
		"\u0002\u0010\u0007\u0010\u0002\u0011\u0007\u0011\u0001\u0000\u0001\u0000"+
		"\u0003\u0000\'\b\u0000\u0001\u0000\u0001\u0000\u0001\u0001\u0001\u0001"+
		"\u0001\u0001\u0001\u0001\u0005\u0001/\b\u0001\n\u0001\f\u00012\t\u0001"+
		"\u0001\u0001\u0003\u00015\b\u0001\u0001\u0001\u0001\u0001\u0001\u0002"+
		"\u0001\u0002\u0001\u0002\u0005\u0002<\b\u0002\n\u0002\f\u0002?\t\u0002"+
		"\u0001\u0003\u0001\u0003\u0001\u0003\u0003\u0003D\b\u0003\u0001\u0003"+
		"\u0001\u0003\u0003\u0003H\b\u0003\u0001\u0004\u0001\u0004\u0001\u0004"+
		"\u0001\u0004\u0005\u0004N\b\u0004\n\u0004\f\u0004Q\t\u0004\u0001\u0004"+
		"\u0003\u0004T\b\u0004\u0001\u0004\u0001\u0004\u0001\u0005\u0001\u0005"+
		"\u0001\u0005\u0001\u0005\u0001\u0006\u0001\u0006\u0001\u0006\u0003\u0006"+
		"_\b\u0006\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007"+
		"\u0001\u0007\u0001\u0007\u0005\u0007h\b\u0007\n\u0007\f\u0007k\t\u0007"+
		"\u0001\u0007\u0001\u0007\u0005\u0007o\b\u0007\n\u0007\f\u0007r\t\u0007"+
		"\u0001\u0007\u0003\u0007u\b\u0007\u0001\u0007\u0001\u0007\u0001\u0007"+
		"\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0003\u0007~\b\u0007"+
		"\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007"+
		"\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007"+
		"\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007"+
		"\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007\u0001\u0007"+
		"\u0001\u0007\u0005\u0007\u0099\b\u0007\n\u0007\f\u0007\u009c\t\u0007\u0001"+
		"\b\u0001\b\u0001\b\u0001\t\u0001\t\u0001\t\u0001\n\u0001\n\u0001\n\u0003"+
		"\n\u00a7\b\n\u0001\n\u0001\n\u0003\n\u00ab\b\n\u0001\n\u0001\n\u0003\n"+
		"\u00af\b\n\u0001\u000b\u0001\u000b\u0001\u000b\u0001\u000b\u0003\u000b"+
		"\u00b5\b\u000b\u0001\u000b\u0001\u000b\u0001\u000b\u0001\f\u0001\f\u0001"+
		"\f\u0001\f\u0001\f\u0001\f\u0005\f\u00c0\b\f\n\f\f\f\u00c3\t\f\u0003\f"+
		"\u00c5\b\f\u0001\f\u0001\f\u0004\f\u00c9\b\f\u000b\f\f\f\u00ca\u0001\f"+
		"\u0001\f\u0003\f\u00cf\b\f\u0001\r\u0001\r\u0001\r\u0003\r\u00d4\b\r\u0001"+
		"\r\u0001\r\u0001\r\u0001\r\u0005\r\u00da\b\r\n\r\f\r\u00dd\t\r\u0003\r"+
		"\u00df\b\r\u0001\r\u0001\r\u0005\r\u00e3\b\r\n\r\f\r\u00e6\t\r\u0001\r"+
		"\u0003\r\u00e9\b\r\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001"+
		"\u000e\u0005\u000e\u00f0\b\u000e\n\u000e\f\u000e\u00f3\t\u000e\u0001\u000e"+
		"\u0003\u000e\u00f6\b\u000e\u0001\u000f\u0001\u000f\u0001\u000f\u0001\u000f"+
		"\u0001\u000f\u0003\u000f\u00fd\b\u000f\u0001\u000f\u0005\u000f\u0100\b"+
		"\u000f\n\u000f\f\u000f\u0103\t\u000f\u0001\u000f\u0003\u000f\u0106\b\u000f"+
		"\u0001\u0010\u0001\u0010\u0001\u0010\u0001\u0010\u0001\u0010\u0001\u0010"+
		"\u0003\u0010\u010e\b\u0010\u0001\u0011\u0001\u0011\u0005\u0011\u0112\b"+
		"\u0011\n\u0011\f\u0011\u0115\t\u0011\u0001\u0011\u0005\u0011\u0118\b\u0011"+
		"\n\u0011\f\u0011\u011b\t\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0000"+
		"\u0001\u000e\u0012\u0000\u0002\u0004\u0006\b\n\f\u000e\u0010\u0012\u0014"+
		"\u0016\u0018\u001a\u001c\u001e \"\u0000\u0003\u0001\u0000\u0007\t\u0001"+
		"\u0000\n\u000b\u0002\u0000\u0001\u0001\f\r\u013f\u0000&\u0001\u0000\u0000"+
		"\u0000\u0002*\u0001\u0000\u0000\u0000\u00048\u0001\u0000\u0000\u0000\u0006"+
		"@\u0001\u0000\u0000\u0000\bI\u0001\u0000\u0000\u0000\nW\u0001\u0000\u0000"+
		"\u0000\f^\u0001\u0000\u0000\u0000\u000e}\u0001\u0000\u0000\u0000\u0010"+
		"\u009d\u0001\u0000\u0000\u0000\u0012\u00a0\u0001\u0000\u0000\u0000\u0014"+
		"\u00a3\u0001\u0000\u0000\u0000\u0016\u00b0\u0001\u0000\u0000\u0000\u0018"+
		"\u00b9\u0001\u0000\u0000\u0000\u001a\u00d0\u0001\u0000\u0000\u0000\u001c"+
		"\u00ea\u0001\u0000\u0000\u0000\u001e\u00f7\u0001\u0000\u0000\u0000 \u010d"+
		"\u0001\u0000\u0000\u0000\"\u010f\u0001\u0000\u0000\u0000$%\u0005\u001e"+
		"\u0000\u0000%\'\u0005\u0001\u0000\u0000&$\u0001\u0000\u0000\u0000&\'\u0001"+
		"\u0000\u0000\u0000\'(\u0001\u0000\u0000\u0000()\u0003\u000e\u0007\u0000"+
		")\u0001\u0001\u0000\u0000\u0000*0\u0005\u0002\u0000\u0000+,\u0003\u0000"+
		"\u0000\u0000,-\u0005\u0003\u0000\u0000-/\u0001\u0000\u0000\u0000.+\u0001"+
		"\u0000\u0000\u0000/2\u0001\u0000\u0000\u00000.\u0001\u0000\u0000\u0000"+
		"01\u0001\u0000\u0000\u000014\u0001\u0000\u0000\u000020\u0001\u0000\u0000"+
		"\u000035\u0003\u0000\u0000\u000043\u0001\u0000\u0000\u000045\u0001\u0000"+
		"\u0000\u000056\u0001\u0000\u0000\u000067\u0005\u0004\u0000\u00007\u0003"+
		"\u0001\u0000\u0000\u00008=\u0005\u001e\u0000\u00009:\u0005\u0005\u0000"+
		"\u0000:<\u0005\u001e\u0000\u0000;9\u0001\u0000\u0000\u0000<?\u0001\u0000"+
		"\u0000\u0000=;\u0001\u0000\u0000\u0000=>\u0001\u0000\u0000\u0000>\u0005"+
		"\u0001\u0000\u0000\u0000?=\u0001\u0000\u0000\u0000@C\u0005\u001e\u0000"+
		"\u0000AB\u0005\u0006\u0000\u0000BD\u0003\f\u0006\u0000CA\u0001\u0000\u0000"+
		"\u0000CD\u0001\u0000\u0000\u0000DG\u0001\u0000\u0000\u0000EF\u0005\u0001"+
		"\u0000\u0000FH\u0003\u000e\u0007\u0000GE\u0001\u0000\u0000\u0000GH\u0001"+
		"\u0000\u0000\u0000H\u0007\u0001\u0000\u0000\u0000IO\u0005\u0002\u0000"+
		"\u0000JK\u0003\u0006\u0003\u0000KL\u0005\u0003\u0000\u0000LN\u0001\u0000"+
		"\u0000\u0000MJ\u0001\u0000\u0000\u0000NQ\u0001\u0000\u0000\u0000OM\u0001"+
		"\u0000\u0000\u0000OP\u0001\u0000\u0000\u0000PS\u0001\u0000\u0000\u0000"+
		"QO\u0001\u0000\u0000\u0000RT\u0003\u0006\u0003\u0000SR\u0001\u0000\u0000"+
		"\u0000ST\u0001\u0000\u0000\u0000TU\u0001\u0000\u0000\u0000UV\u0005\u0004"+
		"\u0000\u0000V\t\u0001\u0000\u0000\u0000WX\u0003\b\u0004\u0000XY\u0005"+
		"\u001c\u0000\u0000YZ\u0003\f\u0006\u0000Z\u000b\u0001\u0000\u0000\u0000"+
		"[_\u0003\u0004\u0002\u0000\\_\u0003\b\u0004\u0000]_\u0003\n\u0005\u0000"+
		"^[\u0001\u0000\u0000\u0000^\\\u0001\u0000\u0000\u0000^]\u0001\u0000\u0000"+
		"\u0000_\r\u0001\u0000\u0000\u0000`a\u0006\u0007\uffff\uffff\u0000a~\u0003"+
		"\u0002\u0001\u0000bc\u0005\u0019\u0000\u0000cd\u0005\u0006\u0000\u0000"+
		"di\u0003\u0004\u0002\u0000ef\u0005\u000f\u0000\u0000fh\u0003\u0004\u0002"+
		"\u0000ge\u0001\u0000\u0000\u0000hk\u0001\u0000\u0000\u0000ig\u0001\u0000"+
		"\u0000\u0000ij\u0001\u0000\u0000\u0000jt\u0001\u0000\u0000\u0000ki\u0001"+
		"\u0000\u0000\u0000lp\u0005\u0010\u0000\u0000mo\u0003\u0014\n\u0000nm\u0001"+
		"\u0000\u0000\u0000or\u0001\u0000\u0000\u0000pn\u0001\u0000\u0000\u0000"+
		"pq\u0001\u0000\u0000\u0000qs\u0001\u0000\u0000\u0000rp\u0001\u0000\u0000"+
		"\u0000su\u0005\u0011\u0000\u0000tl\u0001\u0000\u0000\u0000tu\u0001\u0000"+
		"\u0000\u0000u~\u0001\u0000\u0000\u0000vw\u0003\b\u0004\u0000wx\u0005\u001c"+
		"\u0000\u0000xy\u0003\u000e\u0007\u0004y~\u0001\u0000\u0000\u0000z~\u0005"+
		" \u0000\u0000{~\u0005\u001f\u0000\u0000|~\u0005\u001e\u0000\u0000}`\u0001"+
		"\u0000\u0000\u0000}b\u0001\u0000\u0000\u0000}v\u0001\u0000\u0000\u0000"+
		"}z\u0001\u0000\u0000\u0000}{\u0001\u0000\u0000\u0000}|\u0001\u0000\u0000"+
		"\u0000~\u009a\u0001\u0000\u0000\u0000\u007f\u0080\n\n\u0000\u0000\u0080"+
		"\u0081\u0007\u0000\u0000\u0000\u0081\u0099\u0003\u000e\u0007\u000b\u0082"+
		"\u0083\n\t\u0000\u0000\u0083\u0084\u0007\u0001\u0000\u0000\u0084\u0099"+
		"\u0003\u000e\u0007\n\u0085\u0086\n\b\u0000\u0000\u0086\u0087\u0007\u0002"+
		"\u0000\u0000\u0087\u0099\u0003\u000e\u0007\t\u0088\u0089\n\u0007\u0000"+
		"\u0000\u0089\u008a\u0005\u000e\u0000\u0000\u008a\u008b\u0003\u000e\u0007"+
		"\u0000\u008b\u008c\u0005\u0006\u0000\u0000\u008c\u008d\u0003\u000e\u0007"+
		"\b\u008d\u0099\u0001\u0000\u0000\u0000\u008e\u008f\n\r\u0000\u0000\u008f"+
		"\u0090\u0005\u0005\u0000\u0000\u0090\u0099\u0005\u001e\u0000\u0000\u0091"+
		"\u0092\n\f\u0000\u0000\u0092\u0099\u0003\u0002\u0001\u0000\u0093\u0094"+
		"\n\u000b\u0000\u0000\u0094\u0095\u0005\u001d\u0000\u0000\u0095\u0096\u0003"+
		"\u000e\u0007\u0000\u0096\u0097\u0003\u0002\u0001\u0000\u0097\u0099\u0001"+
		"\u0000\u0000\u0000\u0098\u007f\u0001\u0000\u0000\u0000\u0098\u0082\u0001"+
		"\u0000\u0000\u0000\u0098\u0085\u0001\u0000\u0000\u0000\u0098\u0088\u0001"+
		"\u0000\u0000\u0000\u0098\u008e\u0001\u0000\u0000\u0000\u0098\u0091\u0001"+
		"\u0000\u0000\u0000\u0098\u0093\u0001\u0000\u0000\u0000\u0099\u009c\u0001"+
		"\u0000\u0000\u0000\u009a\u0098\u0001\u0000\u0000\u0000\u009a\u009b\u0001"+
		"\u0000\u0000\u0000\u009b\u000f\u0001\u0000\u0000\u0000\u009c\u009a\u0001"+
		"\u0000\u0000\u0000\u009d\u009e\u0005\u0012\u0000\u0000\u009e\u009f\u0003"+
		"\u0004\u0002\u0000\u009f\u0011\u0001\u0000\u0000\u0000\u00a0\u00a1\u0005"+
		"\u0013\u0000\u0000\u00a1\u00a2\u0003\u0004\u0002\u0000\u00a2\u0013\u0001"+
		"\u0000\u0000\u0000\u00a3\u00a4\u0005\u0014\u0000\u0000\u00a4\u00a6\u0005"+
		"\u001e\u0000\u0000\u00a5\u00a7\u0003\b\u0004\u0000\u00a6\u00a5\u0001\u0000"+
		"\u0000\u0000\u00a6\u00a7\u0001\u0000\u0000\u0000\u00a7\u00aa\u0001\u0000"+
		"\u0000\u0000\u00a8\u00a9\u0005\u0006\u0000\u0000\u00a9\u00ab\u0003\f\u0006"+
		"\u0000\u00aa\u00a8\u0001\u0000\u0000\u0000\u00aa\u00ab\u0001\u0000\u0000"+
		"\u0000\u00ab\u00ae\u0001\u0000\u0000\u0000\u00ac\u00ad\u0005\u0001\u0000"+
		"\u0000\u00ad\u00af\u0003\u000e\u0007\u0000\u00ae\u00ac\u0001\u0000\u0000"+
		"\u0000\u00ae\u00af\u0001\u0000\u0000\u0000\u00af\u0015\u0001\u0000\u0000"+
		"\u0000\u00b0\u00b1\u0005\u0015\u0000\u0000\u00b1\u00b4\u0005\u001e\u0000"+
		"\u0000\u00b2\u00b3\u0005\u0006\u0000\u0000\u00b3\u00b5\u0003\f\u0006\u0000"+
		"\u00b4\u00b2\u0001\u0000\u0000\u0000\u00b4\u00b5\u0001\u0000\u0000\u0000"+
		"\u00b5\u00b6\u0001\u0000\u0000\u0000\u00b6\u00b7\u0005\u0001\u0000\u0000"+
		"\u00b7\u00b8\u0003\u000e\u0007\u0000\u00b8\u0017\u0001\u0000\u0000\u0000"+
		"\u00b9\u00ba\u0005\u0017\u0000\u0000\u00ba\u00c4\u0005\u001e\u0000\u0000"+
		"\u00bb\u00bc\u0005\u0006\u0000\u0000\u00bc\u00c1\u0003\u0004\u0002\u0000"+
		"\u00bd\u00be\u0005\u000f\u0000\u0000\u00be\u00c0\u0003\u0004\u0002\u0000"+
		"\u00bf\u00bd\u0001\u0000\u0000\u0000\u00c0\u00c3\u0001\u0000\u0000\u0000"+
		"\u00c1\u00bf\u0001\u0000\u0000\u0000\u00c1\u00c2\u0001\u0000\u0000\u0000"+
		"\u00c2\u00c5\u0001\u0000\u0000\u0000\u00c3\u00c1\u0001\u0000\u0000\u0000"+
		"\u00c4\u00bb\u0001\u0000\u0000\u0000\u00c4\u00c5\u0001\u0000\u0000\u0000"+
		"\u00c5\u00ce\u0001\u0000\u0000\u0000\u00c6\u00c8\u0005\u0010\u0000\u0000"+
		"\u00c7\u00c9\u0003\u0014\n\u0000\u00c8\u00c7\u0001\u0000\u0000\u0000\u00c9"+
		"\u00ca\u0001\u0000\u0000\u0000\u00ca\u00c8\u0001\u0000\u0000\u0000\u00ca"+
		"\u00cb\u0001\u0000\u0000\u0000\u00cb\u00cc\u0001\u0000\u0000\u0000\u00cc"+
		"\u00cd\u0005\u0011\u0000\u0000\u00cd\u00cf\u0001\u0000\u0000\u0000\u00ce"+
		"\u00c6\u0001\u0000\u0000\u0000\u00ce\u00cf\u0001\u0000\u0000\u0000\u00cf"+
		"\u0019\u0001\u0000\u0000\u0000\u00d0\u00d1\u0005\u0018\u0000\u0000\u00d1"+
		"\u00d3\u0005\u001e\u0000\u0000\u00d2\u00d4\u0003\b\u0004\u0000\u00d3\u00d2"+
		"\u0001\u0000\u0000\u0000\u00d3\u00d4\u0001\u0000\u0000\u0000\u00d4\u00de"+
		"\u0001\u0000\u0000\u0000\u00d5\u00d6\u0005\u0006\u0000\u0000\u00d6\u00db"+
		"\u0003\u0004\u0002\u0000\u00d7\u00d8\u0005\u000f\u0000\u0000\u00d8\u00da"+
		"\u0003\u0004\u0002\u0000\u00d9\u00d7\u0001\u0000\u0000\u0000\u00da\u00dd"+
		"\u0001\u0000\u0000\u0000\u00db\u00d9\u0001\u0000\u0000\u0000\u00db\u00dc"+
		"\u0001\u0000\u0000\u0000\u00dc\u00df\u0001\u0000\u0000\u0000\u00dd\u00db"+
		"\u0001\u0000\u0000\u0000\u00de\u00d5\u0001\u0000\u0000\u0000\u00de\u00df"+
		"\u0001\u0000\u0000\u0000\u00df\u00e8\u0001\u0000\u0000\u0000\u00e0\u00e4"+
		"\u0005\u0010\u0000\u0000\u00e1\u00e3\u0003\u0014\n\u0000\u00e2\u00e1\u0001"+
		"\u0000\u0000\u0000\u00e3\u00e6\u0001\u0000\u0000\u0000\u00e4\u00e2\u0001"+
		"\u0000\u0000\u0000\u00e4\u00e5\u0001\u0000\u0000\u0000\u00e5\u00e7\u0001"+
		"\u0000\u0000\u0000\u00e6\u00e4\u0001\u0000\u0000\u0000\u00e7\u00e9\u0005"+
		"\u0011\u0000\u0000\u00e8\u00e0\u0001\u0000\u0000\u0000\u00e8\u00e9\u0001"+
		"\u0000\u0000\u0000\u00e9\u001b\u0001\u0000\u0000\u0000\u00ea\u00eb\u0005"+
		"\u0016\u0000\u0000\u00eb\u00ec\u0005\u001e\u0000\u0000\u00ec\u00f5\u0003"+
		"\b\u0004\u0000\u00ed\u00f1\u0005\u0010\u0000\u0000\u00ee\u00f0\u0003\u0014"+
		"\n\u0000\u00ef\u00ee\u0001\u0000\u0000\u0000\u00f0\u00f3\u0001\u0000\u0000"+
		"\u0000\u00f1\u00ef\u0001\u0000\u0000\u0000\u00f1\u00f2\u0001\u0000\u0000"+
		"\u0000\u00f2\u00f4\u0001\u0000\u0000\u0000\u00f3\u00f1\u0001\u0000\u0000"+
		"\u0000\u00f4\u00f6\u0005\u0011\u0000\u0000\u00f5\u00ed\u0001\u0000\u0000"+
		"\u0000\u00f5\u00f6\u0001\u0000\u0000\u0000\u00f6\u001d\u0001\u0000\u0000"+
		"\u0000\u00f7\u00f8\u0005\u001a\u0000\u0000\u00f8\u0105\u0005\u001e\u0000"+
		"\u0000\u00f9\u0101\u0005\u0010\u0000\u0000\u00fa\u00fc\u0005\u001e\u0000"+
		"\u0000\u00fb\u00fd\u0003\b\u0004\u0000\u00fc\u00fb\u0001\u0000\u0000\u0000"+
		"\u00fc\u00fd\u0001\u0000\u0000\u0000\u00fd\u0100\u0001\u0000\u0000\u0000"+
		"\u00fe\u0100\u0003\u0014\n\u0000\u00ff\u00fa\u0001\u0000\u0000\u0000\u00ff"+
		"\u00fe\u0001\u0000\u0000\u0000\u0100\u0103\u0001\u0000\u0000\u0000\u0101"+
		"\u00ff\u0001\u0000\u0000\u0000\u0101\u0102\u0001\u0000\u0000\u0000\u0102"+
		"\u0104\u0001\u0000\u0000\u0000\u0103\u0101\u0001\u0000\u0000\u0000\u0104"+
		"\u0106\u0005\u0011\u0000\u0000\u0105\u00f9\u0001\u0000\u0000\u0000\u0105"+
		"\u0106\u0001\u0000\u0000\u0000\u0106\u001f\u0001\u0000\u0000\u0000\u0107"+
		"\u010e\u0003\u0016\u000b\u0000\u0108\u010e\u0003\u0014\n\u0000\u0109\u010e"+
		"\u0003\u0018\f\u0000\u010a\u010e\u0003\u001a\r\u0000\u010b\u010e\u0003"+
		"\u001c\u000e\u0000\u010c\u010e\u0003\u001e\u000f\u0000\u010d\u0107\u0001"+
		"\u0000\u0000\u0000\u010d\u0108\u0001\u0000\u0000\u0000\u010d\u0109\u0001"+
		"\u0000\u0000\u0000\u010d\u010a\u0001\u0000\u0000\u0000\u010d\u010b\u0001"+
		"\u0000\u0000\u0000\u010d\u010c\u0001\u0000\u0000\u0000\u010e!\u0001\u0000"+
		"\u0000\u0000\u010f\u0113\u0003\u0010\b\u0000\u0110\u0112\u0003\u0012\t"+
		"\u0000\u0111\u0110\u0001\u0000\u0000\u0000\u0112\u0115\u0001\u0000\u0000"+
		"\u0000\u0113\u0111\u0001\u0000\u0000\u0000\u0113\u0114\u0001\u0000\u0000"+
		"\u0000\u0114\u0119\u0001\u0000\u0000\u0000\u0115\u0113\u0001\u0000\u0000"+
		"\u0000\u0116\u0118\u0003 \u0010\u0000\u0117\u0116\u0001\u0000\u0000\u0000"+
		"\u0118\u011b\u0001\u0000\u0000\u0000\u0119\u0117\u0001\u0000\u0000\u0000"+
		"\u0119\u011a\u0001\u0000\u0000\u0000\u011a\u011c\u0001\u0000\u0000\u0000"+
		"\u011b\u0119\u0001\u0000\u0000\u0000\u011c\u011d\u0005\u0000\u0000\u0001"+
		"\u011d#\u0001\u0000\u0000\u0000%&04=CGOS^ipt}\u0098\u009a\u00a6\u00aa"+
		"\u00ae\u00b4\u00c1\u00c4\u00ca\u00ce\u00d3\u00db\u00de\u00e4\u00e8\u00f1"+
		"\u00f5\u00fc\u00ff\u0101\u0105\u010d\u0113\u0119";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}