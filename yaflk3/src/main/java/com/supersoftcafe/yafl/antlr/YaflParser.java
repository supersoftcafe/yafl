// Generated from /Users/mbrown/Projects/yafl/yaflk3/Yafl.g4 by ANTLR 4.12.0
package com.supersoftcafe.yafl.antlr;
import org.antlr.v4.runtime.atn.*;
import org.antlr.v4.runtime.dfa.DFA;
import org.antlr.v4.runtime.*;
import org.antlr.v4.runtime.misc.*;
import org.antlr.v4.runtime.tree.*;
import java.util.List;
import java.util.Iterator;
import java.util.ArrayList;

@SuppressWarnings({"all", "warnings", "unchecked", "unused", "cast", "CheckReturnValue"})
public class YaflParser extends Parser {
	static { RuntimeMetaData.checkVersion("4.12.0", RuntimeMetaData.VERSION); }

	protected static final DFA[] _decisionToDFA;
	protected static final PredictionContextCache _sharedContextCache =
		new PredictionContextCache();
	public static final int
		T__0=1, T__1=2, T__2=3, T__3=4, T__4=5, T__5=6, T__6=7, T__7=8, T__8=9, 
		T__9=10, T__10=11, T__11=12, T__12=13, T__13=14, T__14=15, T__15=16, T__16=17, 
		T__17=18, T__18=19, T__19=20, LLVM_IR=21, PRIMITIVE=22, ASSERT=23, RAW_POINTER=24, 
		PARALLEL=25, MODULE=26, IMPORT=27, ALIAS=28, WHEN=29, IS=30, ELSE=31, 
		END=32, TEMPLATE=33, FUN=34, MEMBER_FUN=35, LET=36, MEMBER_LET=37, INTERFACE=38, 
		TRAIT=39, IMPL=40, CLASS=41, STRUCT=42, OBJECT=43, ENUM=44, LAZY=45, LAMBDA=46, 
		PIPE_RIGHT=47, PIPE_MAYBE=48, NAMESPACE=49, CMP_LE=50, CMP_GE=51, CMP_EQ=52, 
		CMP_NE=53, SHL=54, SHR=55, POW=56, TAG=57, NAME=58, INTEGER=59, STRING=60, 
		WS=61, COMMENT=62;
	public static final int
		RULE_qualifiedName = 0, RULE_exprOfTuplePart = 1, RULE_exprOfTuple = 2, 
		RULE_typeRef = 3, RULE_typeOfTuplePart = 4, RULE_typeOfTuple = 5, RULE_typeOfTagsPart = 6, 
		RULE_typeOfTags = 7, RULE_typePrimitive = 8, RULE_typeOfLambda = 9, RULE_type = 10, 
		RULE_attributes = 11, RULE_valueParamsBody = 12, RULE_valueParamsArray = 13, 
		RULE_valueParamsPart = 14, RULE_valueParamsDeclare = 15, RULE_whenBranch = 16, 
		RULE_expression = 17, RULE_let = 18, RULE_functionTail = 19, RULE_function = 20, 
		RULE_classMember = 21, RULE_interface = 22, RULE_class = 23, RULE_alias = 24, 
		RULE_extends = 25, RULE_module = 26, RULE_import_ = 27, RULE_declaration = 28, 
		RULE_root = 29;
	private static String[] makeRuleNames() {
		return new String[] {
			"qualifiedName", "exprOfTuplePart", "exprOfTuple", "typeRef", "typeOfTuplePart", 
			"typeOfTuple", "typeOfTagsPart", "typeOfTags", "typePrimitive", "typeOfLambda", 
			"type", "attributes", "valueParamsBody", "valueParamsArray", "valueParamsPart", 
			"valueParamsDeclare", "whenBranch", "expression", "let", "functionTail", 
			"function", "classMember", "interface", "class", "alias", "extends", 
			"module", "import_", "declaration", "root"
		};
	}
	public static final String[] ruleNames = makeRuleNames();

