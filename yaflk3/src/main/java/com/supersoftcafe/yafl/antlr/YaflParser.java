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
		T__17=18, T__18=19, T__19=20, T__20=21, T__21=22, LLVM_IR=23, PRIMITIVE=24, 
		ASSERT=25, RAW_POINTER=26, PARALLEL=27, MODULE=28, IMPORT=29, ALIAS=30, 
		FUN=31, LET=32, INTERFACE=33, TRAIT=34, IMPL=35, CLASS=36, OBJECT=37, 
		ENUM=38, LAZY=39, LAMBDA=40, PIPE_RIGHT=41, PIPE_MAYBE=42, NAMESPACE=43, 
		CMP_LE=44, CMP_GE=45, CMP_EQ=46, CMP_NE=47, SHL=48, SHR=49, POW=50, NAME=51, 
		INTEGER=52, STRING=53, WS=54, COMMENT=55;
	public static final int
		RULE_qualifiedName = 0, RULE_exprOfTuplePart = 1, RULE_exprOfTuple = 2, 
		RULE_genericParamsPassing = 3, RULE_genericParamsDeclare = 4, RULE_typeRef = 5, 
		RULE_typePrimitive = 6, RULE_typeOfTuplePart = 7, RULE_typeOfTuple = 8, 
		RULE_typeOfLambda = 9, RULE_type = 10, RULE_attributes = 11, RULE_valueParamsPart = 12, 
		RULE_valueParamsDeclare = 13, RULE_expression = 14, RULE_let = 15, RULE_function = 16, 
		RULE_interface = 17, RULE_class = 18, RULE_enum = 19, RULE_alias = 20, 
		RULE_extends = 21, RULE_module = 22, RULE_import_ = 23, RULE_declaration = 24, 
		RULE_classMember = 25, RULE_root = 26;
	private static String[] makeRuleNames() {
		return new String[] {
			"qualifiedName", "exprOfTuplePart", "exprOfTuple", "genericParamsPassing", 
			"genericParamsDeclare", "typeRef", "typePrimitive", "typeOfTuplePart", 
			"typeOfTuple", "typeOfLambda", "type", "attributes", "valueParamsPart", 
			"valueParamsDeclare", "expression", "let", "function", "interface", "class", 
			"enum", "alias", "extends", "module", "import_", "declaration", "classMember", 
			"root"
		};
	}
	public static final String[] ruleNames = makeRuleNames();

	private static String[] makeLiteralNames() {
		return new String[] {
			null, "'='", "'('", "','", "')'", "'<'", "'>'", "':'", "'['", "']'", 
			"'.'", "'+'", "'-'", "'*'", "'/'", "'%'", "'&'", "'^'", "'|'", "'?'", 
			"'{'", "'}'", "';'", "'__llvm_ir__'", "'__primitive__'", "'__assert__'", 
			"'__raw_pointer__'", "'__parallel__'", "'module'", "'import'", "'alias'", 
			"'fun'", "'let'", "'interface'", "'trait'", "'impl'", "'class'", "'object'", 
			"'enum'", "'lazy'", "'=>'", "'|>'", "'?>'", "'::'", "'<='", "'>='", "'=='", 
			"'!='", "'<<'", "'>>'", "'**'"
		};
	}
	private static final String[] _LITERAL_NAMES = makeLiteralNames();
	private static String[] makeSymbolicNames() {
		return new String[] {
			null, null, null, null, null, null, null, null, null, null, null, null, 
			null, null, null, null, null, null, null, null, null, null, null, "LLVM_IR", 
			"PRIMITIVE", "ASSERT", "RAW_POINTER", "PARALLEL", "MODULE", "IMPORT", 
			"ALIAS", "FUN", "LET", "INTERFACE", "TRAIT", "IMPL", "CLASS", "OBJECT", 
			"ENUM", "LAZY", "LAMBDA", "PIPE_RIGHT", "PIPE_MAYBE", "NAMESPACE", "CMP_LE", 
			"CMP_GE", "CMP_EQ", "CMP_NE", "SHL", "SHR", "POW", "NAME", "INTEGER", 
			"STRING", "WS", "COMMENT"
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
		public List<TerminalNode> NAME() { return getTokens(YaflParser.NAME); }
		public TerminalNode NAME(int i) {
			return getToken(YaflParser.NAME, i);
		}
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
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(58);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,0,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(54);
					match(NAME);
					setState(55);
					match(NAMESPACE);
					}
					} 
				}
				setState(60);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,0,_ctx);
			}
			setState(61);
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
			setState(65);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,1,_ctx) ) {
			case 1:
				{
				setState(63);
				match(NAME);
				setState(64);
				match(T__0);
				}
				break;
			}
			setState(67);
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
			setState(69);
			match(T__1);
			setState(75);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,2,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(70);
					exprOfTuplePart();
					setState(71);
					match(T__2);
					}
					} 
				}
				setState(77);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,2,_ctx);
			}
			setState(79);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__1) | (1L << T__7) | (1L << T__10) | (1L << T__11) | (1L << LLVM_IR) | (1L << ASSERT) | (1L << RAW_POINTER) | (1L << PARALLEL) | (1L << FUN) | (1L << LET) | (1L << OBJECT) | (1L << NAME) | (1L << INTEGER) | (1L << STRING))) != 0)) {
				{
				setState(78);
				exprOfTuplePart();
				}
			}

			setState(81);
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

	public static class GenericParamsPassingContext extends ParserRuleContext {
		public List<TypeContext> type() {
			return getRuleContexts(TypeContext.class);
		}
		public TypeContext type(int i) {
			return getRuleContext(TypeContext.class,i);
		}
		public GenericParamsPassingContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_genericParamsPassing; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterGenericParamsPassing(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitGenericParamsPassing(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitGenericParamsPassing(this);
			else return visitor.visitChildren(this);
		}
	}

	public final GenericParamsPassingContext genericParamsPassing() throws RecognitionException {
		GenericParamsPassingContext _localctx = new GenericParamsPassingContext(_ctx, getState());
		enterRule(_localctx, 6, RULE_genericParamsPassing);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(83);
			match(T__4);
			setState(89);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,4,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(84);
					type();
					setState(85);
					match(T__2);
					}
					} 
				}
				setState(91);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,4,_ctx);
			}
			setState(93);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__1) | (1L << PRIMITIVE) | (1L << NAME))) != 0)) {
				{
				setState(92);
				type();
				}
			}

			setState(95);
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

	public static class GenericParamsDeclareContext extends ParserRuleContext {
		public List<TerminalNode> NAME() { return getTokens(YaflParser.NAME); }
		public TerminalNode NAME(int i) {
			return getToken(YaflParser.NAME, i);
		}
		public GenericParamsDeclareContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_genericParamsDeclare; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterGenericParamsDeclare(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitGenericParamsDeclare(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitGenericParamsDeclare(this);
			else return visitor.visitChildren(this);
		}
	}

	public final GenericParamsDeclareContext genericParamsDeclare() throws RecognitionException {
		GenericParamsDeclareContext _localctx = new GenericParamsDeclareContext(_ctx, getState());
		enterRule(_localctx, 8, RULE_genericParamsDeclare);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(97);
			match(T__4);
			setState(102);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,6,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(98);
					match(NAME);
					setState(99);
					match(T__2);
					}
					} 
				}
				setState(104);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,6,_ctx);
			}
			setState(106);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==NAME) {
				{
				setState(105);
				match(NAME);
				}
			}

			setState(108);
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

	public static class TypeRefContext extends ParserRuleContext {
		public QualifiedNameContext qualifiedName() {
			return getRuleContext(QualifiedNameContext.class,0);
		}
		public GenericParamsPassingContext genericParamsPassing() {
			return getRuleContext(GenericParamsPassingContext.class,0);
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
		enterRule(_localctx, 10, RULE_typeRef);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(110);
			qualifiedName();
			setState(112);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,8,_ctx) ) {
			case 1:
				{
				setState(111);
				genericParamsPassing();
				}
				break;
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
		enterRule(_localctx, 12, RULE_typePrimitive);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(114);
			match(PRIMITIVE);
			setState(115);
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
		enterRule(_localctx, 14, RULE_typeOfTuplePart);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(119);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,9,_ctx) ) {
			case 1:
				{
				setState(117);
				match(NAME);
				setState(118);
				match(T__6);
				}
				break;
			}
			setState(121);
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
		enterRule(_localctx, 16, RULE_typeOfTuple);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(123);
			match(T__1);
			setState(129);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,10,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(124);
					typeOfTuplePart();
					setState(125);
					match(T__2);
					}
					} 
				}
				setState(131);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,10,_ctx);
			}
			setState(133);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__1) | (1L << PRIMITIVE) | (1L << NAME))) != 0)) {
				{
				setState(132);
				typeOfTuplePart();
				}
			}

			setState(135);
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
		enterRule(_localctx, 18, RULE_typeOfLambda);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(137);
			typeOfTuple();
			setState(138);
			match(T__6);
			setState(139);
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
		enterRule(_localctx, 20, RULE_type);
		try {
			setState(145);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,12,_ctx) ) {
			case 1:
				_localctx = new NamedTypeContext(_localctx);
				enterOuterAlt(_localctx, 1);
				{
				setState(141);
				typeRef();
				}
				break;
			case 2:
				_localctx = new PrimitiveTypeContext(_localctx);
				enterOuterAlt(_localctx, 2);
				{
				setState(142);
				typePrimitive();
				}
				break;
			case 3:
				_localctx = new TupleTypeContext(_localctx);
				enterOuterAlt(_localctx, 3);
				{
				setState(143);
				typeOfTuple();
				}
				break;
			case 4:
				_localctx = new LambdaTypeContext(_localctx);
				enterOuterAlt(_localctx, 4);
				{
				setState(144);
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
		enterRule(_localctx, 22, RULE_attributes);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(147);
			match(T__7);
			setState(151);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==NAME) {
				{
				{
				setState(148);
				match(NAME);
				}
				}
				setState(153);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(154);
			match(T__8);
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

	public static class ValueParamsPartContext extends ParserRuleContext {
		public ValueParamsDeclareContext valueParamsDeclare() {
			return getRuleContext(ValueParamsDeclareContext.class,0);
		}
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public TerminalNode INTEGER() { return getToken(YaflParser.INTEGER, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode CMP_LE() { return getToken(YaflParser.CMP_LE, 0); }
		public ValueParamsPartContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_valueParamsPart; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterValueParamsPart(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitValueParamsPart(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitValueParamsPart(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ValueParamsPartContext valueParamsPart() throws RecognitionException {
		ValueParamsPartContext _localctx = new ValueParamsPartContext(_ctx, getState());
		enterRule(_localctx, 24, RULE_valueParamsPart);
		int _la;
		try {
			setState(172);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case T__1:
				enterOuterAlt(_localctx, 1);
				{
				setState(156);
				valueParamsDeclare();
				}
				break;
			case NAME:
				enterOuterAlt(_localctx, 2);
				{
				{
				setState(157);
				match(NAME);
				setState(166);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__7) {
					{
					setState(158);
					match(T__7);
					setState(162);
					_errHandler.sync(this);
					switch ( getInterpreter().adaptivePredict(_input,14,_ctx) ) {
					case 1:
						{
						setState(159);
						expression(0);
						setState(160);
						match(CMP_LE);
						}
						break;
					}
					setState(164);
					match(INTEGER);
					setState(165);
					match(T__8);
					}
				}

				setState(170);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__6) {
					{
					setState(168);
					match(T__6);
					setState(169);
					type();
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

	public static class ValueParamsDeclareContext extends ParserRuleContext {
		public List<ValueParamsPartContext> valueParamsPart() {
			return getRuleContexts(ValueParamsPartContext.class);
		}
		public ValueParamsPartContext valueParamsPart(int i) {
			return getRuleContext(ValueParamsPartContext.class,i);
		}
		public ValueParamsDeclareContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_valueParamsDeclare; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterValueParamsDeclare(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitValueParamsDeclare(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitValueParamsDeclare(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ValueParamsDeclareContext valueParamsDeclare() throws RecognitionException {
		ValueParamsDeclareContext _localctx = new ValueParamsDeclareContext(_ctx, getState());
		enterRule(_localctx, 26, RULE_valueParamsDeclare);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(174);
			match(T__1);
			setState(180);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,18,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(175);
					valueParamsPart();
					setState(176);
					match(T__2);
					}
					} 
				}
				setState(182);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,18,_ctx);
			}
			setState(184);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__1 || _la==NAME) {
				{
				setState(183);
				valueParamsPart();
				}
			}

			setState(186);
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
	public static class AssertExprContext extends ExpressionContext {
		public ExpressionContext value;
		public ExpressionContext condition;
		public Token message;
		public TerminalNode ASSERT() { return getToken(YaflParser.ASSERT, 0); }
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public TerminalNode STRING() { return getToken(YaflParser.STRING, 0); }
		public AssertExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterAssertExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitAssertExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitAssertExpr(this);
			else return visitor.visitChildren(this);
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
	public static class PowerExprContext extends ExpressionContext {
		public ExpressionContext left;
		public Token operator;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public TerminalNode POW() { return getToken(YaflParser.POW, 0); }
		public PowerExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterPowerExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitPowerExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitPowerExpr(this);
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
		public LetContext let() {
			return getRuleContext(LetContext.class,0);
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
		public GenericParamsPassingContext genericParamsPassing() {
			return getRuleContext(GenericParamsPassingContext.class,0);
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
	public static class ParallelExprContext extends ExpressionContext {
		public ExprOfTupleContext params;
		public TerminalNode PARALLEL() { return getToken(YaflParser.PARALLEL, 0); }
		public ExprOfTupleContext exprOfTuple() {
			return getRuleContext(ExprOfTupleContext.class,0);
		}
		public ParallelExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterParallelExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitParallelExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitParallelExpr(this);
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
	public static class LambdaExprContext extends ExpressionContext {
		public ValueParamsDeclareContext valueParamsDeclare() {
			return getRuleContext(ValueParamsDeclareContext.class,0);
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
	public static class NewArrayExprContext extends ExpressionContext {
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public NewArrayExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterNewArrayExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitNewArrayExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitNewArrayExpr(this);
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
	public static class RawPointerExprContext extends ExpressionContext {
		public ExpressionContext value;
		public TerminalNode RAW_POINTER() { return getToken(YaflParser.RAW_POINTER, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public RawPointerExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterRawPointerExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitRawPointerExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitRawPointerExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class ArrayLookupExprContext extends ExpressionContext {
		public ExpressionContext left;
		public ExpressionContext right;
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public ArrayLookupExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterArrayLookupExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitArrayLookupExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitArrayLookupExpr(this);
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
			setState(283);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,30,_ctx) ) {
			case 1:
				{
				_localctx = new LlvmirExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;

				setState(189);
				match(LLVM_IR);
				setState(190);
				match(T__4);
				setState(191);
				type();
				setState(192);
				match(T__5);
				setState(193);
				match(T__1);
				setState(194);
				((LlvmirExprContext)_localctx).pattern = match(STRING);
				setState(199);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==T__2) {
					{
					{
					setState(195);
					match(T__2);
					setState(196);
					expression(0);
					}
					}
					setState(201);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(202);
				match(T__3);
				}
				break;
			case 2:
				{
				_localctx = new AssertExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(204);
				match(ASSERT);
				setState(205);
				match(T__1);
				setState(206);
				((AssertExprContext)_localctx).value = expression(0);
				setState(207);
				match(T__2);
				setState(208);
				((AssertExprContext)_localctx).condition = expression(0);
				setState(209);
				match(T__2);
				setState(210);
				((AssertExprContext)_localctx).message = match(STRING);
				setState(211);
				match(T__3);
				}
				break;
			case 3:
				{
				_localctx = new RawPointerExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(213);
				match(RAW_POINTER);
				setState(214);
				match(T__1);
				setState(215);
				((RawPointerExprContext)_localctx).value = expression(0);
				setState(216);
				match(T__3);
				}
				break;
			case 4:
				{
				_localctx = new ParallelExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(218);
				match(PARALLEL);
				setState(219);
				((ParallelExprContext)_localctx).params = exprOfTuple();
				}
				break;
			case 5:
				{
				_localctx = new UnaryExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(220);
				((UnaryExprContext)_localctx).operator = _input.LT(1);
				_la = _input.LA(1);
				if ( !(_la==T__10 || _la==T__11) ) {
					((UnaryExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
				}
				else {
					if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
					_errHandler.reportMatch(this);
					consume();
				}
				setState(221);
				((UnaryExprContext)_localctx).right = expression(20);
				}
				break;
			case 6:
				{
				_localctx = new TupleExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(222);
				exprOfTuple();
				}
				break;
			case 7:
				{
				_localctx = new ObjectExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(223);
				match(OBJECT);
				setState(224);
				match(T__6);
				setState(225);
				typeRef();
				setState(230);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,21,_ctx);
				while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
					if ( _alt==1 ) {
						{
						{
						setState(226);
						match(T__17);
						setState(227);
						typeRef();
						}
						} 
					}
					setState(232);
					_errHandler.sync(this);
					_alt = getInterpreter().adaptivePredict(_input,21,_ctx);
				}
				setState(241);
				_errHandler.sync(this);
				switch ( getInterpreter().adaptivePredict(_input,23,_ctx) ) {
				case 1:
					{
					setState(233);
					match(T__19);
					setState(237);
					_errHandler.sync(this);
					_la = _input.LA(1);
					while (_la==FUN) {
						{
						{
						setState(234);
						function();
						}
						}
						setState(239);
						_errHandler.sync(this);
						_la = _input.LA(1);
					}
					setState(240);
					match(T__20);
					}
					break;
				}
				}
				break;
			case 8:
				{
				_localctx = new LetExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(243);
				let();
				setState(245);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__21) {
					{
					setState(244);
					match(T__21);
					}
				}

				setState(247);
				expression(7);
				}
				break;
			case 9:
				{
				_localctx = new FunctionExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(249);
				function();
				setState(251);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__21) {
					{
					setState(250);
					match(T__21);
					}
				}

				setState(253);
				expression(6);
				}
				break;
			case 10:
				{
				_localctx = new LambdaExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(255);
				valueParamsDeclare();
				setState(258);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__6) {
					{
					setState(256);
					match(T__6);
					setState(257);
					type();
					}
				}

				setState(260);
				match(LAMBDA);
				setState(261);
				expression(5);
				}
				break;
			case 11:
				{
				_localctx = new NewArrayExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(263);
				match(T__7);
				setState(264);
				expression(0);
				setState(269);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,27,_ctx);
				while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
					if ( _alt==1 ) {
						{
						{
						setState(265);
						match(T__2);
						setState(266);
						expression(0);
						}
						} 
					}
					setState(271);
					_errHandler.sync(this);
					_alt = getInterpreter().adaptivePredict(_input,27,_ctx);
				}
				setState(273);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__2) {
					{
					setState(272);
					match(T__2);
					}
				}

				setState(275);
				match(T__8);
				}
				break;
			case 12:
				{
				_localctx = new StringExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(277);
				match(STRING);
				}
				break;
			case 13:
				{
				_localctx = new IntegerExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(278);
				match(INTEGER);
				}
				break;
			case 14:
				{
				_localctx = new NameExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(279);
				qualifiedName();
				setState(281);
				_errHandler.sync(this);
				switch ( getInterpreter().adaptivePredict(_input,29,_ctx) ) {
				case 1:
					{
					setState(280);
					genericParamsPassing();
					}
					break;
				}
				}
				break;
			}
			_ctx.stop = _input.LT(-1);
			setState(335);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,32,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					if ( _parseListeners!=null ) triggerExitRuleEvent();
					_prevctx = _localctx;
					{
					setState(333);
					_errHandler.sync(this);
					switch ( getInterpreter().adaptivePredict(_input,31,_ctx) ) {
					case 1:
						{
						_localctx = new PowerExprContext(new ExpressionContext(_parentctx, _parentState));
						((PowerExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(285);
						if (!(precpred(_ctx, 19))) throw new FailedPredicateException(this, "precpred(_ctx, 19)");
						setState(286);
						((PowerExprContext)_localctx).operator = match(POW);
						setState(287);
						((PowerExprContext)_localctx).right = expression(20);
						}
						break;
					case 2:
						{
						_localctx = new ProductExprContext(new ExpressionContext(_parentctx, _parentState));
						((ProductExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(288);
						if (!(precpred(_ctx, 18))) throw new FailedPredicateException(this, "precpred(_ctx, 18)");
						setState(289);
						((ProductExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__12) | (1L << T__13) | (1L << T__14))) != 0)) ) {
							((ProductExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(290);
						((ProductExprContext)_localctx).right = expression(19);
						}
						break;
					case 3:
						{
						_localctx = new SumExprContext(new ExpressionContext(_parentctx, _parentState));
						((SumExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(291);
						if (!(precpred(_ctx, 17))) throw new FailedPredicateException(this, "precpred(_ctx, 17)");
						setState(292);
						((SumExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !(_la==T__10 || _la==T__11) ) {
							((SumExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(293);
						((SumExprContext)_localctx).right = expression(18);
						}
						break;
					case 4:
						{
						_localctx = new ShiftExprContext(new ExpressionContext(_parentctx, _parentState));
						((ShiftExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(294);
						if (!(precpred(_ctx, 16))) throw new FailedPredicateException(this, "precpred(_ctx, 16)");
						setState(295);
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
						setState(296);
						((ShiftExprContext)_localctx).right = expression(17);
						}
						break;
					case 5:
						{
						_localctx = new CompareExprContext(new ExpressionContext(_parentctx, _parentState));
						((CompareExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(297);
						if (!(precpred(_ctx, 15))) throw new FailedPredicateException(this, "precpred(_ctx, 15)");
						setState(298);
						((CompareExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__4) | (1L << T__5) | (1L << CMP_LE) | (1L << CMP_GE))) != 0)) ) {
							((CompareExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(299);
						((CompareExprContext)_localctx).right = expression(16);
						}
						break;
					case 6:
						{
						_localctx = new EqualExprContext(new ExpressionContext(_parentctx, _parentState));
						((EqualExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(300);
						if (!(precpred(_ctx, 14))) throw new FailedPredicateException(this, "precpred(_ctx, 14)");
						setState(301);
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
						setState(302);
						((EqualExprContext)_localctx).right = expression(15);
						}
						break;
					case 7:
						{
						_localctx = new BitAndExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitAndExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(303);
						if (!(precpred(_ctx, 13))) throw new FailedPredicateException(this, "precpred(_ctx, 13)");
						setState(304);
						((BitAndExprContext)_localctx).operator = match(T__15);
						setState(305);
						((BitAndExprContext)_localctx).right = expression(14);
						}
						break;
					case 8:
						{
						_localctx = new BitXorExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitXorExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(306);
						if (!(precpred(_ctx, 12))) throw new FailedPredicateException(this, "precpred(_ctx, 12)");
						setState(307);
						((BitXorExprContext)_localctx).operator = match(T__16);
						setState(308);
						((BitXorExprContext)_localctx).right = expression(13);
						}
						break;
					case 9:
						{
						_localctx = new BitOrExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitOrExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(309);
						if (!(precpred(_ctx, 11))) throw new FailedPredicateException(this, "precpred(_ctx, 11)");
						setState(310);
						((BitOrExprContext)_localctx).operator = match(T__17);
						setState(311);
						((BitOrExprContext)_localctx).right = expression(12);
						}
						break;
					case 10:
						{
						_localctx = new DotExprContext(new ExpressionContext(_parentctx, _parentState));
						((DotExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(312);
						if (!(precpred(_ctx, 25))) throw new FailedPredicateException(this, "precpred(_ctx, 25)");
						setState(313);
						((DotExprContext)_localctx).operator = match(T__9);
						setState(314);
						((DotExprContext)_localctx).right = match(NAME);
						}
						break;
					case 11:
						{
						_localctx = new CallExprContext(new ExpressionContext(_parentctx, _parentState));
						((CallExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(315);
						if (!(precpred(_ctx, 24))) throw new FailedPredicateException(this, "precpred(_ctx, 24)");
						setState(316);
						((CallExprContext)_localctx).params = exprOfTuple();
						}
						break;
					case 12:
						{
						_localctx = new ArrayLookupExprContext(new ExpressionContext(_parentctx, _parentState));
						((ArrayLookupExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(317);
						if (!(precpred(_ctx, 22))) throw new FailedPredicateException(this, "precpred(_ctx, 22)");
						setState(318);
						match(T__7);
						setState(319);
						((ArrayLookupExprContext)_localctx).right = expression(0);
						setState(320);
						match(T__8);
						}
						break;
					case 13:
						{
						_localctx = new ApplyExprContext(new ExpressionContext(_parentctx, _parentState));
						((ApplyExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(322);
						if (!(precpred(_ctx, 21))) throw new FailedPredicateException(this, "precpred(_ctx, 21)");
						setState(323);
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
						setState(324);
						((ApplyExprContext)_localctx).right = expression(0);
						setState(325);
						((ApplyExprContext)_localctx).params = exprOfTuple();
						}
						break;
					case 14:
						{
						_localctx = new IfExprContext(new ExpressionContext(_parentctx, _parentState));
						((IfExprContext)_localctx).condition = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(327);
						if (!(precpred(_ctx, 10))) throw new FailedPredicateException(this, "precpred(_ctx, 10)");
						{
						setState(328);
						match(T__18);
						setState(329);
						((IfExprContext)_localctx).left = expression(0);
						setState(330);
						match(T__6);
						setState(331);
						((IfExprContext)_localctx).right = expression(0);
						}
						}
						break;
					}
					} 
				}
				setState(337);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,32,_ctx);
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

	public static class LetContext extends ParserRuleContext {
		public TerminalNode LET() { return getToken(YaflParser.LET, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public GenericParamsDeclareContext genericParamsDeclare() {
			return getRuleContext(GenericParamsDeclareContext.class,0);
		}
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public LetContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_let; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterLet(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitLet(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitLet(this);
			else return visitor.visitChildren(this);
		}
	}

	public final LetContext let() throws RecognitionException {
		LetContext _localctx = new LetContext(_ctx, getState());
		enterRule(_localctx, 30, RULE_let);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(338);
			match(LET);
			setState(339);
			match(NAME);
			setState(341);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(340);
				genericParamsDeclare();
				}
			}

			setState(345);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__6) {
				{
				setState(343);
				match(T__6);
				setState(344);
				type();
				}
			}

			setState(349);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__0) {
				{
				setState(347);
				match(T__0);
				setState(348);
				expression(0);
				}
			}

			setState(352);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,36,_ctx) ) {
			case 1:
				{
				setState(351);
				match(T__21);
				}
				break;
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

	public static class FunctionContext extends ParserRuleContext {
		public TypeRefContext extensionType;
		public TerminalNode FUN() { return getToken(YaflParser.FUN, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public AttributesContext attributes() {
			return getRuleContext(AttributesContext.class,0);
		}
		public GenericParamsDeclareContext genericParamsDeclare() {
			return getRuleContext(GenericParamsDeclareContext.class,0);
		}
		public ValueParamsDeclareContext valueParamsDeclare() {
			return getRuleContext(ValueParamsDeclareContext.class,0);
		}
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public TerminalNode LAMBDA() { return getToken(YaflParser.LAMBDA, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TypeRefContext typeRef() {
			return getRuleContext(TypeRefContext.class,0);
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
		enterRule(_localctx, 32, RULE_function);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(354);
			match(FUN);
			setState(356);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__7) {
				{
				setState(355);
				attributes();
				}
			}

			setState(361);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,38,_ctx) ) {
			case 1:
				{
				setState(358);
				((FunctionContext)_localctx).extensionType = typeRef();
				setState(359);
				match(T__9);
				}
				break;
			}
			setState(363);
			match(NAME);
			setState(365);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(364);
				genericParamsDeclare();
				}
			}

			setState(368);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,40,_ctx) ) {
			case 1:
				{
				setState(367);
				valueParamsDeclare();
				}
				break;
			}
			setState(372);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__6) {
				{
				setState(370);
				match(T__6);
				setState(371);
				type();
				}
			}

			setState(376);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==LAMBDA) {
				{
				setState(374);
				match(LAMBDA);
				setState(375);
				expression(0);
				}
			}

			setState(379);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,43,_ctx) ) {
			case 1:
				{
				setState(378);
				match(T__21);
				}
				break;
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

	public static class InterfaceContext extends ParserRuleContext {
		public TerminalNode INTERFACE() { return getToken(YaflParser.INTERFACE, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public GenericParamsDeclareContext genericParamsDeclare() {
			return getRuleContext(GenericParamsDeclareContext.class,0);
		}
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
		enterRule(_localctx, 34, RULE_interface);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(381);
			match(INTERFACE);
			setState(382);
			match(NAME);
			setState(384);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(383);
				genericParamsDeclare();
				}
			}

			setState(387);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__6) {
				{
				setState(386);
				extends_();
				}
			}

			setState(397);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__19) {
				{
				setState(389);
				match(T__19);
				setState(393);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN) {
					{
					{
					setState(390);
					function();
					}
					}
					setState(395);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(396);
				match(T__20);
				}
			}

			setState(400);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__21) {
				{
				setState(399);
				match(T__21);
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
		public GenericParamsDeclareContext genericParamsDeclare() {
			return getRuleContext(GenericParamsDeclareContext.class,0);
		}
		public ValueParamsDeclareContext valueParamsDeclare() {
			return getRuleContext(ValueParamsDeclareContext.class,0);
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
		enterRule(_localctx, 36, RULE_class);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(402);
			match(CLASS);
			setState(403);
			match(NAME);
			setState(405);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(404);
				genericParamsDeclare();
				}
			}

			setState(408);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__1) {
				{
				setState(407);
				valueParamsDeclare();
				}
			}

			setState(411);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__6) {
				{
				setState(410);
				extends_();
				}
			}

			setState(421);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__19) {
				{
				setState(413);
				match(T__19);
				setState(417);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN) {
					{
					{
					setState(414);
					classMember();
					}
					}
					setState(419);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(420);
				match(T__20);
				}
			}

			setState(424);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__21) {
				{
				setState(423);
				match(T__21);
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
		public List<GenericParamsDeclareContext> genericParamsDeclare() {
			return getRuleContexts(GenericParamsDeclareContext.class);
		}
		public GenericParamsDeclareContext genericParamsDeclare(int i) {
			return getRuleContext(GenericParamsDeclareContext.class,i);
		}
		public List<ValueParamsDeclareContext> valueParamsDeclare() {
			return getRuleContexts(ValueParamsDeclareContext.class);
		}
		public ValueParamsDeclareContext valueParamsDeclare(int i) {
			return getRuleContext(ValueParamsDeclareContext.class,i);
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
		enterRule(_localctx, 38, RULE_enum);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(426);
			match(ENUM);
			setState(427);
			match(NAME);
			setState(443);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__19) {
				{
				setState(428);
				match(T__19);
				setState(439);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==FUN || _la==NAME) {
					{
					setState(437);
					_errHandler.sync(this);
					switch (_input.LA(1)) {
					case NAME:
						{
						{
						setState(429);
						match(NAME);
						setState(431);
						_errHandler.sync(this);
						_la = _input.LA(1);
						if (_la==T__4) {
							{
							setState(430);
							genericParamsDeclare();
							}
						}

						setState(434);
						_errHandler.sync(this);
						_la = _input.LA(1);
						if (_la==T__1) {
							{
							setState(433);
							valueParamsDeclare();
							}
						}

						}
						}
						break;
					case FUN:
						{
						setState(436);
						function();
						}
						break;
					default:
						throw new NoViableAltException(this);
					}
					}
					setState(441);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(442);
				match(T__20);
				}
			}

			setState(446);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__21) {
				{
				setState(445);
				match(T__21);
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
		public GenericParamsDeclareContext genericParamsDeclare() {
			return getRuleContext(GenericParamsDeclareContext.class,0);
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
		enterRule(_localctx, 40, RULE_alias);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(448);
			match(ALIAS);
			setState(449);
			match(NAME);
			setState(451);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(450);
				genericParamsDeclare();
				}
			}

			setState(453);
			match(T__6);
			setState(454);
			type();
			setState(456);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__21) {
				{
				setState(455);
				match(T__21);
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
		enterRule(_localctx, 42, RULE_extends);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(458);
			match(T__6);
			setState(459);
			typeRef();
			setState(464);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==T__2) {
				{
				{
				setState(460);
				match(T__2);
				setState(461);
				typeRef();
				}
				}
				setState(466);
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
		enterRule(_localctx, 44, RULE_module);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(467);
			match(MODULE);
			setState(468);
			typeRef();
			setState(470);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__21) {
				{
				setState(469);
				match(T__21);
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
		enterRule(_localctx, 46, RULE_import_);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(472);
			match(IMPORT);
			setState(473);
			typeRef();
			setState(475);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__21) {
				{
				setState(474);
				match(T__21);
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
		public LetContext let() {
			return getRuleContext(LetContext.class,0);
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
		enterRule(_localctx, 48, RULE_declaration);
		try {
			setState(483);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case LET:
				enterOuterAlt(_localctx, 1);
				{
				setState(477);
				let();
				}
				break;
			case FUN:
				enterOuterAlt(_localctx, 2);
				{
				setState(478);
				function();
				}
				break;
			case INTERFACE:
				enterOuterAlt(_localctx, 3);
				{
				setState(479);
				interface_();
				}
				break;
			case CLASS:
				enterOuterAlt(_localctx, 4);
				{
				setState(480);
				class_();
				}
				break;
			case ENUM:
				enterOuterAlt(_localctx, 5);
				{
				setState(481);
				enum_();
				}
				break;
			case ALIAS:
				enterOuterAlt(_localctx, 6);
				{
				setState(482);
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
		enterRule(_localctx, 50, RULE_classMember);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(485);
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
		enterRule(_localctx, 52, RULE_root);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(487);
			module();
			setState(491);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==IMPORT) {
				{
				{
				setState(488);
				import_();
				}
				}
				setState(493);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(497);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << ALIAS) | (1L << FUN) | (1L << LET) | (1L << INTERFACE) | (1L << CLASS) | (1L << ENUM))) != 0)) {
				{
				{
				setState(494);
				declaration();
				}
				}
				setState(499);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(500);
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
			return precpred(_ctx, 19);
		case 1:
			return precpred(_ctx, 18);
		case 2:
			return precpred(_ctx, 17);
		case 3:
			return precpred(_ctx, 16);
		case 4:
			return precpred(_ctx, 15);
		case 5:
			return precpred(_ctx, 14);
		case 6:
			return precpred(_ctx, 13);
		case 7:
			return precpred(_ctx, 12);
		case 8:
			return precpred(_ctx, 11);
		case 9:
			return precpred(_ctx, 25);
		case 10:
			return precpred(_ctx, 24);
		case 11:
			return precpred(_ctx, 22);
		case 12:
			return precpred(_ctx, 21);
		case 13:
			return precpred(_ctx, 10);
		}
		return true;
	}

	public static final String _serializedATN =
		"\u0004\u00017\u01f7\u0002\u0000\u0007\u0000\u0002\u0001\u0007\u0001\u0002"+
		"\u0002\u0007\u0002\u0002\u0003\u0007\u0003\u0002\u0004\u0007\u0004\u0002"+
		"\u0005\u0007\u0005\u0002\u0006\u0007\u0006\u0002\u0007\u0007\u0007\u0002"+
		"\b\u0007\b\u0002\t\u0007\t\u0002\n\u0007\n\u0002\u000b\u0007\u000b\u0002"+
		"\f\u0007\f\u0002\r\u0007\r\u0002\u000e\u0007\u000e\u0002\u000f\u0007\u000f"+
		"\u0002\u0010\u0007\u0010\u0002\u0011\u0007\u0011\u0002\u0012\u0007\u0012"+
		"\u0002\u0013\u0007\u0013\u0002\u0014\u0007\u0014\u0002\u0015\u0007\u0015"+
		"\u0002\u0016\u0007\u0016\u0002\u0017\u0007\u0017\u0002\u0018\u0007\u0018"+
		"\u0002\u0019\u0007\u0019\u0002\u001a\u0007\u001a\u0001\u0000\u0001\u0000"+
		"\u0005\u00009\b\u0000\n\u0000\f\u0000<\t\u0000\u0001\u0000\u0001\u0000"+
		"\u0001\u0001\u0001\u0001\u0003\u0001B\b\u0001\u0001\u0001\u0001\u0001"+
		"\u0001\u0002\u0001\u0002\u0001\u0002\u0001\u0002\u0005\u0002J\b\u0002"+
		"\n\u0002\f\u0002M\t\u0002\u0001\u0002\u0003\u0002P\b\u0002\u0001\u0002"+
		"\u0001\u0002\u0001\u0003\u0001\u0003\u0001\u0003\u0001\u0003\u0005\u0003"+
		"X\b\u0003\n\u0003\f\u0003[\t\u0003\u0001\u0003\u0003\u0003^\b\u0003\u0001"+
		"\u0003\u0001\u0003\u0001\u0004\u0001\u0004\u0001\u0004\u0005\u0004e\b"+
		"\u0004\n\u0004\f\u0004h\t\u0004\u0001\u0004\u0003\u0004k\b\u0004\u0001"+
		"\u0004\u0001\u0004\u0001\u0005\u0001\u0005\u0003\u0005q\b\u0005\u0001"+
		"\u0006\u0001\u0006\u0001\u0006\u0001\u0007\u0001\u0007\u0003\u0007x\b"+
		"\u0007\u0001\u0007\u0001\u0007\u0001\b\u0001\b\u0001\b\u0001\b\u0005\b"+
		"\u0080\b\b\n\b\f\b\u0083\t\b\u0001\b\u0003\b\u0086\b\b\u0001\b\u0001\b"+
		"\u0001\t\u0001\t\u0001\t\u0001\t\u0001\n\u0001\n\u0001\n\u0001\n\u0003"+
		"\n\u0092\b\n\u0001\u000b\u0001\u000b\u0005\u000b\u0096\b\u000b\n\u000b"+
		"\f\u000b\u0099\t\u000b\u0001\u000b\u0001\u000b\u0001\f\u0001\f\u0001\f"+
		"\u0001\f\u0001\f\u0001\f\u0003\f\u00a3\b\f\u0001\f\u0001\f\u0003\f\u00a7"+
		"\b\f\u0001\f\u0001\f\u0003\f\u00ab\b\f\u0003\f\u00ad\b\f\u0001\r\u0001"+
		"\r\u0001\r\u0001\r\u0005\r\u00b3\b\r\n\r\f\r\u00b6\t\r\u0001\r\u0003\r"+
		"\u00b9\b\r\u0001\r\u0001\r\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0005\u000e"+
		"\u00c6\b\u000e\n\u000e\f\u000e\u00c9\t\u000e\u0001\u000e\u0001\u000e\u0001"+
		"\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001"+
		"\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001"+
		"\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001"+
		"\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0005"+
		"\u000e\u00e5\b\u000e\n\u000e\f\u000e\u00e8\t\u000e\u0001\u000e\u0001\u000e"+
		"\u0005\u000e\u00ec\b\u000e\n\u000e\f\u000e\u00ef\t\u000e\u0001\u000e\u0003"+
		"\u000e\u00f2\b\u000e\u0001\u000e\u0001\u000e\u0003\u000e\u00f6\b\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0003\u000e\u00fc\b\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0003\u000e"+
		"\u0103\b\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0005\u000e\u010c\b\u000e\n\u000e\f\u000e\u010f"+
		"\t\u000e\u0001\u000e\u0003\u000e\u0112\b\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0003\u000e\u011a\b\u000e"+
		"\u0003\u000e\u011c\b\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e\u0001\u000e"+
		"\u0001\u000e\u0001\u000e\u0005\u000e\u014e\b\u000e\n\u000e\f\u000e\u0151"+
		"\t\u000e\u0001\u000f\u0001\u000f\u0001\u000f\u0003\u000f\u0156\b\u000f"+
		"\u0001\u000f\u0001\u000f\u0003\u000f\u015a\b\u000f\u0001\u000f\u0001\u000f"+
		"\u0003\u000f\u015e\b\u000f\u0001\u000f\u0003\u000f\u0161\b\u000f\u0001"+
		"\u0010\u0001\u0010\u0003\u0010\u0165\b\u0010\u0001\u0010\u0001\u0010\u0001"+
		"\u0010\u0003\u0010\u016a\b\u0010\u0001\u0010\u0001\u0010\u0003\u0010\u016e"+
		"\b\u0010\u0001\u0010\u0003\u0010\u0171\b\u0010\u0001\u0010\u0001\u0010"+
		"\u0003\u0010\u0175\b\u0010\u0001\u0010\u0001\u0010\u0003\u0010\u0179\b"+
		"\u0010\u0001\u0010\u0003\u0010\u017c\b\u0010\u0001\u0011\u0001\u0011\u0001"+
		"\u0011\u0003\u0011\u0181\b\u0011\u0001\u0011\u0003\u0011\u0184\b\u0011"+
		"\u0001\u0011\u0001\u0011\u0005\u0011\u0188\b\u0011\n\u0011\f\u0011\u018b"+
		"\t\u0011\u0001\u0011\u0003\u0011\u018e\b\u0011\u0001\u0011\u0003\u0011"+
		"\u0191\b\u0011\u0001\u0012\u0001\u0012\u0001\u0012\u0003\u0012\u0196\b"+
		"\u0012\u0001\u0012\u0003\u0012\u0199\b\u0012\u0001\u0012\u0003\u0012\u019c"+
		"\b\u0012\u0001\u0012\u0001\u0012\u0005\u0012\u01a0\b\u0012\n\u0012\f\u0012"+
		"\u01a3\t\u0012\u0001\u0012\u0003\u0012\u01a6\b\u0012\u0001\u0012\u0003"+
		"\u0012\u01a9\b\u0012\u0001\u0013\u0001\u0013\u0001\u0013\u0001\u0013\u0001"+
		"\u0013\u0003\u0013\u01b0\b\u0013\u0001\u0013\u0003\u0013\u01b3\b\u0013"+
		"\u0001\u0013\u0005\u0013\u01b6\b\u0013\n\u0013\f\u0013\u01b9\t\u0013\u0001"+
		"\u0013\u0003\u0013\u01bc\b\u0013\u0001\u0013\u0003\u0013\u01bf\b\u0013"+
		"\u0001\u0014\u0001\u0014\u0001\u0014\u0003\u0014\u01c4\b\u0014\u0001\u0014"+
		"\u0001\u0014\u0001\u0014\u0003\u0014\u01c9\b\u0014\u0001\u0015\u0001\u0015"+
		"\u0001\u0015\u0001\u0015\u0005\u0015\u01cf\b\u0015\n\u0015\f\u0015\u01d2"+
		"\t\u0015\u0001\u0016\u0001\u0016\u0001\u0016\u0003\u0016\u01d7\b\u0016"+
		"\u0001\u0017\u0001\u0017\u0001\u0017\u0003\u0017\u01dc\b\u0017\u0001\u0018"+
		"\u0001\u0018\u0001\u0018\u0001\u0018\u0001\u0018\u0001\u0018\u0003\u0018"+
		"\u01e4\b\u0018\u0001\u0019\u0001\u0019\u0001\u001a\u0001\u001a\u0005\u001a"+
		"\u01ea\b\u001a\n\u001a\f\u001a\u01ed\t\u001a\u0001\u001a\u0005\u001a\u01f0"+
		"\b\u001a\n\u001a\f\u001a\u01f3\t\u001a\u0001\u001a\u0001\u001a\u0001\u001a"+
		"\u0000\u0001\u001c\u001b\u0000\u0002\u0004\u0006\b\n\f\u000e\u0010\u0012"+
		"\u0014\u0016\u0018\u001a\u001c\u001e \"$&(*,.024\u0000\u0006\u0001\u0000"+
		"\u000b\f\u0001\u0000\r\u000f\u0001\u000001\u0002\u0000\u0005\u0006,-\u0001"+
		"\u0000./\u0001\u0000)*\u023e\u0000:\u0001\u0000\u0000\u0000\u0002A\u0001"+
		"\u0000\u0000\u0000\u0004E\u0001\u0000\u0000\u0000\u0006S\u0001\u0000\u0000"+
		"\u0000\ba\u0001\u0000\u0000\u0000\nn\u0001\u0000\u0000\u0000\fr\u0001"+
		"\u0000\u0000\u0000\u000ew\u0001\u0000\u0000\u0000\u0010{\u0001\u0000\u0000"+
		"\u0000\u0012\u0089\u0001\u0000\u0000\u0000\u0014\u0091\u0001\u0000\u0000"+
		"\u0000\u0016\u0093\u0001\u0000\u0000\u0000\u0018\u00ac\u0001\u0000\u0000"+
		"\u0000\u001a\u00ae\u0001\u0000\u0000\u0000\u001c\u011b\u0001\u0000\u0000"+
		"\u0000\u001e\u0152\u0001\u0000\u0000\u0000 \u0162\u0001\u0000\u0000\u0000"+
		"\"\u017d\u0001\u0000\u0000\u0000$\u0192\u0001\u0000\u0000\u0000&\u01aa"+
		"\u0001\u0000\u0000\u0000(\u01c0\u0001\u0000\u0000\u0000*\u01ca\u0001\u0000"+
		"\u0000\u0000,\u01d3\u0001\u0000\u0000\u0000.\u01d8\u0001\u0000\u0000\u0000"+
		"0\u01e3\u0001\u0000\u0000\u00002\u01e5\u0001\u0000\u0000\u00004\u01e7"+
		"\u0001\u0000\u0000\u000067\u00053\u0000\u000079\u0005+\u0000\u000086\u0001"+
		"\u0000\u0000\u00009<\u0001\u0000\u0000\u0000:8\u0001\u0000\u0000\u0000"+
		":;\u0001\u0000\u0000\u0000;=\u0001\u0000\u0000\u0000<:\u0001\u0000\u0000"+
		"\u0000=>\u00053\u0000\u0000>\u0001\u0001\u0000\u0000\u0000?@\u00053\u0000"+
		"\u0000@B\u0005\u0001\u0000\u0000A?\u0001\u0000\u0000\u0000AB\u0001\u0000"+
		"\u0000\u0000BC\u0001\u0000\u0000\u0000CD\u0003\u001c\u000e\u0000D\u0003"+
		"\u0001\u0000\u0000\u0000EK\u0005\u0002\u0000\u0000FG\u0003\u0002\u0001"+
		"\u0000GH\u0005\u0003\u0000\u0000HJ\u0001\u0000\u0000\u0000IF\u0001\u0000"+
		"\u0000\u0000JM\u0001\u0000\u0000\u0000KI\u0001\u0000\u0000\u0000KL\u0001"+
		"\u0000\u0000\u0000LO\u0001\u0000\u0000\u0000MK\u0001\u0000\u0000\u0000"+
		"NP\u0003\u0002\u0001\u0000ON\u0001\u0000\u0000\u0000OP\u0001\u0000\u0000"+
		"\u0000PQ\u0001\u0000\u0000\u0000QR\u0005\u0004\u0000\u0000R\u0005\u0001"+
		"\u0000\u0000\u0000SY\u0005\u0005\u0000\u0000TU\u0003\u0014\n\u0000UV\u0005"+
		"\u0003\u0000\u0000VX\u0001\u0000\u0000\u0000WT\u0001\u0000\u0000\u0000"+
		"X[\u0001\u0000\u0000\u0000YW\u0001\u0000\u0000\u0000YZ\u0001\u0000\u0000"+
		"\u0000Z]\u0001\u0000\u0000\u0000[Y\u0001\u0000\u0000\u0000\\^\u0003\u0014"+
		"\n\u0000]\\\u0001\u0000\u0000\u0000]^\u0001\u0000\u0000\u0000^_\u0001"+
		"\u0000\u0000\u0000_`\u0005\u0006\u0000\u0000`\u0007\u0001\u0000\u0000"+
		"\u0000af\u0005\u0005\u0000\u0000bc\u00053\u0000\u0000ce\u0005\u0003\u0000"+
		"\u0000db\u0001\u0000\u0000\u0000eh\u0001\u0000\u0000\u0000fd\u0001\u0000"+
		"\u0000\u0000fg\u0001\u0000\u0000\u0000gj\u0001\u0000\u0000\u0000hf\u0001"+
		"\u0000\u0000\u0000ik\u00053\u0000\u0000ji\u0001\u0000\u0000\u0000jk\u0001"+
		"\u0000\u0000\u0000kl\u0001\u0000\u0000\u0000lm\u0005\u0006\u0000\u0000"+
		"m\t\u0001\u0000\u0000\u0000np\u0003\u0000\u0000\u0000oq\u0003\u0006\u0003"+
		"\u0000po\u0001\u0000\u0000\u0000pq\u0001\u0000\u0000\u0000q\u000b\u0001"+
		"\u0000\u0000\u0000rs\u0005\u0018\u0000\u0000st\u00053\u0000\u0000t\r\u0001"+
		"\u0000\u0000\u0000uv\u00053\u0000\u0000vx\u0005\u0007\u0000\u0000wu\u0001"+
		"\u0000\u0000\u0000wx\u0001\u0000\u0000\u0000xy\u0001\u0000\u0000\u0000"+
		"yz\u0003\u0014\n\u0000z\u000f\u0001\u0000\u0000\u0000{\u0081\u0005\u0002"+
		"\u0000\u0000|}\u0003\u000e\u0007\u0000}~\u0005\u0003\u0000\u0000~\u0080"+
		"\u0001\u0000\u0000\u0000\u007f|\u0001\u0000\u0000\u0000\u0080\u0083\u0001"+
		"\u0000\u0000\u0000\u0081\u007f\u0001\u0000\u0000\u0000\u0081\u0082\u0001"+
		"\u0000\u0000\u0000\u0082\u0085\u0001\u0000\u0000\u0000\u0083\u0081\u0001"+
		"\u0000\u0000\u0000\u0084\u0086\u0003\u000e\u0007\u0000\u0085\u0084\u0001"+
		"\u0000\u0000\u0000\u0085\u0086\u0001\u0000\u0000\u0000\u0086\u0087\u0001"+
		"\u0000\u0000\u0000\u0087\u0088\u0005\u0004\u0000\u0000\u0088\u0011\u0001"+
		"\u0000\u0000\u0000\u0089\u008a\u0003\u0010\b\u0000\u008a\u008b\u0005\u0007"+
		"\u0000\u0000\u008b\u008c\u0003\u0014\n\u0000\u008c\u0013\u0001\u0000\u0000"+
		"\u0000\u008d\u0092\u0003\n\u0005\u0000\u008e\u0092\u0003\f\u0006\u0000"+
		"\u008f\u0092\u0003\u0010\b\u0000\u0090\u0092\u0003\u0012\t\u0000\u0091"+
		"\u008d\u0001\u0000\u0000\u0000\u0091\u008e\u0001\u0000\u0000\u0000\u0091"+
		"\u008f\u0001\u0000\u0000\u0000\u0091\u0090\u0001\u0000\u0000\u0000\u0092"+
		"\u0015\u0001\u0000\u0000\u0000\u0093\u0097\u0005\b\u0000\u0000\u0094\u0096"+
		"\u00053\u0000\u0000\u0095\u0094\u0001\u0000\u0000\u0000\u0096\u0099\u0001"+
		"\u0000\u0000\u0000\u0097\u0095\u0001\u0000\u0000\u0000\u0097\u0098\u0001"+
		"\u0000\u0000\u0000\u0098\u009a\u0001\u0000\u0000\u0000\u0099\u0097\u0001"+
		"\u0000\u0000\u0000\u009a\u009b\u0005\t\u0000\u0000\u009b\u0017\u0001\u0000"+
		"\u0000\u0000\u009c\u00ad\u0003\u001a\r\u0000\u009d\u00a6\u00053\u0000"+
		"\u0000\u009e\u00a2\u0005\b\u0000\u0000\u009f\u00a0\u0003\u001c\u000e\u0000"+
		"\u00a0\u00a1\u0005,\u0000\u0000\u00a1\u00a3\u0001\u0000\u0000\u0000\u00a2"+
		"\u009f\u0001\u0000\u0000\u0000\u00a2\u00a3\u0001\u0000\u0000\u0000\u00a3"+
		"\u00a4\u0001\u0000\u0000\u0000\u00a4\u00a5\u00054\u0000\u0000\u00a5\u00a7"+
		"\u0005\t\u0000\u0000\u00a6\u009e\u0001\u0000\u0000\u0000\u00a6\u00a7\u0001"+
		"\u0000\u0000\u0000\u00a7\u00aa\u0001\u0000\u0000\u0000\u00a8\u00a9\u0005"+
		"\u0007\u0000\u0000\u00a9\u00ab\u0003\u0014\n\u0000\u00aa\u00a8\u0001\u0000"+
		"\u0000\u0000\u00aa\u00ab\u0001\u0000\u0000\u0000\u00ab\u00ad\u0001\u0000"+
		"\u0000\u0000\u00ac\u009c\u0001\u0000\u0000\u0000\u00ac\u009d\u0001\u0000"+
		"\u0000\u0000\u00ad\u0019\u0001\u0000\u0000\u0000\u00ae\u00b4\u0005\u0002"+
		"\u0000\u0000\u00af\u00b0\u0003\u0018\f\u0000\u00b0\u00b1\u0005\u0003\u0000"+
		"\u0000\u00b1\u00b3\u0001\u0000\u0000\u0000\u00b2\u00af\u0001\u0000\u0000"+
		"\u0000\u00b3\u00b6\u0001\u0000\u0000\u0000\u00b4\u00b2\u0001\u0000\u0000"+
		"\u0000\u00b4\u00b5\u0001\u0000\u0000\u0000\u00b5\u00b8\u0001\u0000\u0000"+
		"\u0000\u00b6\u00b4\u0001\u0000\u0000\u0000\u00b7\u00b9\u0003\u0018\f\u0000"+
		"\u00b8\u00b7\u0001\u0000\u0000\u0000\u00b8\u00b9\u0001\u0000\u0000\u0000"+
		"\u00b9\u00ba\u0001\u0000\u0000\u0000\u00ba\u00bb\u0005\u0004\u0000\u0000"+
		"\u00bb\u001b\u0001\u0000\u0000\u0000\u00bc\u00bd\u0006\u000e\uffff\uffff"+
		"\u0000\u00bd\u00be\u0005\u0017\u0000\u0000\u00be\u00bf\u0005\u0005\u0000"+
		"\u0000\u00bf\u00c0\u0003\u0014\n\u0000\u00c0\u00c1\u0005\u0006\u0000\u0000"+
		"\u00c1\u00c2\u0005\u0002\u0000\u0000\u00c2\u00c7\u00055\u0000\u0000\u00c3"+
		"\u00c4\u0005\u0003\u0000\u0000\u00c4\u00c6\u0003\u001c\u000e\u0000\u00c5"+
		"\u00c3\u0001\u0000\u0000\u0000\u00c6\u00c9\u0001\u0000\u0000\u0000\u00c7"+
		"\u00c5\u0001\u0000\u0000\u0000\u00c7\u00c8\u0001\u0000\u0000\u0000\u00c8"+
		"\u00ca\u0001\u0000\u0000\u0000\u00c9\u00c7\u0001\u0000\u0000\u0000\u00ca"+
		"\u00cb\u0005\u0004\u0000\u0000\u00cb\u011c\u0001\u0000\u0000\u0000\u00cc"+
		"\u00cd\u0005\u0019\u0000\u0000\u00cd\u00ce\u0005\u0002\u0000\u0000\u00ce"+
		"\u00cf\u0003\u001c\u000e\u0000\u00cf\u00d0\u0005\u0003\u0000\u0000\u00d0"+
		"\u00d1\u0003\u001c\u000e\u0000\u00d1\u00d2\u0005\u0003\u0000\u0000\u00d2"+
		"\u00d3\u00055\u0000\u0000\u00d3\u00d4\u0005\u0004\u0000\u0000\u00d4\u011c"+
		"\u0001\u0000\u0000\u0000\u00d5\u00d6\u0005\u001a\u0000\u0000\u00d6\u00d7"+
		"\u0005\u0002\u0000\u0000\u00d7\u00d8\u0003\u001c\u000e\u0000\u00d8\u00d9"+
		"\u0005\u0004\u0000\u0000\u00d9\u011c\u0001\u0000\u0000\u0000\u00da\u00db"+
		"\u0005\u001b\u0000\u0000\u00db\u011c\u0003\u0004\u0002\u0000\u00dc\u00dd"+
		"\u0007\u0000\u0000\u0000\u00dd\u011c\u0003\u001c\u000e\u0014\u00de\u011c"+
		"\u0003\u0004\u0002\u0000\u00df\u00e0\u0005%\u0000\u0000\u00e0\u00e1\u0005"+
		"\u0007\u0000\u0000\u00e1\u00e6\u0003\n\u0005\u0000\u00e2\u00e3\u0005\u0012"+
		"\u0000\u0000\u00e3\u00e5\u0003\n\u0005\u0000\u00e4\u00e2\u0001\u0000\u0000"+
		"\u0000\u00e5\u00e8\u0001\u0000\u0000\u0000\u00e6\u00e4\u0001\u0000\u0000"+
		"\u0000\u00e6\u00e7\u0001\u0000\u0000\u0000\u00e7\u00f1\u0001\u0000\u0000"+
		"\u0000\u00e8\u00e6\u0001\u0000\u0000\u0000\u00e9\u00ed\u0005\u0014\u0000"+
		"\u0000\u00ea\u00ec\u0003 \u0010\u0000\u00eb\u00ea\u0001\u0000\u0000\u0000"+
		"\u00ec\u00ef\u0001\u0000\u0000\u0000\u00ed\u00eb\u0001\u0000\u0000\u0000"+
		"\u00ed\u00ee\u0001\u0000\u0000\u0000\u00ee\u00f0\u0001\u0000\u0000\u0000"+
		"\u00ef\u00ed\u0001\u0000\u0000\u0000\u00f0\u00f2\u0005\u0015\u0000\u0000"+
		"\u00f1\u00e9\u0001\u0000\u0000\u0000\u00f1\u00f2\u0001\u0000\u0000\u0000"+
		"\u00f2\u011c\u0001\u0000\u0000\u0000\u00f3\u00f5\u0003\u001e\u000f\u0000"+
		"\u00f4\u00f6\u0005\u0016\u0000\u0000\u00f5\u00f4\u0001\u0000\u0000\u0000"+
		"\u00f5\u00f6\u0001\u0000\u0000\u0000\u00f6\u00f7\u0001\u0000\u0000\u0000"+
		"\u00f7\u00f8\u0003\u001c\u000e\u0007\u00f8\u011c\u0001\u0000\u0000\u0000"+
		"\u00f9\u00fb\u0003 \u0010\u0000\u00fa\u00fc\u0005\u0016\u0000\u0000\u00fb"+
		"\u00fa\u0001\u0000\u0000\u0000\u00fb\u00fc\u0001\u0000\u0000\u0000\u00fc"+
		"\u00fd\u0001\u0000\u0000\u0000\u00fd\u00fe\u0003\u001c\u000e\u0006\u00fe"+
		"\u011c\u0001\u0000\u0000\u0000\u00ff\u0102\u0003\u001a\r\u0000\u0100\u0101"+
		"\u0005\u0007\u0000\u0000\u0101\u0103\u0003\u0014\n\u0000\u0102\u0100\u0001"+
		"\u0000\u0000\u0000\u0102\u0103\u0001\u0000\u0000\u0000\u0103\u0104\u0001"+
		"\u0000\u0000\u0000\u0104\u0105\u0005(\u0000\u0000\u0105\u0106\u0003\u001c"+
		"\u000e\u0005\u0106\u011c\u0001\u0000\u0000\u0000\u0107\u0108\u0005\b\u0000"+
		"\u0000\u0108\u010d\u0003\u001c\u000e\u0000\u0109\u010a\u0005\u0003\u0000"+
		"\u0000\u010a\u010c\u0003\u001c\u000e\u0000\u010b\u0109\u0001\u0000\u0000"+
		"\u0000\u010c\u010f\u0001\u0000\u0000\u0000\u010d\u010b\u0001\u0000\u0000"+
		"\u0000\u010d\u010e\u0001\u0000\u0000\u0000\u010e\u0111\u0001\u0000\u0000"+
		"\u0000\u010f\u010d\u0001\u0000\u0000\u0000\u0110\u0112\u0005\u0003\u0000"+
		"\u0000\u0111\u0110\u0001\u0000\u0000\u0000\u0111\u0112\u0001\u0000\u0000"+
		"\u0000\u0112\u0113\u0001\u0000\u0000\u0000\u0113\u0114\u0005\t\u0000\u0000"+
		"\u0114\u011c\u0001\u0000\u0000\u0000\u0115\u011c\u00055\u0000\u0000\u0116"+
		"\u011c\u00054\u0000\u0000\u0117\u0119\u0003\u0000\u0000\u0000\u0118\u011a"+
		"\u0003\u0006\u0003\u0000\u0119\u0118\u0001\u0000\u0000\u0000\u0119\u011a"+
		"\u0001\u0000\u0000\u0000\u011a\u011c\u0001\u0000\u0000\u0000\u011b\u00bc"+
		"\u0001\u0000\u0000\u0000\u011b\u00cc\u0001\u0000\u0000\u0000\u011b\u00d5"+
		"\u0001\u0000\u0000\u0000\u011b\u00da\u0001\u0000\u0000\u0000\u011b\u00dc"+
		"\u0001\u0000\u0000\u0000\u011b\u00de\u0001\u0000\u0000\u0000\u011b\u00df"+
		"\u0001\u0000\u0000\u0000\u011b\u00f3\u0001\u0000\u0000\u0000\u011b\u00f9"+
		"\u0001\u0000\u0000\u0000\u011b\u00ff\u0001\u0000\u0000\u0000\u011b\u0107"+
		"\u0001\u0000\u0000\u0000\u011b\u0115\u0001\u0000\u0000\u0000\u011b\u0116"+
		"\u0001\u0000\u0000\u0000\u011b\u0117\u0001\u0000\u0000\u0000\u011c\u014f"+
		"\u0001\u0000\u0000\u0000\u011d\u011e\n\u0013\u0000\u0000\u011e\u011f\u0005"+
		"2\u0000\u0000\u011f\u014e\u0003\u001c\u000e\u0014\u0120\u0121\n\u0012"+
		"\u0000\u0000\u0121\u0122\u0007\u0001\u0000\u0000\u0122\u014e\u0003\u001c"+
		"\u000e\u0013\u0123\u0124\n\u0011\u0000\u0000\u0124\u0125\u0007\u0000\u0000"+
		"\u0000\u0125\u014e\u0003\u001c\u000e\u0012\u0126\u0127\n\u0010\u0000\u0000"+
		"\u0127\u0128\u0007\u0002\u0000\u0000\u0128\u014e\u0003\u001c\u000e\u0011"+
		"\u0129\u012a\n\u000f\u0000\u0000\u012a\u012b\u0007\u0003\u0000\u0000\u012b"+
		"\u014e\u0003\u001c\u000e\u0010\u012c\u012d\n\u000e\u0000\u0000\u012d\u012e"+
		"\u0007\u0004\u0000\u0000\u012e\u014e\u0003\u001c\u000e\u000f\u012f\u0130"+
		"\n\r\u0000\u0000\u0130\u0131\u0005\u0010\u0000\u0000\u0131\u014e\u0003"+
		"\u001c\u000e\u000e\u0132\u0133\n\f\u0000\u0000\u0133\u0134\u0005\u0011"+
		"\u0000\u0000\u0134\u014e\u0003\u001c\u000e\r\u0135\u0136\n\u000b\u0000"+
		"\u0000\u0136\u0137\u0005\u0012\u0000\u0000\u0137\u014e\u0003\u001c\u000e"+
		"\f\u0138\u0139\n\u0019\u0000\u0000\u0139\u013a\u0005\n\u0000\u0000\u013a"+
		"\u014e\u00053\u0000\u0000\u013b\u013c\n\u0018\u0000\u0000\u013c\u014e"+
		"\u0003\u0004\u0002\u0000\u013d\u013e\n\u0016\u0000\u0000\u013e\u013f\u0005"+
		"\b\u0000\u0000\u013f\u0140\u0003\u001c\u000e\u0000\u0140\u0141\u0005\t"+
		"\u0000\u0000\u0141\u014e\u0001\u0000\u0000\u0000\u0142\u0143\n\u0015\u0000"+
		"\u0000\u0143\u0144\u0007\u0005\u0000\u0000\u0144\u0145\u0003\u001c\u000e"+
		"\u0000\u0145\u0146\u0003\u0004\u0002\u0000\u0146\u014e\u0001\u0000\u0000"+
		"\u0000\u0147\u0148\n\n\u0000\u0000\u0148\u0149\u0005\u0013\u0000\u0000"+
		"\u0149\u014a\u0003\u001c\u000e\u0000\u014a\u014b\u0005\u0007\u0000\u0000"+
		"\u014b\u014c\u0003\u001c\u000e\u0000\u014c\u014e\u0001\u0000\u0000\u0000"+
		"\u014d\u011d\u0001\u0000\u0000\u0000\u014d\u0120\u0001\u0000\u0000\u0000"+
		"\u014d\u0123\u0001\u0000\u0000\u0000\u014d\u0126\u0001\u0000\u0000\u0000"+
		"\u014d\u0129\u0001\u0000\u0000\u0000\u014d\u012c\u0001\u0000\u0000\u0000"+
		"\u014d\u012f\u0001\u0000\u0000\u0000\u014d\u0132\u0001\u0000\u0000\u0000"+
		"\u014d\u0135\u0001\u0000\u0000\u0000\u014d\u0138\u0001\u0000\u0000\u0000"+
		"\u014d\u013b\u0001\u0000\u0000\u0000\u014d\u013d\u0001\u0000\u0000\u0000"+
		"\u014d\u0142\u0001\u0000\u0000\u0000\u014d\u0147\u0001\u0000\u0000\u0000"+
		"\u014e\u0151\u0001\u0000\u0000\u0000\u014f\u014d\u0001\u0000\u0000\u0000"+
		"\u014f\u0150\u0001\u0000\u0000\u0000\u0150\u001d\u0001\u0000\u0000\u0000"+
		"\u0151\u014f\u0001\u0000\u0000\u0000\u0152\u0153\u0005 \u0000\u0000\u0153"+
		"\u0155\u00053\u0000\u0000\u0154\u0156\u0003\b\u0004\u0000\u0155\u0154"+
		"\u0001\u0000\u0000\u0000\u0155\u0156\u0001\u0000\u0000\u0000\u0156\u0159"+
		"\u0001\u0000\u0000\u0000\u0157\u0158\u0005\u0007\u0000\u0000\u0158\u015a"+
		"\u0003\u0014\n\u0000\u0159\u0157\u0001\u0000\u0000\u0000\u0159\u015a\u0001"+
		"\u0000\u0000\u0000\u015a\u015d\u0001\u0000\u0000\u0000\u015b\u015c\u0005"+
		"\u0001\u0000\u0000\u015c\u015e\u0003\u001c\u000e\u0000\u015d\u015b\u0001"+
		"\u0000\u0000\u0000\u015d\u015e\u0001\u0000\u0000\u0000\u015e\u0160\u0001"+
		"\u0000\u0000\u0000\u015f\u0161\u0005\u0016\u0000\u0000\u0160\u015f\u0001"+
		"\u0000\u0000\u0000\u0160\u0161\u0001\u0000\u0000\u0000\u0161\u001f\u0001"+
		"\u0000\u0000\u0000\u0162\u0164\u0005\u001f\u0000\u0000\u0163\u0165\u0003"+
		"\u0016\u000b\u0000\u0164\u0163\u0001\u0000\u0000\u0000\u0164\u0165\u0001"+
		"\u0000\u0000\u0000\u0165\u0169\u0001\u0000\u0000\u0000\u0166\u0167\u0003"+
		"\n\u0005\u0000\u0167\u0168\u0005\n\u0000\u0000\u0168\u016a\u0001\u0000"+
		"\u0000\u0000\u0169\u0166\u0001\u0000\u0000\u0000\u0169\u016a\u0001\u0000"+
		"\u0000\u0000\u016a\u016b\u0001\u0000\u0000\u0000\u016b\u016d\u00053\u0000"+
		"\u0000\u016c\u016e\u0003\b\u0004\u0000\u016d\u016c\u0001\u0000\u0000\u0000"+
		"\u016d\u016e\u0001\u0000\u0000\u0000\u016e\u0170\u0001\u0000\u0000\u0000"+
		"\u016f\u0171\u0003\u001a\r\u0000\u0170\u016f\u0001\u0000\u0000\u0000\u0170"+
		"\u0171\u0001\u0000\u0000\u0000\u0171\u0174\u0001\u0000\u0000\u0000\u0172"+
		"\u0173\u0005\u0007\u0000\u0000\u0173\u0175\u0003\u0014\n\u0000\u0174\u0172"+
		"\u0001\u0000\u0000\u0000\u0174\u0175\u0001\u0000\u0000\u0000\u0175\u0178"+
		"\u0001\u0000\u0000\u0000\u0176\u0177\u0005(\u0000\u0000\u0177\u0179\u0003"+
		"\u001c\u000e\u0000\u0178\u0176\u0001\u0000\u0000\u0000\u0178\u0179\u0001"+
		"\u0000\u0000\u0000\u0179\u017b\u0001\u0000\u0000\u0000\u017a\u017c\u0005"+
		"\u0016\u0000\u0000\u017b\u017a\u0001\u0000\u0000\u0000\u017b\u017c\u0001"+
		"\u0000\u0000\u0000\u017c!\u0001\u0000\u0000\u0000\u017d\u017e\u0005!\u0000"+
		"\u0000\u017e\u0180\u00053\u0000\u0000\u017f\u0181\u0003\b\u0004\u0000"+
		"\u0180\u017f\u0001\u0000\u0000\u0000\u0180\u0181\u0001\u0000\u0000\u0000"+
		"\u0181\u0183\u0001\u0000\u0000\u0000\u0182\u0184\u0003*\u0015\u0000\u0183"+
		"\u0182\u0001\u0000\u0000\u0000\u0183\u0184\u0001\u0000\u0000\u0000\u0184"+
		"\u018d\u0001\u0000\u0000\u0000\u0185\u0189\u0005\u0014\u0000\u0000\u0186"+
		"\u0188\u0003 \u0010\u0000\u0187\u0186\u0001\u0000\u0000\u0000\u0188\u018b"+
		"\u0001\u0000\u0000\u0000\u0189\u0187\u0001\u0000\u0000\u0000\u0189\u018a"+
		"\u0001\u0000\u0000\u0000\u018a\u018c\u0001\u0000\u0000\u0000\u018b\u0189"+
		"\u0001\u0000\u0000\u0000\u018c\u018e\u0005\u0015\u0000\u0000\u018d\u0185"+
		"\u0001\u0000\u0000\u0000\u018d\u018e\u0001\u0000\u0000\u0000\u018e\u0190"+
		"\u0001\u0000\u0000\u0000\u018f\u0191\u0005\u0016\u0000\u0000\u0190\u018f"+
		"\u0001\u0000\u0000\u0000\u0190\u0191\u0001\u0000\u0000\u0000\u0191#\u0001"+
		"\u0000\u0000\u0000\u0192\u0193\u0005$\u0000\u0000\u0193\u0195\u00053\u0000"+
		"\u0000\u0194\u0196\u0003\b\u0004\u0000\u0195\u0194\u0001\u0000\u0000\u0000"+
		"\u0195\u0196\u0001\u0000\u0000\u0000\u0196\u0198\u0001\u0000\u0000\u0000"+
		"\u0197\u0199\u0003\u001a\r\u0000\u0198\u0197\u0001\u0000\u0000\u0000\u0198"+
		"\u0199\u0001\u0000\u0000\u0000\u0199\u019b\u0001\u0000\u0000\u0000\u019a"+
		"\u019c\u0003*\u0015\u0000\u019b\u019a\u0001\u0000\u0000\u0000\u019b\u019c"+
		"\u0001\u0000\u0000\u0000\u019c\u01a5\u0001\u0000\u0000\u0000\u019d\u01a1"+
		"\u0005\u0014\u0000\u0000\u019e\u01a0\u00032\u0019\u0000\u019f\u019e\u0001"+
		"\u0000\u0000\u0000\u01a0\u01a3\u0001\u0000\u0000\u0000\u01a1\u019f\u0001"+
		"\u0000\u0000\u0000\u01a1\u01a2\u0001\u0000\u0000\u0000\u01a2\u01a4\u0001"+
		"\u0000\u0000\u0000\u01a3\u01a1\u0001\u0000\u0000\u0000\u01a4\u01a6\u0005"+
		"\u0015\u0000\u0000\u01a5\u019d\u0001\u0000\u0000\u0000\u01a5\u01a6\u0001"+
		"\u0000\u0000\u0000\u01a6\u01a8\u0001\u0000\u0000\u0000\u01a7\u01a9\u0005"+
		"\u0016\u0000\u0000\u01a8\u01a7\u0001\u0000\u0000\u0000\u01a8\u01a9\u0001"+
		"\u0000\u0000\u0000\u01a9%\u0001\u0000\u0000\u0000\u01aa\u01ab\u0005&\u0000"+
		"\u0000\u01ab\u01bb\u00053\u0000\u0000\u01ac\u01b7\u0005\u0014\u0000\u0000"+
		"\u01ad\u01af\u00053\u0000\u0000\u01ae\u01b0\u0003\b\u0004\u0000\u01af"+
		"\u01ae\u0001\u0000\u0000\u0000\u01af\u01b0\u0001\u0000\u0000\u0000\u01b0"+
		"\u01b2\u0001\u0000\u0000\u0000\u01b1\u01b3\u0003\u001a\r\u0000\u01b2\u01b1"+
		"\u0001\u0000\u0000\u0000\u01b2\u01b3\u0001\u0000\u0000\u0000\u01b3\u01b6"+
		"\u0001\u0000\u0000\u0000\u01b4\u01b6\u0003 \u0010\u0000\u01b5\u01ad\u0001"+
		"\u0000\u0000\u0000\u01b5\u01b4\u0001\u0000\u0000\u0000\u01b6\u01b9\u0001"+
		"\u0000\u0000\u0000\u01b7\u01b5\u0001\u0000\u0000\u0000\u01b7\u01b8\u0001"+
		"\u0000\u0000\u0000\u01b8\u01ba\u0001\u0000\u0000\u0000\u01b9\u01b7\u0001"+
		"\u0000\u0000\u0000\u01ba\u01bc\u0005\u0015\u0000\u0000\u01bb\u01ac\u0001"+
		"\u0000\u0000\u0000\u01bb\u01bc\u0001\u0000\u0000\u0000\u01bc\u01be\u0001"+
		"\u0000\u0000\u0000\u01bd\u01bf\u0005\u0016\u0000\u0000\u01be\u01bd\u0001"+
		"\u0000\u0000\u0000\u01be\u01bf\u0001\u0000\u0000\u0000\u01bf\'\u0001\u0000"+
		"\u0000\u0000\u01c0\u01c1\u0005\u001e\u0000\u0000\u01c1\u01c3\u00053\u0000"+
		"\u0000\u01c2\u01c4\u0003\b\u0004\u0000\u01c3\u01c2\u0001\u0000\u0000\u0000"+
		"\u01c3\u01c4\u0001\u0000\u0000\u0000\u01c4\u01c5\u0001\u0000\u0000\u0000"+
		"\u01c5\u01c6\u0005\u0007\u0000\u0000\u01c6\u01c8\u0003\u0014\n\u0000\u01c7"+
		"\u01c9\u0005\u0016\u0000\u0000\u01c8\u01c7\u0001\u0000\u0000\u0000\u01c8"+
		"\u01c9\u0001\u0000\u0000\u0000\u01c9)\u0001\u0000\u0000\u0000\u01ca\u01cb"+
		"\u0005\u0007\u0000\u0000\u01cb\u01d0\u0003\n\u0005\u0000\u01cc\u01cd\u0005"+
		"\u0003\u0000\u0000\u01cd\u01cf\u0003\n\u0005\u0000\u01ce\u01cc\u0001\u0000"+
		"\u0000\u0000\u01cf\u01d2\u0001\u0000\u0000\u0000\u01d0\u01ce\u0001\u0000"+
		"\u0000\u0000\u01d0\u01d1\u0001\u0000\u0000\u0000\u01d1+\u0001\u0000\u0000"+
		"\u0000\u01d2\u01d0\u0001\u0000\u0000\u0000\u01d3\u01d4\u0005\u001c\u0000"+
		"\u0000\u01d4\u01d6\u0003\n\u0005\u0000\u01d5\u01d7\u0005\u0016\u0000\u0000"+
		"\u01d6\u01d5\u0001\u0000\u0000\u0000\u01d6\u01d7\u0001\u0000\u0000\u0000"+
		"\u01d7-\u0001\u0000\u0000\u0000\u01d8\u01d9\u0005\u001d\u0000\u0000\u01d9"+
		"\u01db\u0003\n\u0005\u0000\u01da\u01dc\u0005\u0016\u0000\u0000\u01db\u01da"+
		"\u0001\u0000\u0000\u0000\u01db\u01dc\u0001\u0000\u0000\u0000\u01dc/\u0001"+
		"\u0000\u0000\u0000\u01dd\u01e4\u0003\u001e\u000f\u0000\u01de\u01e4\u0003"+
		" \u0010\u0000\u01df\u01e4\u0003\"\u0011\u0000\u01e0\u01e4\u0003$\u0012"+
		"\u0000\u01e1\u01e4\u0003&\u0013\u0000\u01e2\u01e4\u0003(\u0014\u0000\u01e3"+
		"\u01dd\u0001\u0000\u0000\u0000\u01e3\u01de\u0001\u0000\u0000\u0000\u01e3"+
		"\u01df\u0001\u0000\u0000\u0000\u01e3\u01e0\u0001\u0000\u0000\u0000\u01e3"+
		"\u01e1\u0001\u0000\u0000\u0000\u01e3\u01e2\u0001\u0000\u0000\u0000\u01e4"+
		"1\u0001\u0000\u0000\u0000\u01e5\u01e6\u0003 \u0010\u0000\u01e63\u0001"+
		"\u0000\u0000\u0000\u01e7\u01eb\u0003,\u0016\u0000\u01e8\u01ea\u0003.\u0017"+
		"\u0000\u01e9\u01e8\u0001\u0000\u0000\u0000\u01ea\u01ed\u0001\u0000\u0000"+
		"\u0000\u01eb\u01e9\u0001\u0000\u0000\u0000\u01eb\u01ec\u0001\u0000\u0000"+
		"\u0000\u01ec\u01f1\u0001\u0000\u0000\u0000\u01ed\u01eb\u0001\u0000\u0000"+
		"\u0000\u01ee\u01f0\u00030\u0018\u0000\u01ef\u01ee\u0001\u0000\u0000\u0000"+
		"\u01f0\u01f3\u0001\u0000\u0000\u0000\u01f1\u01ef\u0001\u0000\u0000\u0000"+
		"\u01f1\u01f2\u0001\u0000\u0000\u0000\u01f2\u01f4\u0001\u0000\u0000\u0000"+
		"\u01f3\u01f1\u0001\u0000\u0000\u0000\u01f4\u01f5\u0005\u0000\u0000\u0001"+
		"\u01f55\u0001\u0000\u0000\u0000E:AKOY]fjpw\u0081\u0085\u0091\u0097\u00a2"+
		"\u00a6\u00aa\u00ac\u00b4\u00b8\u00c7\u00e6\u00ed\u00f1\u00f5\u00fb\u0102"+
		"\u010d\u0111\u0119\u011b\u014d\u014f\u0155\u0159\u015d\u0160\u0164\u0169"+
		"\u016d\u0170\u0174\u0178\u017b\u0180\u0183\u0189\u018d\u0190\u0195\u0198"+
		"\u019b\u01a1\u01a5\u01a8\u01af\u01b2\u01b5\u01b7\u01bb\u01be\u01c3\u01c8"+
		"\u01d0\u01d6\u01db\u01e3\u01eb\u01f1";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}