	private static String[] makeLiteralNames() {
		return new String[] {
			null, "'='", "'('", "','", "')'", "':'", "'['", "']'", "'<'", "'>'", 
			"'.'", "'+'", "'-'", "'*'", "'/'", "'%'", "'&'", "'^'", "'|'", "'?'", 
			"';'", "'__llvm_ir__'", "'__primitive__'", "'__assert__'", "'__raw_pointer__'", 
			"'__parallel__'", "'module'", "'import'", "'alias'", "'when'", "'is'", 
			"'else'", "'end'", "'template'", "'fun'", null, "'let'", null, "'interface'", 
			"'trait'", "'impl'", "'class'", "'struct'", "'object'", "'enum'", "'lazy'", 
			"'=>'", "'|>'", "'?>'", "'::'", "'<='", "'>='", "'=='", "'!='", "'<<'", 
			"'>>'", "'**'"
		};
	}
	private static final String[] _LITERAL_NAMES = makeLiteralNames();
	private static String[] makeSymbolicNames() {
		return new String[] {
			null, null, null, null, null, null, null, null, null, null, null, null, 
			null, null, null, null, null, null, null, null, null, "LLVM_IR", "PRIMITIVE", 
			"ASSERT", "RAW_POINTER", "PARALLEL", "MODULE", "IMPORT", "ALIAS", "WHEN", 
			"IS", "ELSE", "END", "TEMPLATE", "FUN", "MEMBER_FUN", "LET", "MEMBER_LET", 
			"INTERFACE", "TRAIT", "IMPL", "CLASS", "STRUCT", "OBJECT", "ENUM", "LAZY", 
			"LAMBDA", "PIPE_RIGHT", "PIPE_MAYBE", "NAMESPACE", "CMP_LE", "CMP_GE", 
			"CMP_EQ", "CMP_NE", "SHL", "SHR", "POW", "TAG", "NAME", "INTEGER", "STRING", 
			"WS", "COMMENT"
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

	@SuppressWarnings("CheckReturnValue")
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
			setState(64);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,0,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(60);
					match(NAME);
					setState(61);
					match(NAMESPACE);
					}
					} 
				}
				setState(66);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,0,_ctx);
			}
			setState(67);
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

	@SuppressWarnings("CheckReturnValue")
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
			setState(71);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,1,_ctx) ) {
			case 1:
				{
				setState(69);
				match(NAME);
				setState(70);
				match(T__0);
				}
				break;
			}
			setState(73);
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

	@SuppressWarnings("CheckReturnValue")
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
			setState(75);
			match(T__1);
			setState(81);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,2,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(76);
					exprOfTuplePart();
					setState(77);
					match(T__2);
					}
					} 
				}
				setState(83);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,2,_ctx);
			}
			setState(85);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & 2161727907634878532L) != 0)) {
				{
				setState(84);
				exprOfTuplePart();
				}
			}

			setState(87);
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

	@SuppressWarnings("CheckReturnValue")
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
			setState(89);
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 8, RULE_typeOfTuplePart);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(93);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,4,_ctx) ) {
			case 1:
				{
				setState(91);
				match(NAME);
				setState(92);
				match(T__4);
				}
				break;
			}
			setState(95);
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 10, RULE_typeOfTuple);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(97);
			match(T__1);
			setState(103);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,5,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(98);
					typeOfTuplePart();
					setState(99);
					match(T__2);
					}
					} 
				}
				setState(105);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,5,_ctx);
			}
			setState(107);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & 432345564231761924L) != 0)) {
				{
				setState(106);
				typeOfTuplePart();
				}
			}

			setState(109);
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

	@SuppressWarnings("CheckReturnValue")
	public static class TypeOfTagsPartContext extends ParserRuleContext {
		public TerminalNode TAG() { return getToken(YaflParser.TAG, 0); }
		public TypeOfTupleContext typeOfTuple() {
			return getRuleContext(TypeOfTupleContext.class,0);
		}
		public TypeOfTagsPartContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_typeOfTagsPart; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTypeOfTagsPart(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTypeOfTagsPart(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTypeOfTagsPart(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypeOfTagsPartContext typeOfTagsPart() throws RecognitionException {
		TypeOfTagsPartContext _localctx = new TypeOfTagsPartContext(_ctx, getState());
		enterRule(_localctx, 12, RULE_typeOfTagsPart);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(111);
			match(TAG);
			setState(113);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,7,_ctx) ) {
			case 1:
				{
				setState(112);
				typeOfTuple();
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

	@SuppressWarnings("CheckReturnValue")
	public static class TypeOfTagsContext extends ParserRuleContext {
		public List<TypeOfTagsPartContext> typeOfTagsPart() {
			return getRuleContexts(TypeOfTagsPartContext.class);
		}
		public TypeOfTagsPartContext typeOfTagsPart(int i) {
			return getRuleContext(TypeOfTagsPartContext.class,i);
		}
		public TypeOfTagsContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_typeOfTags; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTypeOfTags(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTypeOfTags(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTypeOfTags(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypeOfTagsContext typeOfTags() throws RecognitionException {
		TypeOfTagsContext _localctx = new TypeOfTagsContext(_ctx, getState());
		enterRule(_localctx, 14, RULE_typeOfTags);
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(116); 
			_errHandler.sync(this);
			_alt = 1;
			do {
				switch (_alt) {
				case 1:
					{
					{
					setState(115);
					typeOfTagsPart();
					}
					}
					break;
				default:
					throw new NoViableAltException(this);
				}
				setState(118); 
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,8,_ctx);
			} while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER );
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 16, RULE_typePrimitive);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(120);
			match(PRIMITIVE);
			setState(121);
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

	@SuppressWarnings("CheckReturnValue")
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
			setState(123);
			typeOfTuple();
			setState(124);
			match(T__4);
			setState(125);
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

	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
	public static class TagsTypeContext extends TypeContext {
		public TypeOfTagsContext typeOfTags() {
			return getRuleContext(TypeOfTagsContext.class,0);
		}
		public TagsTypeContext(TypeContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTagsType(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTagsType(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTagsType(this);
			else return visitor.visitChildren(this);
		}
	}
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
			setState(132);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,9,_ctx) ) {
			case 1:
				_localctx = new NamedTypeContext(_localctx);
				enterOuterAlt(_localctx, 1);
				{
				setState(127);
				typeRef();
				}
				break;
			case 2:
				_localctx = new PrimitiveTypeContext(_localctx);
				enterOuterAlt(_localctx, 2);
				{
				setState(128);
				typePrimitive();
				}
				break;
			case 3:
				_localctx = new TupleTypeContext(_localctx);
				enterOuterAlt(_localctx, 3);
				{
				setState(129);
				typeOfTuple();
				}
				break;
			case 4:
				_localctx = new TagsTypeContext(_localctx);
				enterOuterAlt(_localctx, 4);
				{
				setState(130);
				typeOfTags();
				}
				break;
			case 5:
				_localctx = new LambdaTypeContext(_localctx);
				enterOuterAlt(_localctx, 5);
				{
				setState(131);
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

	@SuppressWarnings("CheckReturnValue")
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
			setState(134);
			match(T__5);
			setState(138);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==NAME) {
				{
				{
				setState(135);
				match(NAME);
				}
				}
				setState(140);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(141);
			match(T__6);
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

	@SuppressWarnings("CheckReturnValue")
	public static class ValueParamsBodyContext extends ParserRuleContext {
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public ValueParamsBodyContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_valueParamsBody; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterValueParamsBody(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitValueParamsBody(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitValueParamsBody(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ValueParamsBodyContext valueParamsBody() throws RecognitionException {
		ValueParamsBodyContext _localctx = new ValueParamsBodyContext(_ctx, getState());
		enterRule(_localctx, 24, RULE_valueParamsBody);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(143);
			match(T__0);
			setState(144);
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

	@SuppressWarnings("CheckReturnValue")
	public static class ValueParamsArrayContext extends ParserRuleContext {
		public TerminalNode INTEGER() { return getToken(YaflParser.INTEGER, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode CMP_LE() { return getToken(YaflParser.CMP_LE, 0); }
		public ValueParamsArrayContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_valueParamsArray; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterValueParamsArray(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitValueParamsArray(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitValueParamsArray(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ValueParamsArrayContext valueParamsArray() throws RecognitionException {
		ValueParamsArrayContext _localctx = new ValueParamsArrayContext(_ctx, getState());
		enterRule(_localctx, 26, RULE_valueParamsArray);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(146);
			match(T__5);
			setState(150);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,11,_ctx) ) {
			case 1:
				{
				setState(147);
				expression(0);
				setState(148);
				match(CMP_LE);
				}
				break;
			}
			setState(152);
			match(INTEGER);
			setState(153);
			match(T__6);
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

	@SuppressWarnings("CheckReturnValue")
	public static class ValueParamsPartContext extends ParserRuleContext {
		public ValueParamsDeclareContext valueParamsDeclare() {
			return getRuleContext(ValueParamsDeclareContext.class,0);
		}
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public ValueParamsArrayContext valueParamsArray() {
			return getRuleContext(ValueParamsArrayContext.class,0);
		}
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public ValueParamsBodyContext valueParamsBody() {
			return getRuleContext(ValueParamsBodyContext.class,0);
		}
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
		enterRule(_localctx, 28, RULE_valueParamsPart);
		int _la;
		try {
			setState(167);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case T__1:
				enterOuterAlt(_localctx, 1);
				{
				setState(155);
				valueParamsDeclare();
				}
				break;
			case NAME:
				enterOuterAlt(_localctx, 2);
				{
				{
				setState(156);
				match(NAME);
				setState(158);
				_errHandler.sync(this);
				switch ( getInterpreter().adaptivePredict(_input,12,_ctx) ) {
				case 1:
					{
					setState(157);
					valueParamsArray();
					}
					break;
				}
				setState(162);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__4) {
					{
					setState(160);
					match(T__4);
					setState(161);
					type();
					}
				}

				setState(165);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__0) {
					{
					setState(164);
					valueParamsBody();
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 30, RULE_valueParamsDeclare);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(169);
			match(T__1);
			setState(175);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,16,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					{
					{
					setState(170);
					valueParamsPart();
					setState(171);
					match(T__2);
					}
					} 
				}
				setState(177);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,16,_ctx);
			}
			setState(179);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__1 || _la==NAME) {
				{
				setState(178);
				valueParamsPart();
				}
			}

			setState(181);
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

	@SuppressWarnings("CheckReturnValue")
	public static class WhenBranchContext extends ParserRuleContext {
		public TerminalNode LAMBDA() { return getToken(YaflParser.LAMBDA, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode ELSE() { return getToken(YaflParser.ELSE, 0); }
		public TerminalNode IS() { return getToken(YaflParser.IS, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public ValueParamsDeclareContext valueParamsDeclare() {
			return getRuleContext(ValueParamsDeclareContext.class,0);
		}
		public WhenBranchContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_whenBranch; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterWhenBranch(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitWhenBranch(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitWhenBranch(this);
			else return visitor.visitChildren(this);
		}
	}

	public final WhenBranchContext whenBranch() throws RecognitionException {
		WhenBranchContext _localctx = new WhenBranchContext(_ctx, getState());
		enterRule(_localctx, 32, RULE_whenBranch);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(189);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case IS:
				{
				{
				setState(183);
				match(IS);
				setState(184);
				match(NAME);
				setState(186);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__1) {
					{
					setState(185);
					valueParamsDeclare();
					}
				}

				}
				}
				break;
			case ELSE:
				{
				setState(188);
				match(ELSE);
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
			setState(191);
			match(LAMBDA);
			setState(192);
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

	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
	public static class TagExprContext extends ExpressionContext {
		public TerminalNode TAG() { return getToken(YaflParser.TAG, 0); }
		public ExprOfTupleContext exprOfTuple() {
			return getRuleContext(ExprOfTupleContext.class,0);
		}
		public TagExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterTagExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitTagExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitTagExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
	public static class WhenExprContext extends ExpressionContext {
		public TerminalNode WHEN() { return getToken(YaflParser.WHEN, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public List<WhenBranchContext> whenBranch() {
			return getRuleContexts(WhenBranchContext.class);
		}
		public WhenBranchContext whenBranch(int i) {
			return getRuleContext(WhenBranchContext.class,i);
		}
		public WhenExprContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterWhenExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitWhenExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitWhenExpr(this);
			else return visitor.visitChildren(this);
		}
	}
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
	@SuppressWarnings("CheckReturnValue")
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
		int _startState = 34;
		enterRecursionRule(_localctx, 34, RULE_expression, _p);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(277);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,28,_ctx) ) {
			case 1:
				{
				_localctx = new LlvmirExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;

				setState(195);
				match(LLVM_IR);
				setState(196);
				match(T__7);
				setState(197);
				type();
				setState(198);
				match(T__8);
				setState(199);
				match(T__1);
				setState(200);
				((LlvmirExprContext)_localctx).pattern = match(STRING);
				setState(205);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while (_la==T__2) {
					{
					{
					setState(201);
					match(T__2);
					setState(202);
					expression(0);
					}
					}
					setState(207);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(208);
				match(T__3);
				}
				break;
			case 2:
				{
				_localctx = new AssertExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(210);
				match(ASSERT);
				setState(211);
				match(T__1);
				setState(212);
				((AssertExprContext)_localctx).value = expression(0);
				setState(213);
				match(T__2);
				setState(214);
				((AssertExprContext)_localctx).condition = expression(0);
				setState(215);
				match(T__2);
				setState(216);
				((AssertExprContext)_localctx).message = match(STRING);
				setState(217);
				match(T__3);
				}
				break;
			case 3:
				{
				_localctx = new RawPointerExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(219);
				match(RAW_POINTER);
				setState(220);
				match(T__1);
				setState(221);
				((RawPointerExprContext)_localctx).value = expression(0);
				setState(222);
				match(T__3);
				}
				break;
			case 4:
				{
				_localctx = new ParallelExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(224);
				match(PARALLEL);
				setState(225);
				((ParallelExprContext)_localctx).params = exprOfTuple();
				}
				break;
			case 5:
				{
				_localctx = new UnaryExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(226);
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
				setState(227);
				((UnaryExprContext)_localctx).right = expression(21);
				}
				break;
			case 6:
				{
				_localctx = new TupleExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(228);
				exprOfTuple();
				}
				break;
			case 7:
				{
				_localctx = new TagExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(229);
				match(TAG);
				setState(231);
				_errHandler.sync(this);
				switch ( getInterpreter().adaptivePredict(_input,21,_ctx) ) {
				case 1:
					{
					setState(230);
					exprOfTuple();
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
				setState(233);
				let();
				setState(235);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__19) {
					{
					setState(234);
					match(T__19);
					}
				}

				setState(237);
				expression(8);
				}
				break;
			case 9:
				{
				_localctx = new FunctionExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(239);
				function();
				setState(241);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__19) {
					{
					setState(240);
					match(T__19);
					}
				}

				setState(243);
				expression(7);
				}
				break;
			case 10:
				{
				_localctx = new LambdaExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(245);
				valueParamsDeclare();
				setState(248);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__4) {
					{
					setState(246);
					match(T__4);
					setState(247);
					type();
					}
				}

				setState(250);
				match(LAMBDA);
				setState(251);
				expression(6);
				}
				break;
			case 11:
				{
				_localctx = new NewArrayExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(253);
				match(T__5);
				setState(254);
				expression(0);
				setState(259);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,25,_ctx);
				while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
					if ( _alt==1 ) {
						{
						{
						setState(255);
						match(T__2);
						setState(256);
						expression(0);
						}
						} 
					}
					setState(261);
					_errHandler.sync(this);
					_alt = getInterpreter().adaptivePredict(_input,25,_ctx);
				}
				setState(263);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==T__2) {
					{
					setState(262);
					match(T__2);
					}
				}

				setState(265);
				match(T__6);
				}
				break;
			case 12:
				{
				_localctx = new StringExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(267);
				match(STRING);
				}
				break;
			case 13:
				{
				_localctx = new IntegerExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(268);
				match(INTEGER);
				}
				break;
			case 14:
				{
				_localctx = new NameExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(269);
				qualifiedName();
				}
				break;
			case 15:
				{
				_localctx = new WhenExprContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(270);
				match(WHEN);
				setState(271);
				expression(0);
				setState(273); 
				_errHandler.sync(this);
				_alt = 1;
				do {
					switch (_alt) {
					case 1:
						{
						{
						setState(272);
						whenBranch();
						}
						}
						break;
					default:
						throw new NoViableAltException(this);
					}
					setState(275); 
					_errHandler.sync(this);
					_alt = getInterpreter().adaptivePredict(_input,27,_ctx);
				} while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER );
				}
				break;
			}
			_ctx.stop = _input.LT(-1);
			setState(329);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,30,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					if ( _parseListeners!=null ) triggerExitRuleEvent();
					_prevctx = _localctx;
					{
					setState(327);
					_errHandler.sync(this);
					switch ( getInterpreter().adaptivePredict(_input,29,_ctx) ) {
					case 1:
						{
						_localctx = new PowerExprContext(new ExpressionContext(_parentctx, _parentState));
						((PowerExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(279);
						if (!(precpred(_ctx, 20))) throw new FailedPredicateException(this, "precpred(_ctx, 20)");
						setState(280);
						((PowerExprContext)_localctx).operator = match(POW);
						setState(281);
						((PowerExprContext)_localctx).right = expression(21);
						}
						break;
					case 2:
						{
						_localctx = new ProductExprContext(new ExpressionContext(_parentctx, _parentState));
						((ProductExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(282);
						if (!(precpred(_ctx, 19))) throw new FailedPredicateException(this, "precpred(_ctx, 19)");
						setState(283);
						((ProductExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & 57344L) != 0)) ) {
							((ProductExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(284);
						((ProductExprContext)_localctx).right = expression(20);
						}
						break;
					case 3:
						{
						_localctx = new SumExprContext(new ExpressionContext(_parentctx, _parentState));
						((SumExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(285);
						if (!(precpred(_ctx, 18))) throw new FailedPredicateException(this, "precpred(_ctx, 18)");
						setState(286);
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
						setState(287);
						((SumExprContext)_localctx).right = expression(19);
						}
						break;
					case 4:
						{
						_localctx = new ShiftExprContext(new ExpressionContext(_parentctx, _parentState));
						((ShiftExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(288);
						if (!(precpred(_ctx, 17))) throw new FailedPredicateException(this, "precpred(_ctx, 17)");
						setState(289);
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
						setState(290);
						((ShiftExprContext)_localctx).right = expression(18);
						}
						break;
					case 5:
						{
						_localctx = new CompareExprContext(new ExpressionContext(_parentctx, _parentState));
						((CompareExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(291);
						if (!(precpred(_ctx, 16))) throw new FailedPredicateException(this, "precpred(_ctx, 16)");
						setState(292);
						((CompareExprContext)_localctx).operator = _input.LT(1);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & 3377699720528640L) != 0)) ) {
							((CompareExprContext)_localctx).operator = (Token)_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(293);
						((CompareExprContext)_localctx).right = expression(17);
						}
						break;
					case 6:
						{
						_localctx = new EqualExprContext(new ExpressionContext(_parentctx, _parentState));
						((EqualExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(294);
						if (!(precpred(_ctx, 15))) throw new FailedPredicateException(this, "precpred(_ctx, 15)");
						setState(295);
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
						setState(296);
						((EqualExprContext)_localctx).right = expression(16);
						}
						break;
					case 7:
						{
						_localctx = new BitAndExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitAndExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(297);
						if (!(precpred(_ctx, 14))) throw new FailedPredicateException(this, "precpred(_ctx, 14)");
						setState(298);
						((BitAndExprContext)_localctx).operator = match(T__15);
						setState(299);
						((BitAndExprContext)_localctx).right = expression(15);
						}
						break;
					case 8:
						{
						_localctx = new BitXorExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitXorExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(300);
						if (!(precpred(_ctx, 13))) throw new FailedPredicateException(this, "precpred(_ctx, 13)");
						setState(301);
						((BitXorExprContext)_localctx).operator = match(T__16);
						setState(302);
						((BitXorExprContext)_localctx).right = expression(14);
						}
						break;
					case 9:
						{
						_localctx = new BitOrExprContext(new ExpressionContext(_parentctx, _parentState));
						((BitOrExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(303);
						if (!(precpred(_ctx, 12))) throw new FailedPredicateException(this, "precpred(_ctx, 12)");
						setState(304);
						((BitOrExprContext)_localctx).operator = match(T__17);
						setState(305);
						((BitOrExprContext)_localctx).right = expression(13);
						}
						break;
					case 10:
						{
						_localctx = new DotExprContext(new ExpressionContext(_parentctx, _parentState));
						((DotExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(306);
						if (!(precpred(_ctx, 26))) throw new FailedPredicateException(this, "precpred(_ctx, 26)");
						setState(307);
						((DotExprContext)_localctx).operator = match(T__9);
						setState(308);
						((DotExprContext)_localctx).right = match(NAME);
						}
						break;
					case 11:
						{
						_localctx = new CallExprContext(new ExpressionContext(_parentctx, _parentState));
						((CallExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(309);
						if (!(precpred(_ctx, 25))) throw new FailedPredicateException(this, "precpred(_ctx, 25)");
						setState(310);
						((CallExprContext)_localctx).params = exprOfTuple();
						}
						break;
					case 12:
						{
						_localctx = new ArrayLookupExprContext(new ExpressionContext(_parentctx, _parentState));
						((ArrayLookupExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(311);
						if (!(precpred(_ctx, 23))) throw new FailedPredicateException(this, "precpred(_ctx, 23)");
						setState(312);
						match(T__5);
						setState(313);
						((ArrayLookupExprContext)_localctx).right = expression(0);
						setState(314);
						match(T__6);
						}
						break;
					case 13:
						{
						_localctx = new ApplyExprContext(new ExpressionContext(_parentctx, _parentState));
						((ApplyExprContext)_localctx).left = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(316);
						if (!(precpred(_ctx, 22))) throw new FailedPredicateException(this, "precpred(_ctx, 22)");
						setState(317);
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
						setState(318);
						((ApplyExprContext)_localctx).right = expression(0);
						setState(319);
						((ApplyExprContext)_localctx).params = exprOfTuple();
						}
						break;
					case 14:
						{
						_localctx = new IfExprContext(new ExpressionContext(_parentctx, _parentState));
						((IfExprContext)_localctx).condition = _prevctx;
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(321);
						if (!(precpred(_ctx, 11))) throw new FailedPredicateException(this, "precpred(_ctx, 11)");
						{
						setState(322);
						match(T__18);
						setState(323);
						((IfExprContext)_localctx).left = expression(0);
						setState(324);
						match(T__4);
						setState(325);
						((IfExprContext)_localctx).right = expression(0);
						}
						}
						break;
					}
					} 
				}
				setState(331);
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

	@SuppressWarnings("CheckReturnValue")
	public static class LetContext extends ParserRuleContext {
		public TerminalNode LET() { return getToken(YaflParser.LET, 0); }
		public ValueParamsPartContext valueParamsPart() {
			return getRuleContext(ValueParamsPartContext.class,0);
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
		enterRule(_localctx, 36, RULE_let);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(332);
			match(LET);
			setState(333);
			valueParamsPart();
			setState(335);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,31,_ctx) ) {
			case 1:
				{
				setState(334);
				match(T__19);
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

	@SuppressWarnings("CheckReturnValue")
	public static class FunctionTailContext extends ParserRuleContext {
		public TypeRefContext extensionType;
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public AttributesContext attributes() {
			return getRuleContext(AttributesContext.class,0);
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
		public FunctionTailContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_functionTail; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).enterFunctionTail(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof YaflListener ) ((YaflListener)listener).exitFunctionTail(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof YaflVisitor ) return ((YaflVisitor<? extends T>)visitor).visitFunctionTail(this);
			else return visitor.visitChildren(this);
		}
	}

	public final FunctionTailContext functionTail() throws RecognitionException {
		FunctionTailContext _localctx = new FunctionTailContext(_ctx, getState());
		enterRule(_localctx, 38, RULE_functionTail);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(338);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__5) {
				{
				setState(337);
				attributes();
				}
			}

			setState(343);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,33,_ctx) ) {
			case 1:
				{
				setState(340);
				((FunctionTailContext)_localctx).extensionType = typeRef();
				setState(341);
				match(T__9);
				}
				break;
			}
			setState(345);
			match(NAME);
			setState(347);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,34,_ctx) ) {
			case 1:
				{
				setState(346);
				valueParamsDeclare();
				}
				break;
			}
			setState(351);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(349);
				match(T__4);
				setState(350);
				type();
				}
			}

			setState(355);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==LAMBDA) {
				{
				setState(353);
				match(LAMBDA);
				setState(354);
				expression(0);
				}
			}

			setState(358);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,37,_ctx) ) {
			case 1:
				{
				setState(357);
				match(T__19);
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

	@SuppressWarnings("CheckReturnValue")
	public static class FunctionContext extends ParserRuleContext {
		public TerminalNode FUN() { return getToken(YaflParser.FUN, 0); }
		public FunctionTailContext functionTail() {
			return getRuleContext(FunctionTailContext.class,0);
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
		enterRule(_localctx, 40, RULE_function);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(360);
			match(FUN);
			setState(361);
			functionTail();
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

	@SuppressWarnings("CheckReturnValue")
	public static class ClassMemberContext extends ParserRuleContext {
		public TerminalNode MEMBER_FUN() { return getToken(YaflParser.MEMBER_FUN, 0); }
		public FunctionTailContext functionTail() {
			return getRuleContext(FunctionTailContext.class,0);
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
		enterRule(_localctx, 42, RULE_classMember);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(363);
			match(MEMBER_FUN);
			setState(364);
			functionTail();
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

	@SuppressWarnings("CheckReturnValue")
	public static class InterfaceContext extends ParserRuleContext {
		public TerminalNode INTERFACE() { return getToken(YaflParser.INTERFACE, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
		public ExtendsContext extends_() {
			return getRuleContext(ExtendsContext.class,0);
		}
		public List<ClassMemberContext> classMember() {
			return getRuleContexts(ClassMemberContext.class);
		}
		public ClassMemberContext classMember(int i) {
			return getRuleContext(ClassMemberContext.class,i);
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
		enterRule(_localctx, 44, RULE_interface);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(366);
			match(INTERFACE);
			setState(367);
			match(NAME);
			setState(369);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(368);
				extends_();
				}
			}

			setState(374);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==MEMBER_FUN) {
				{
				{
				setState(371);
				classMember();
				}
				}
				setState(376);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(378);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__19) {
				{
				setState(377);
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

	@SuppressWarnings("CheckReturnValue")
	public static class ClassContext extends ParserRuleContext {
		public TerminalNode CLASS() { return getToken(YaflParser.CLASS, 0); }
		public TerminalNode NAME() { return getToken(YaflParser.NAME, 0); }
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
		enterRule(_localctx, 46, RULE_class);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(380);
			match(CLASS);
			setState(381);
			match(NAME);
			setState(383);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__1) {
				{
				setState(382);
				valueParamsDeclare();
				}
			}

			setState(386);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(385);
				extends_();
				}
			}

			setState(391);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==MEMBER_FUN) {
				{
				{
				setState(388);
				classMember();
				}
				}
				setState(393);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(395);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__19) {
				{
				setState(394);
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 48, RULE_alias);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(397);
			match(ALIAS);
			setState(398);
			match(NAME);
			setState(399);
			match(T__4);
			setState(400);
			type();
			setState(402);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__19) {
				{
				setState(401);
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 50, RULE_extends);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(404);
			match(T__4);
			setState(405);
			typeRef();
			setState(410);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==T__2) {
				{
				{
				setState(406);
				match(T__2);
				setState(407);
				typeRef();
				}
				}
				setState(412);
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 52, RULE_module);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(413);
			match(MODULE);
			setState(414);
			typeRef();
			setState(416);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__19) {
				{
				setState(415);
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 54, RULE_import_);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(418);
			match(IMPORT);
			setState(419);
			typeRef();
			setState(421);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__19) {
				{
				setState(420);
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 56, RULE_declaration);
		try {
			setState(428);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case LET:
				enterOuterAlt(_localctx, 1);
				{
				setState(423);
				let();
				}
				break;
			case FUN:
				enterOuterAlt(_localctx, 2);
				{
				setState(424);
				function();
				}
				break;
			case INTERFACE:
				enterOuterAlt(_localctx, 3);
				{
				setState(425);
				interface_();
				}
				break;
			case CLASS:
				enterOuterAlt(_localctx, 4);
				{
				setState(426);
				class_();
				}
				break;
			case ALIAS:
				enterOuterAlt(_localctx, 5);
				{
				setState(427);
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

	@SuppressWarnings("CheckReturnValue")
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
		enterRule(_localctx, 58, RULE_root);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(430);
			module();
			setState(434);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==IMPORT) {
				{
				{
				setState(431);
				import_();
				}
				}
				setState(436);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(440);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while ((((_la) & ~0x3f) == 0 && ((1L << _la) & 2560068943872L) != 0)) {
				{
				{
				setState(437);
				declaration();
				}
				}
				setState(442);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(443);
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
		case 17:
			return expression_sempred((ExpressionContext)_localctx, predIndex);
		}
		return true;
	}
	private boolean expression_sempred(ExpressionContext _localctx, int predIndex) {
		switch (predIndex) {
		case 0:
			return precpred(_ctx, 20);
		case 1:
			return precpred(_ctx, 19);
		case 2:
			return precpred(_ctx, 18);
		case 3:
			return precpred(_ctx, 17);
		case 4:
			return precpred(_ctx, 16);
		case 5:
			return precpred(_ctx, 15);
		case 6:
			return precpred(_ctx, 14);
		case 7:
			return precpred(_ctx, 13);
		case 8:
			return precpred(_ctx, 12);
		case 9:
			return precpred(_ctx, 26);
		case 10:
			return precpred(_ctx, 25);
		case 11:
			return precpred(_ctx, 23);
		case 12:
			return precpred(_ctx, 22);
		case 13:
			return precpred(_ctx, 11);
		}
		return true;
	}

	public static final String _serializedATN =
		"\u0004\u0001>\u01be\u0002\u0000\u0007\u0000\u0002\u0001\u0007\u0001\u0002"+
		"\u0002\u0007\u0002\u0002\u0003\u0007\u0003\u0002\u0004\u0007\u0004\u0002"+
		"\u0005\u0007\u0005\u0002\u0006\u0007\u0006\u0002\u0007\u0007\u0007\u0002"+
		"\b\u0007\b\u0002\t\u0007\t\u0002\n\u0007\n\u0002\u000b\u0007\u000b\u0002"+
		"\f\u0007\f\u0002\r\u0007\r\u0002\u000e\u0007\u000e\u0002\u000f\u0007\u000f"+
		"\u0002\u0010\u0007\u0010\u0002\u0011\u0007\u0011\u0002\u0012\u0007\u0012"+
		"\u0002\u0013\u0007\u0013\u0002\u0014\u0007\u0014\u0002\u0015\u0007\u0015"+
		"\u0002\u0016\u0007\u0016\u0002\u0017\u0007\u0017\u0002\u0018\u0007\u0018"+
		"\u0002\u0019\u0007\u0019\u0002\u001a\u0007\u001a\u0002\u001b\u0007\u001b"+
		"\u0002\u001c\u0007\u001c\u0002\u001d\u0007\u001d\u0001\u0000\u0001\u0000"+
		"\u0005\u0000?\b\u0000\n\u0000\f\u0000B\t\u0000\u0001\u0000\u0001\u0000"+
		"\u0001\u0001\u0001\u0001\u0003\u0001H\b\u0001\u0001\u0001\u0001\u0001"+
		"\u0001\u0002\u0001\u0002\u0001\u0002\u0001\u0002\u0005\u0002P\b\u0002"+
		"\n\u0002\f\u0002S\t\u0002\u0001\u0002\u0003\u0002V\b\u0002\u0001\u0002"+
		"\u0001\u0002\u0001\u0003\u0001\u0003\u0001\u0004\u0001\u0004\u0003\u0004"+
		"^\b\u0004\u0001\u0004\u0001\u0004\u0001\u0005\u0001\u0005\u0001\u0005"+
		"\u0001\u0005\u0005\u0005f\b\u0005\n\u0005\f\u0005i\t\u0005\u0001\u0005"+
		"\u0003\u0005l\b\u0005\u0001\u0005\u0001\u0005\u0001\u0006\u0001\u0006"+
		"\u0003\u0006r\b\u0006\u0001\u0007\u0004\u0007u\b\u0007\u000b\u0007\f\u0007"+
		"v\u0001\b\u0001\b\u0001\b\u0001\t\u0001\t\u0001\t\u0001\t\u0001\n\u0001"+
		"\n\u0001\n\u0001\n\u0001\n\u0003\n\u0085\b\n\u0001\u000b\u0001\u000b\u0005"+
		"\u000b\u0089\b\u000b\n\u000b\f\u000b\u008c\t\u000b\u0001\u000b\u0001\u000b"+
		"\u0001\f\u0001\f\u0001\f\u0001\r\u0001\r\u0001\r\u0001\r\u0003\r\u0097"+
		"\b\r\u0001\r\u0001\r\u0001\r\u0001\u000e\u0001\u000e\u0001\u000e\u0003"+
		"\u000e\u009f\b\u000e\u0001\u000e\u0001\u000e\u0003\u000e\u00a3\b\u000e"+
		"\u0001\u000e\u0003\u000e\u00a6\b\u000e\u0003\u000e\u00a8\b\u000e\u0001"+
		"\u000f\u0001\u000f\u0001\u000f\u0001\u000f\u0005\u000f\u00ae\b\u000f\n"+
		"\u000f\f\u000f\u00b1\t\u000f\u0001\u000f\u0003\u000f\u00b4\b\u000f\u0001"+
		"\u000f\u0001\u000f\u0001\u0010\u0001\u0010\u0001\u0010\u0003\u0010\u00bb"+
		"\b\u0010\u0001\u0010\u0003\u0010\u00be\b\u0010\u0001\u0010\u0001\u0010"+
		"\u0001\u0010\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0005\u0011\u00cc\b\u0011"+
		"\n\u0011\f\u0011\u00cf\t\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001"+
		"\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001"+
		"\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001"+
		"\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001"+
		"\u0011\u0001\u0011\u0003\u0011\u00e8\b\u0011\u0001\u0011\u0001\u0011\u0003"+
		"\u0011\u00ec\b\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0003"+
		"\u0011\u00f2\b\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001"+
		"\u0011\u0003\u0011\u00f9\b\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001"+
		"\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0005\u0011\u0102\b\u0011\n"+
		"\u0011\f\u0011\u0105\t\u0011\u0001\u0011\u0003\u0011\u0108\b\u0011\u0001"+
		"\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001"+
		"\u0011\u0001\u0011\u0004\u0011\u0112\b\u0011\u000b\u0011\f\u0011\u0113"+
		"\u0003\u0011\u0116\b\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011\u0001\u0011"+
		"\u0001\u0011\u0001\u0011\u0005\u0011\u0148\b\u0011\n\u0011\f\u0011\u014b"+
		"\t\u0011\u0001\u0012\u0001\u0012\u0001\u0012\u0003\u0012\u0150\b\u0012"+
		"\u0001\u0013\u0003\u0013\u0153\b\u0013\u0001\u0013\u0001\u0013\u0001\u0013"+
		"\u0003\u0013\u0158\b\u0013\u0001\u0013\u0001\u0013\u0003\u0013\u015c\b"+
		"\u0013\u0001\u0013\u0001\u0013\u0003\u0013\u0160\b\u0013\u0001\u0013\u0001"+
		"\u0013\u0003\u0013\u0164\b\u0013\u0001\u0013\u0003\u0013\u0167\b\u0013"+
		"\u0001\u0014\u0001\u0014\u0001\u0014\u0001\u0015\u0001\u0015\u0001\u0015"+
		"\u0001\u0016\u0001\u0016\u0001\u0016\u0003\u0016\u0172\b\u0016\u0001\u0016"+
		"\u0005\u0016\u0175\b\u0016\n\u0016\f\u0016\u0178\t\u0016\u0001\u0016\u0003"+
		"\u0016\u017b\b\u0016\u0001\u0017\u0001\u0017\u0001\u0017\u0003\u0017\u0180"+
		"\b\u0017\u0001\u0017\u0003\u0017\u0183\b\u0017\u0001\u0017\u0005\u0017"+
		"\u0186\b\u0017\n\u0017\f\u0017\u0189\t\u0017\u0001\u0017\u0003\u0017\u018c"+
		"\b\u0017\u0001\u0018\u0001\u0018\u0001\u0018\u0001\u0018\u0001\u0018\u0003"+
		"\u0018\u0193\b\u0018\u0001\u0019\u0001\u0019\u0001\u0019\u0001\u0019\u0005"+
		"\u0019\u0199\b\u0019\n\u0019\f\u0019\u019c\t\u0019\u0001\u001a\u0001\u001a"+
		"\u0001\u001a\u0003\u001a\u01a1\b\u001a\u0001\u001b\u0001\u001b\u0001\u001b"+
		"\u0003\u001b\u01a6\b\u001b\u0001\u001c\u0001\u001c\u0001\u001c\u0001\u001c"+
		"\u0001\u001c\u0003\u001c\u01ad\b\u001c\u0001\u001d\u0001\u001d\u0005\u001d"+
		"\u01b1\b\u001d\n\u001d\f\u001d\u01b4\t\u001d\u0001\u001d\u0005\u001d\u01b7"+
		"\b\u001d\n\u001d\f\u001d\u01ba\t\u001d\u0001\u001d\u0001\u001d\u0001\u001d"+
		"\u0000\u0001\"\u001e\u0000\u0002\u0004\u0006\b\n\f\u000e\u0010\u0012\u0014"+
		"\u0016\u0018\u001a\u001c\u001e \"$&(*,.02468:\u0000\u0006\u0001\u0000"+
		"\u000b\f\u0001\u0000\r\u000f\u0001\u000067\u0002\u0000\b\t23\u0001\u0000"+
		"45\u0001\u0000/0\u01f2\u0000@\u0001\u0000\u0000\u0000\u0002G\u0001\u0000"+
		"\u0000\u0000\u0004K\u0001\u0000\u0000\u0000\u0006Y\u0001\u0000\u0000\u0000"+
		"\b]\u0001\u0000\u0000\u0000\na\u0001\u0000\u0000\u0000\fo\u0001\u0000"+
		"\u0000\u0000\u000et\u0001\u0000\u0000\u0000\u0010x\u0001\u0000\u0000\u0000"+
		"\u0012{\u0001\u0000\u0000\u0000\u0014\u0084\u0001\u0000\u0000\u0000\u0016"+
		"\u0086\u0001\u0000\u0000\u0000\u0018\u008f\u0001\u0000\u0000\u0000\u001a"+
		"\u0092\u0001\u0000\u0000\u0000\u001c\u00a7\u0001\u0000\u0000\u0000\u001e"+
		"\u00a9\u0001\u0000\u0000\u0000 \u00bd\u0001\u0000\u0000\u0000\"\u0115"+
		"\u0001\u0000\u0000\u0000$\u014c\u0001\u0000\u0000\u0000&\u0152\u0001\u0000"+
		"\u0000\u0000(\u0168\u0001\u0000\u0000\u0000*\u016b\u0001\u0000\u0000\u0000"+
		",\u016e\u0001\u0000\u0000\u0000.\u017c\u0001\u0000\u0000\u00000\u018d"+
		"\u0001\u0000\u0000\u00002\u0194\u0001\u0000\u0000\u00004\u019d\u0001\u0000"+
		"\u0000\u00006\u01a2\u0001\u0000\u0000\u00008\u01ac\u0001\u0000\u0000\u0000"+
		":\u01ae\u0001\u0000\u0000\u0000<=\u0005:\u0000\u0000=?\u00051\u0000\u0000"+
		"><\u0001\u0000\u0000\u0000?B\u0001\u0000\u0000\u0000@>\u0001\u0000\u0000"+
		"\u0000@A\u0001\u0000\u0000\u0000AC\u0001\u0000\u0000\u0000B@\u0001\u0000"+
		"\u0000\u0000CD\u0005:\u0000\u0000D\u0001\u0001\u0000\u0000\u0000EF\u0005"+
		":\u0000\u0000FH\u0005\u0001\u0000\u0000GE\u0001\u0000\u0000\u0000GH\u0001"+
		"\u0000\u0000\u0000HI\u0001\u0000\u0000\u0000IJ\u0003\"\u0011\u0000J\u0003"+
		"\u0001\u0000\u0000\u0000KQ\u0005\u0002\u0000\u0000LM\u0003\u0002\u0001"+
		"\u0000MN\u0005\u0003\u0000\u0000NP\u0001\u0000\u0000\u0000OL\u0001\u0000"+
		"\u0000\u0000PS\u0001\u0000\u0000\u0000QO\u0001\u0000\u0000\u0000QR\u0001"+
		"\u0000\u0000\u0000RU\u0001\u0000\u0000\u0000SQ\u0001\u0000\u0000\u0000"+
		"TV\u0003\u0002\u0001\u0000UT\u0001\u0000\u0000\u0000UV\u0001\u0000\u0000"+
		"\u0000VW\u0001\u0000\u0000\u0000WX\u0005\u0004\u0000\u0000X\u0005\u0001"+
		"\u0000\u0000\u0000YZ\u0003\u0000\u0000\u0000Z\u0007\u0001\u0000\u0000"+
		"\u0000[\\\u0005:\u0000\u0000\\^\u0005\u0005\u0000\u0000][\u0001\u0000"+
		"\u0000\u0000]^\u0001\u0000\u0000\u0000^_\u0001\u0000\u0000\u0000_`\u0003"+
		"\u0014\n\u0000`\t\u0001\u0000\u0000\u0000ag\u0005\u0002\u0000\u0000bc"+
		"\u0003\b\u0004\u0000cd\u0005\u0003\u0000\u0000df\u0001\u0000\u0000\u0000"+
		"eb\u0001\u0000\u0000\u0000fi\u0001\u0000\u0000\u0000ge\u0001\u0000\u0000"+
		"\u0000gh\u0001\u0000\u0000\u0000hk\u0001\u0000\u0000\u0000ig\u0001\u0000"+
		"\u0000\u0000jl\u0003\b\u0004\u0000kj\u0001\u0000\u0000\u0000kl\u0001\u0000"+
		"\u0000\u0000lm\u0001\u0000\u0000\u0000mn\u0005\u0004\u0000\u0000n\u000b"+
		"\u0001\u0000\u0000\u0000oq\u00059\u0000\u0000pr\u0003\n\u0005\u0000qp"+
		"\u0001\u0000\u0000\u0000qr\u0001\u0000\u0000\u0000r\r\u0001\u0000\u0000"+
		"\u0000su\u0003\f\u0006\u0000ts\u0001\u0000\u0000\u0000uv\u0001\u0000\u0000"+
		"\u0000vt\u0001\u0000\u0000\u0000vw\u0001\u0000\u0000\u0000w\u000f\u0001"+
		"\u0000\u0000\u0000xy\u0005\u0016\u0000\u0000yz\u0005:\u0000\u0000z\u0011"+
		"\u0001\u0000\u0000\u0000{|\u0003\n\u0005\u0000|}\u0005\u0005\u0000\u0000"+
		"}~\u0003\u0014\n\u0000~\u0013\u0001\u0000\u0000\u0000\u007f\u0085\u0003"+
		"\u0006\u0003\u0000\u0080\u0085\u0003\u0010\b\u0000\u0081\u0085\u0003\n"+
		"\u0005\u0000\u0082\u0085\u0003\u000e\u0007\u0000\u0083\u0085\u0003\u0012"+
		"\t\u0000\u0084\u007f\u0001\u0000\u0000\u0000\u0084\u0080\u0001\u0000\u0000"+
		"\u0000\u0084\u0081\u0001\u0000\u0000\u0000\u0084\u0082\u0001\u0000\u0000"+
		"\u0000\u0084\u0083\u0001\u0000\u0000\u0000\u0085\u0015\u0001\u0000\u0000"+
		"\u0000\u0086\u008a\u0005\u0006\u0000\u0000\u0087\u0089\u0005:\u0000\u0000"+
		"\u0088\u0087\u0001\u0000\u0000\u0000\u0089\u008c\u0001\u0000\u0000\u0000"+
		"\u008a\u0088\u0001\u0000\u0000\u0000\u008a\u008b\u0001\u0000\u0000\u0000"+
		"\u008b\u008d\u0001\u0000\u0000\u0000\u008c\u008a\u0001\u0000\u0000\u0000"+
		"\u008d\u008e\u0005\u0007\u0000\u0000\u008e\u0017\u0001\u0000\u0000\u0000"+
		"\u008f\u0090\u0005\u0001\u0000\u0000\u0090\u0091\u0003\"\u0011\u0000\u0091"+
		"\u0019\u0001\u0000\u0000\u0000\u0092\u0096\u0005\u0006\u0000\u0000\u0093"+
		"\u0094\u0003\"\u0011\u0000\u0094\u0095\u00052\u0000\u0000\u0095\u0097"+
		"\u0001\u0000\u0000\u0000\u0096\u0093\u0001\u0000\u0000\u0000\u0096\u0097"+
		"\u0001\u0000\u0000\u0000\u0097\u0098\u0001\u0000\u0000\u0000\u0098\u0099"+
		"\u0005;\u0000\u0000\u0099\u009a\u0005\u0007\u0000\u0000\u009a\u001b\u0001"+
		"\u0000\u0000\u0000\u009b\u00a8\u0003\u001e\u000f\u0000\u009c\u009e\u0005"+
		":\u0000\u0000\u009d\u009f\u0003\u001a\r\u0000\u009e\u009d\u0001\u0000"+
		"\u0000\u0000\u009e\u009f\u0001\u0000\u0000\u0000\u009f\u00a2\u0001\u0000"+
		"\u0000\u0000\u00a0\u00a1\u0005\u0005\u0000\u0000\u00a1\u00a3\u0003\u0014"+
		"\n\u0000\u00a2\u00a0\u0001\u0000\u0000\u0000\u00a2\u00a3\u0001\u0000\u0000"+
		"\u0000\u00a3\u00a5\u0001\u0000\u0000\u0000\u00a4\u00a6\u0003\u0018\f\u0000"+
		"\u00a5\u00a4\u0001\u0000\u0000\u0000\u00a5\u00a6\u0001\u0000\u0000\u0000"+
		"\u00a6\u00a8\u0001\u0000\u0000\u0000\u00a7\u009b\u0001\u0000\u0000\u0000"+
		"\u00a7\u009c\u0001\u0000\u0000\u0000\u00a8\u001d\u0001\u0000\u0000\u0000"+
		"\u00a9\u00af\u0005\u0002\u0000\u0000\u00aa\u00ab\u0003\u001c\u000e\u0000"+
		"\u00ab\u00ac\u0005\u0003\u0000\u0000\u00ac\u00ae\u0001\u0000\u0000\u0000"+
		"\u00ad\u00aa\u0001\u0000\u0000\u0000\u00ae\u00b1\u0001\u0000\u0000\u0000"+
		"\u00af\u00ad\u0001\u0000\u0000\u0000\u00af\u00b0\u0001\u0000\u0000\u0000"+
		"\u00b0\u00b3\u0001\u0000\u0000\u0000\u00b1\u00af\u0001\u0000\u0000\u0000"+
		"\u00b2\u00b4\u0003\u001c\u000e\u0000\u00b3\u00b2\u0001\u0000\u0000\u0000"+
		"\u00b3\u00b4\u0001\u0000\u0000\u0000\u00b4\u00b5\u0001\u0000\u0000\u0000"+
		"\u00b5\u00b6\u0005\u0004\u0000\u0000\u00b6\u001f\u0001\u0000\u0000\u0000"+
		"\u00b7\u00b8\u0005\u001e\u0000\u0000\u00b8\u00ba\u0005:\u0000\u0000\u00b9"+
		"\u00bb\u0003\u001e\u000f\u0000\u00ba\u00b9\u0001\u0000\u0000\u0000\u00ba"+
		"\u00bb\u0001\u0000\u0000\u0000\u00bb\u00be\u0001\u0000\u0000\u0000\u00bc"+
		"\u00be\u0005\u001f\u0000\u0000\u00bd\u00b7\u0001\u0000\u0000\u0000\u00bd"+
		"\u00bc\u0001\u0000\u0000\u0000\u00be\u00bf\u0001\u0000\u0000\u0000\u00bf"+
		"\u00c0\u0005.\u0000\u0000\u00c0\u00c1\u0003\"\u0011\u0000\u00c1!\u0001"+
		"\u0000\u0000\u0000\u00c2\u00c3\u0006\u0011\uffff\uffff\u0000\u00c3\u00c4"+
		"\u0005\u0015\u0000\u0000\u00c4\u00c5\u0005\b\u0000\u0000\u00c5\u00c6\u0003"+
		"\u0014\n\u0000\u00c6\u00c7\u0005\t\u0000\u0000\u00c7\u00c8\u0005\u0002"+
		"\u0000\u0000\u00c8\u00cd\u0005<\u0000\u0000\u00c9\u00ca\u0005\u0003\u0000"+
		"\u0000\u00ca\u00cc\u0003\"\u0011\u0000\u00cb\u00c9\u0001\u0000\u0000\u0000"+
		"\u00cc\u00cf\u0001\u0000\u0000\u0000\u00cd\u00cb\u0001\u0000\u0000\u0000"+
		"\u00cd\u00ce\u0001\u0000\u0000\u0000\u00ce\u00d0\u0001\u0000\u0000\u0000"+
		"\u00cf\u00cd\u0001\u0000\u0000\u0000\u00d0\u00d1\u0005\u0004\u0000\u0000"+
		"\u00d1\u0116\u0001\u0000\u0000\u0000\u00d2\u00d3\u0005\u0017\u0000\u0000"+
		"\u00d3\u00d4\u0005\u0002\u0000\u0000\u00d4\u00d5\u0003\"\u0011\u0000\u00d5"+
		"\u00d6\u0005\u0003\u0000\u0000\u00d6\u00d7\u0003\"\u0011\u0000\u00d7\u00d8"+
		"\u0005\u0003\u0000\u0000\u00d8\u00d9\u0005<\u0000\u0000\u00d9\u00da\u0005"+
		"\u0004\u0000\u0000\u00da\u0116\u0001\u0000\u0000\u0000\u00db\u00dc\u0005"+
		"\u0018\u0000\u0000\u00dc\u00dd\u0005\u0002\u0000\u0000\u00dd\u00de\u0003"+
		"\"\u0011\u0000\u00de\u00df\u0005\u0004\u0000\u0000\u00df\u0116\u0001\u0000"+
		"\u0000\u0000\u00e0\u00e1\u0005\u0019\u0000\u0000\u00e1\u0116\u0003\u0004"+
		"\u0002\u0000\u00e2\u00e3\u0007\u0000\u0000\u0000\u00e3\u0116\u0003\"\u0011"+
		"\u0015\u00e4\u0116\u0003\u0004\u0002\u0000\u00e5\u00e7\u00059\u0000\u0000"+
		"\u00e6\u00e8\u0003\u0004\u0002\u0000\u00e7\u00e6\u0001\u0000\u0000\u0000"+
		"\u00e7\u00e8\u0001\u0000\u0000\u0000\u00e8\u0116\u0001\u0000\u0000\u0000"+
		"\u00e9\u00eb\u0003$\u0012\u0000\u00ea\u00ec\u0005\u0014\u0000\u0000\u00eb"+
		"\u00ea\u0001\u0000\u0000\u0000\u00eb\u00ec\u0001\u0000\u0000\u0000\u00ec"+
		"\u00ed\u0001\u0000\u0000\u0000\u00ed\u00ee\u0003\"\u0011\b\u00ee\u0116"+
		"\u0001\u0000\u0000\u0000\u00ef\u00f1\u0003(\u0014\u0000\u00f0\u00f2\u0005"+
		"\u0014\u0000\u0000\u00f1\u00f0\u0001\u0000\u0000\u0000\u00f1\u00f2\u0001"+
		"\u0000\u0000\u0000\u00f2\u00f3\u0001\u0000\u0000\u0000\u00f3\u00f4\u0003"+
		"\"\u0011\u0007\u00f4\u0116\u0001\u0000\u0000\u0000\u00f5\u00f8\u0003\u001e"+
		"\u000f\u0000\u00f6\u00f7\u0005\u0005\u0000\u0000\u00f7\u00f9\u0003\u0014"+
		"\n\u0000\u00f8\u00f6\u0001\u0000\u0000\u0000\u00f8\u00f9\u0001\u0000\u0000"+
		"\u0000\u00f9\u00fa\u0001\u0000\u0000\u0000\u00fa\u00fb\u0005.\u0000\u0000"+
		"\u00fb\u00fc\u0003\"\u0011\u0006\u00fc\u0116\u0001\u0000\u0000\u0000\u00fd"+
		"\u00fe\u0005\u0006\u0000\u0000\u00fe\u0103\u0003\"\u0011\u0000\u00ff\u0100"+
		"\u0005\u0003\u0000\u0000\u0100\u0102\u0003\"\u0011\u0000\u0101\u00ff\u0001"+
		"\u0000\u0000\u0000\u0102\u0105\u0001\u0000\u0000\u0000\u0103\u0101\u0001"+
		"\u0000\u0000\u0000\u0103\u0104\u0001\u0000\u0000\u0000\u0104\u0107\u0001"+
		"\u0000\u0000\u0000\u0105\u0103\u0001\u0000\u0000\u0000\u0106\u0108\u0005"+
		"\u0003\u0000\u0000\u0107\u0106\u0001\u0000\u0000\u0000\u0107\u0108\u0001"+
		"\u0000\u0000\u0000\u0108\u0109\u0001\u0000\u0000\u0000\u0109\u010a\u0005"+
		"\u0007\u0000\u0000\u010a\u0116\u0001\u0000\u0000\u0000\u010b\u0116\u0005"+
		"<\u0000\u0000\u010c\u0116\u0005;\u0000\u0000\u010d\u0116\u0003\u0000\u0000"+
		"\u0000\u010e\u010f\u0005\u001d\u0000\u0000\u010f\u0111\u0003\"\u0011\u0000"+
		"\u0110\u0112\u0003 \u0010\u0000\u0111\u0110\u0001\u0000\u0000\u0000\u0112"+
		"\u0113\u0001\u0000\u0000\u0000\u0113\u0111\u0001\u0000\u0000\u0000\u0113"+
		"\u0114\u0001\u0000\u0000\u0000\u0114\u0116\u0001\u0000\u0000\u0000\u0115"+
		"\u00c2\u0001\u0000\u0000\u0000\u0115\u00d2\u0001\u0000\u0000\u0000\u0115"+
		"\u00db\u0001\u0000\u0000\u0000\u0115\u00e0\u0001\u0000\u0000\u0000\u0115"+
		"\u00e2\u0001\u0000\u0000\u0000\u0115\u00e4\u0001\u0000\u0000\u0000\u0115"+
		"\u00e5\u0001\u0000\u0000\u0000\u0115\u00e9\u0001\u0000\u0000\u0000\u0115"+
		"\u00ef\u0001\u0000\u0000\u0000\u0115\u00f5\u0001\u0000\u0000\u0000\u0115"+
		"\u00fd\u0001\u0000\u0000\u0000\u0115\u010b\u0001\u0000\u0000\u0000\u0115"+
		"\u010c\u0001\u0000\u0000\u0000\u0115\u010d\u0001\u0000\u0000\u0000\u0115"+
		"\u010e\u0001\u0000\u0000\u0000\u0116\u0149\u0001\u0000\u0000\u0000\u0117"+
		"\u0118\n\u0014\u0000\u0000\u0118\u0119\u00058\u0000\u0000\u0119\u0148"+
		"\u0003\"\u0011\u0015\u011a\u011b\n\u0013\u0000\u0000\u011b\u011c\u0007"+
		"\u0001\u0000\u0000\u011c\u0148\u0003\"\u0011\u0014\u011d\u011e\n\u0012"+
		"\u0000\u0000\u011e\u011f\u0007\u0000\u0000\u0000\u011f\u0148\u0003\"\u0011"+
		"\u0013\u0120\u0121\n\u0011\u0000\u0000\u0121\u0122\u0007\u0002\u0000\u0000"+
		"\u0122\u0148\u0003\"\u0011\u0012\u0123\u0124\n\u0010\u0000\u0000\u0124"+
		"\u0125\u0007\u0003\u0000\u0000\u0125\u0148\u0003\"\u0011\u0011\u0126\u0127"+
		"\n\u000f\u0000\u0000\u0127\u0128\u0007\u0004\u0000\u0000\u0128\u0148\u0003"+
		"\"\u0011\u0010\u0129\u012a\n\u000e\u0000\u0000\u012a\u012b\u0005\u0010"+
		"\u0000\u0000\u012b\u0148\u0003\"\u0011\u000f\u012c\u012d\n\r\u0000\u0000"+
		"\u012d\u012e\u0005\u0011\u0000\u0000\u012e\u0148\u0003\"\u0011\u000e\u012f"+
		"\u0130\n\f\u0000\u0000\u0130\u0131\u0005\u0012\u0000\u0000\u0131\u0148"+
		"\u0003\"\u0011\r\u0132\u0133\n\u001a\u0000\u0000\u0133\u0134\u0005\n\u0000"+
		"\u0000\u0134\u0148\u0005:\u0000\u0000\u0135\u0136\n\u0019\u0000\u0000"+
		"\u0136\u0148\u0003\u0004\u0002\u0000\u0137\u0138\n\u0017\u0000\u0000\u0138"+
		"\u0139\u0005\u0006\u0000\u0000\u0139\u013a\u0003\"\u0011\u0000\u013a\u013b"+
		"\u0005\u0007\u0000\u0000\u013b\u0148\u0001\u0000\u0000\u0000\u013c\u013d"+
		"\n\u0016\u0000\u0000\u013d\u013e\u0007\u0005\u0000\u0000\u013e\u013f\u0003"+
		"\"\u0011\u0000\u013f\u0140\u0003\u0004\u0002\u0000\u0140\u0148\u0001\u0000"+
		"\u0000\u0000\u0141\u0142\n\u000b\u0000\u0000\u0142\u0143\u0005\u0013\u0000"+
		"\u0000\u0143\u0144\u0003\"\u0011\u0000\u0144\u0145\u0005\u0005\u0000\u0000"+
		"\u0145\u0146\u0003\"\u0011\u0000\u0146\u0148\u0001\u0000\u0000\u0000\u0147"+
		"\u0117\u0001\u0000\u0000\u0000\u0147\u011a\u0001\u0000\u0000\u0000\u0147"+
		"\u011d\u0001\u0000\u0000\u0000\u0147\u0120\u0001\u0000\u0000\u0000\u0147"+
		"\u0123\u0001\u0000\u0000\u0000\u0147\u0126\u0001\u0000\u0000\u0000\u0147"+
		"\u0129\u0001\u0000\u0000\u0000\u0147\u012c\u0001\u0000\u0000\u0000\u0147"+
		"\u012f\u0001\u0000\u0000\u0000\u0147\u0132\u0001\u0000\u0000\u0000\u0147"+
		"\u0135\u0001\u0000\u0000\u0000\u0147\u0137\u0001\u0000\u0000\u0000\u0147"+
		"\u013c\u0001\u0000\u0000\u0000\u0147\u0141\u0001\u0000\u0000\u0000\u0148"+
		"\u014b\u0001\u0000\u0000\u0000\u0149\u0147\u0001\u0000\u0000\u0000\u0149"+
		"\u014a\u0001\u0000\u0000\u0000\u014a#\u0001\u0000\u0000\u0000\u014b\u0149"+
		"\u0001\u0000\u0000\u0000\u014c\u014d\u0005$\u0000\u0000\u014d\u014f\u0003"+
		"\u001c\u000e\u0000\u014e\u0150\u0005\u0014\u0000\u0000\u014f\u014e\u0001"+
		"\u0000\u0000\u0000\u014f\u0150\u0001\u0000\u0000\u0000\u0150%\u0001\u0000"+
		"\u0000\u0000\u0151\u0153\u0003\u0016\u000b\u0000\u0152\u0151\u0001\u0000"+
		"\u0000\u0000\u0152\u0153\u0001\u0000\u0000\u0000\u0153\u0157\u0001\u0000"+
		"\u0000\u0000\u0154\u0155\u0003\u0006\u0003\u0000\u0155\u0156\u0005\n\u0000"+
		"\u0000\u0156\u0158\u0001\u0000\u0000\u0000\u0157\u0154\u0001\u0000\u0000"+
		"\u0000\u0157\u0158\u0001\u0000\u0000\u0000\u0158\u0159\u0001\u0000\u0000"+
		"\u0000\u0159\u015b\u0005:\u0000\u0000\u015a\u015c\u0003\u001e\u000f\u0000"+
		"\u015b\u015a\u0001\u0000\u0000\u0000\u015b\u015c\u0001\u0000\u0000\u0000"+
		"\u015c\u015f\u0001\u0000\u0000\u0000\u015d\u015e\u0005\u0005\u0000\u0000"+
		"\u015e\u0160\u0003\u0014\n\u0000\u015f\u015d\u0001\u0000\u0000\u0000\u015f"+
		"\u0160\u0001\u0000\u0000\u0000\u0160\u0163\u0001\u0000\u0000\u0000\u0161"+
		"\u0162\u0005.\u0000\u0000\u0162\u0164\u0003\"\u0011\u0000\u0163\u0161"+
		"\u0001\u0000\u0000\u0000\u0163\u0164\u0001\u0000\u0000\u0000\u0164\u0166"+
		"\u0001\u0000\u0000\u0000\u0165\u0167\u0005\u0014\u0000\u0000\u0166\u0165"+
		"\u0001\u0000\u0000\u0000\u0166\u0167\u0001\u0000\u0000\u0000\u0167\'\u0001"+
		"\u0000\u0000\u0000\u0168\u0169\u0005\"\u0000\u0000\u0169\u016a\u0003&"+
		"\u0013\u0000\u016a)\u0001\u0000\u0000\u0000\u016b\u016c\u0005#\u0000\u0000"+
		"\u016c\u016d\u0003&\u0013\u0000\u016d+\u0001\u0000\u0000\u0000\u016e\u016f"+
		"\u0005&\u0000\u0000\u016f\u0171\u0005:\u0000\u0000\u0170\u0172\u00032"+
		"\u0019\u0000\u0171\u0170\u0001\u0000\u0000\u0000\u0171\u0172\u0001\u0000"+
		"\u0000\u0000\u0172\u0176\u0001\u0000\u0000\u0000\u0173\u0175\u0003*\u0015"+
		"\u0000\u0174\u0173\u0001\u0000\u0000\u0000\u0175\u0178\u0001\u0000\u0000"+
		"\u0000\u0176\u0174\u0001\u0000\u0000\u0000\u0176\u0177\u0001\u0000\u0000"+
		"\u0000\u0177\u017a\u0001\u0000\u0000\u0000\u0178\u0176\u0001\u0000\u0000"+
		"\u0000\u0179\u017b\u0005\u0014\u0000\u0000\u017a\u0179\u0001\u0000\u0000"+
		"\u0000\u017a\u017b\u0001\u0000\u0000\u0000\u017b-\u0001\u0000\u0000\u0000"+
		"\u017c\u017d\u0005)\u0000\u0000\u017d\u017f\u0005:\u0000\u0000\u017e\u0180"+
		"\u0003\u001e\u000f\u0000\u017f\u017e\u0001\u0000\u0000\u0000\u017f\u0180"+
		"\u0001\u0000\u0000\u0000\u0180\u0182\u0001\u0000\u0000\u0000\u0181\u0183"+
		"\u00032\u0019\u0000\u0182\u0181\u0001\u0000\u0000\u0000\u0182\u0183\u0001"+
		"\u0000\u0000\u0000\u0183\u0187\u0001\u0000\u0000\u0000\u0184\u0186\u0003"+
		"*\u0015\u0000\u0185\u0184\u0001\u0000\u0000\u0000\u0186\u0189\u0001\u0000"+
		"\u0000\u0000\u0187\u0185\u0001\u0000\u0000\u0000\u0187\u0188\u0001\u0000"+
		"\u0000\u0000\u0188\u018b\u0001\u0000\u0000\u0000\u0189\u0187\u0001\u0000"+
		"\u0000\u0000\u018a\u018c\u0005\u0014\u0000\u0000\u018b\u018a\u0001\u0000"+
		"\u0000\u0000\u018b\u018c\u0001\u0000\u0000\u0000\u018c/\u0001\u0000\u0000"+
		"\u0000\u018d\u018e\u0005\u001c\u0000\u0000\u018e\u018f\u0005:\u0000\u0000"+
		"\u018f\u0190\u0005\u0005\u0000\u0000\u0190\u0192\u0003\u0014\n\u0000\u0191"+
		"\u0193\u0005\u0014\u0000\u0000\u0192\u0191\u0001\u0000\u0000\u0000\u0192"+
		"\u0193\u0001\u0000\u0000\u0000\u01931\u0001\u0000\u0000\u0000\u0194\u0195"+
		"\u0005\u0005\u0000\u0000\u0195\u019a\u0003\u0006\u0003\u0000\u0196\u0197"+
		"\u0005\u0003\u0000\u0000\u0197\u0199\u0003\u0006\u0003\u0000\u0198\u0196"+
		"\u0001\u0000\u0000\u0000\u0199\u019c\u0001\u0000\u0000\u0000\u019a\u0198"+
		"\u0001\u0000\u0000\u0000\u019a\u019b\u0001\u0000\u0000\u0000\u019b3\u0001"+
		"\u0000\u0000\u0000\u019c\u019a\u0001\u0000\u0000\u0000\u019d\u019e\u0005"+
		"\u001a\u0000\u0000\u019e\u01a0\u0003\u0006\u0003\u0000\u019f\u01a1\u0005"+
		"\u0014\u0000\u0000\u01a0\u019f\u0001\u0000\u0000\u0000\u01a0\u01a1\u0001"+
		"\u0000\u0000\u0000\u01a15\u0001\u0000\u0000\u0000\u01a2\u01a3\u0005\u001b"+
		"\u0000\u0000\u01a3\u01a5\u0003\u0006\u0003\u0000\u01a4\u01a6\u0005\u0014"+
		"\u0000\u0000\u01a5\u01a4\u0001\u0000\u0000\u0000\u01a5\u01a6\u0001\u0000"+
		"\u0000\u0000\u01a67\u0001\u0000\u0000\u0000\u01a7\u01ad\u0003$\u0012\u0000"+
		"\u01a8\u01ad\u0003(\u0014\u0000\u01a9\u01ad\u0003,\u0016\u0000\u01aa\u01ad"+
		"\u0003.\u0017\u0000\u01ab\u01ad\u00030\u0018\u0000\u01ac\u01a7\u0001\u0000"+
		"\u0000\u0000\u01ac\u01a8\u0001\u0000\u0000\u0000\u01ac\u01a9\u0001\u0000"+
		"\u0000\u0000\u01ac\u01aa\u0001\u0000\u0000\u0000\u01ac\u01ab\u0001\u0000"+
		"\u0000\u0000\u01ad9\u0001\u0000\u0000\u0000\u01ae\u01b2\u00034\u001a\u0000"+
		"\u01af\u01b1\u00036\u001b\u0000\u01b0\u01af\u0001\u0000\u0000\u0000\u01b1"+
		"\u01b4\u0001\u0000\u0000\u0000\u01b2\u01b0\u0001\u0000\u0000\u0000\u01b2"+
		"\u01b3\u0001\u0000\u0000\u0000\u01b3\u01b8\u0001\u0000\u0000\u0000\u01b4"+
		"\u01b2\u0001\u0000\u0000\u0000\u01b5\u01b7\u00038\u001c\u0000\u01b6\u01b5"+
		"\u0001\u0000\u0000\u0000\u01b7\u01ba\u0001\u0000\u0000\u0000\u01b8\u01b6"+
		"\u0001\u0000\u0000\u0000\u01b8\u01b9\u0001\u0000\u0000\u0000\u01b9\u01bb"+
		"\u0001\u0000\u0000\u0000\u01ba\u01b8\u0001\u0000\u0000\u0000\u01bb\u01bc"+
		"\u0005\u0000\u0000\u0001\u01bc;\u0001\u0000\u0000\u00004@GQU]gkqv\u0084"+
		"\u008a\u0096\u009e\u00a2\u00a5\u00a7\u00af\u00b3\u00ba\u00bd\u00cd\u00e7"+
		"\u00eb\u00f1\u00f8\u0103\u0107\u0113\u0115\u0147\u0149\u014f\u0152\u0157"+
		"\u015b\u015f\u0163\u0166\u0171\u0176\u017a\u017f\u0182\u0187\u018b\u0192"+
		"\u019a\u01a0\u01a5\u01ac\u01b2\u01b8";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}