// Generated from /Users/mbrown/Projects/my/yafl/compiler/src/yafl.g4 by ANTLR 4.9.2
import org.antlr.v4.runtime.atn.*;
import org.antlr.v4.runtime.dfa.DFA;
import org.antlr.v4.runtime.*;
import org.antlr.v4.runtime.misc.*;
import org.antlr.v4.runtime.tree.*;
import java.util.List;
import java.util.Iterator;
import java.util.ArrayList;

@SuppressWarnings({"all", "warnings", "unchecked", "unused", "cast"})
public class yaflParser extends Parser {
	static { RuntimeMetaData.checkVersion("4.9.2", RuntimeMetaData.VERSION); }

	protected static final DFA[] _decisionToDFA;
	protected static final PredictionContextCache _sharedContextCache =
		new PredictionContextCache();
	public static final int
		T__0=1, T__1=2, T__2=3, T__3=4, T__4=5, ALIAS=6, VAR=7, FUN=8, DATA=9, 
		CLASS=10, IF=11, ELSE=12, RETURN=13, OBJECT=14, MODULE=15, IMPORT=16, 
		WHERE=17, MULTDIV=18, ADDSUB=19, COMMA=20, COLON=21, DOT=22, NAME=23, 
		WS=24, COMMENT=25, INTEGER=26, STRING=27;
	public static final int
		RULE_simpleTypeName = 0, RULE_genericParams = 1, RULE_namedType = 2, RULE_tupleType = 3, 
		RULE_type = 4, RULE_parameter = 5, RULE_whereExpr = 6, RULE_alias = 7, 
		RULE_var = 8, RULE_fun = 9, RULE_data = 10, RULE_namedParams = 11, RULE_expression = 12, 
		RULE_codeBlock = 13, RULE_statements = 14, RULE_declarations = 15, RULE_module = 16, 
		RULE_imports = 17, RULE_root = 18;
	private static String[] makeRuleNames() {
		return new String[] {
			"simpleTypeName", "genericParams", "namedType", "tupleType", "type", 
			"parameter", "whereExpr", "alias", "var", "fun", "data", "namedParams", 
			"expression", "codeBlock", "statements", "declarations", "module", "imports", 
			"root"
		};
	}
	public static final String[] ruleNames = makeRuleNames();

	private static String[] makeLiteralNames() {
		return new String[] {
			null, "'<'", "'>'", "'('", "')'", "'='", "'alias'", "'var'", null, "'data'", 
			"'class'", "'if'", "'else'", "'return'", "'object'", "'module'", "'import'", 
			"'where'", null, null, "','", "':'", "'.'"
		};
	}
	private static final String[] _LITERAL_NAMES = makeLiteralNames();
	private static String[] makeSymbolicNames() {
		return new String[] {
			null, null, null, null, null, null, "ALIAS", "VAR", "FUN", "DATA", "CLASS", 
			"IF", "ELSE", "RETURN", "OBJECT", "MODULE", "IMPORT", "WHERE", "MULTDIV", 
			"ADDSUB", "COMMA", "COLON", "DOT", "NAME", "WS", "COMMENT", "INTEGER", 
			"STRING"
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
	public String getGrammarFileName() { return "yafl.g4"; }

	@Override
	public String[] getRuleNames() { return ruleNames; }

	@Override
	public String getSerializedATN() { return _serializedATN; }

	@Override
	public ATN getATN() { return _ATN; }

	public yaflParser(TokenStream input) {
		super(input);
		_interp = new ParserATNSimulator(this,_ATN,_decisionToDFA,_sharedContextCache);
	}

	public static class SimpleTypeNameContext extends ParserRuleContext {
		public List<TerminalNode> NAME() { return getTokens(yaflParser.NAME); }
		public TerminalNode NAME(int i) {
			return getToken(yaflParser.NAME, i);
		}
		public List<TerminalNode> DOT() { return getTokens(yaflParser.DOT); }
		public TerminalNode DOT(int i) {
			return getToken(yaflParser.DOT, i);
		}
		public SimpleTypeNameContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_simpleTypeName; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterSimpleTypeName(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitSimpleTypeName(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitSimpleTypeName(this);
			else return visitor.visitChildren(this);
		}
	}

	public final SimpleTypeNameContext simpleTypeName() throws RecognitionException {
		SimpleTypeNameContext _localctx = new SimpleTypeNameContext(_ctx, getState());
		enterRule(_localctx, 0, RULE_simpleTypeName);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(38);
			match(NAME);
			setState(43);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==DOT) {
				{
				{
				setState(39);
				match(DOT);
				setState(40);
				match(NAME);
				}
				}
				setState(45);
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

	public static class GenericParamsContext extends ParserRuleContext {
		public List<NamedTypeContext> namedType() {
			return getRuleContexts(NamedTypeContext.class);
		}
		public NamedTypeContext namedType(int i) {
			return getRuleContext(NamedTypeContext.class,i);
		}
		public List<TerminalNode> COMMA() { return getTokens(yaflParser.COMMA); }
		public TerminalNode COMMA(int i) {
			return getToken(yaflParser.COMMA, i);
		}
		public GenericParamsContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_genericParams; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterGenericParams(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitGenericParams(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitGenericParams(this);
			else return visitor.visitChildren(this);
		}
	}

	public final GenericParamsContext genericParams() throws RecognitionException {
		GenericParamsContext _localctx = new GenericParamsContext(_ctx, getState());
		enterRule(_localctx, 2, RULE_genericParams);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(46);
			match(T__0);
			setState(47);
			namedType();
			setState(52);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==COMMA) {
				{
				{
				setState(48);
				match(COMMA);
				setState(49);
				namedType();
				}
				}
				setState(54);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(55);
			match(T__1);
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

	public static class NamedTypeContext extends ParserRuleContext {
		public SimpleTypeNameContext simpleTypeName() {
			return getRuleContext(SimpleTypeNameContext.class,0);
		}
		public GenericParamsContext genericParams() {
			return getRuleContext(GenericParamsContext.class,0);
		}
		public NamedTypeContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_namedType; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterNamedType(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitNamedType(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitNamedType(this);
			else return visitor.visitChildren(this);
		}
	}

	public final NamedTypeContext namedType() throws RecognitionException {
		NamedTypeContext _localctx = new NamedTypeContext(_ctx, getState());
		enterRule(_localctx, 4, RULE_namedType);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(57);
			simpleTypeName();
			setState(59);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__0) {
				{
				setState(58);
				genericParams();
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

	public static class TupleTypeContext extends ParserRuleContext {
		public List<ParameterContext> parameter() {
			return getRuleContexts(ParameterContext.class);
		}
		public ParameterContext parameter(int i) {
			return getRuleContext(ParameterContext.class,i);
		}
		public List<TerminalNode> COMMA() { return getTokens(yaflParser.COMMA); }
		public TerminalNode COMMA(int i) {
			return getToken(yaflParser.COMMA, i);
		}
		public TupleTypeContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_tupleType; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterTupleType(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitTupleType(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitTupleType(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TupleTypeContext tupleType() throws RecognitionException {
		TupleTypeContext _localctx = new TupleTypeContext(_ctx, getState());
		enterRule(_localctx, 6, RULE_tupleType);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(61);
			match(T__2);
			setState(62);
			parameter();
			setState(67);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==COMMA) {
				{
				{
				setState(63);
				match(COMMA);
				setState(64);
				parameter();
				}
				}
				setState(69);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(70);
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

	public static class TypeContext extends ParserRuleContext {
		public NamedTypeContext namedType() {
			return getRuleContext(NamedTypeContext.class,0);
		}
		public TupleTypeContext tupleType() {
			return getRuleContext(TupleTypeContext.class,0);
		}
		public TypeContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_type; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterType(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitType(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitType(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypeContext type() throws RecognitionException {
		TypeContext _localctx = new TypeContext(_ctx, getState());
		enterRule(_localctx, 8, RULE_type);
		try {
			setState(74);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case NAME:
				enterOuterAlt(_localctx, 1);
				{
				setState(72);
				namedType();
				}
				break;
			case T__2:
				enterOuterAlt(_localctx, 2);
				{
				setState(73);
				tupleType();
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

	public static class ParameterContext extends ParserRuleContext {
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TerminalNode COLON() { return getToken(yaflParser.COLON, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public ParameterContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_parameter; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterParameter(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitParameter(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitParameter(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ParameterContext parameter() throws RecognitionException {
		ParameterContext _localctx = new ParameterContext(_ctx, getState());
		enterRule(_localctx, 10, RULE_parameter);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(76);
			match(NAME);
			setState(79);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==COLON) {
				{
				setState(77);
				match(COLON);
				setState(78);
				type();
				}
			}

			setState(83);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__4) {
				{
				setState(81);
				match(T__4);
				setState(82);
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

	public static class WhereExprContext extends ParserRuleContext {
		public TerminalNode WHERE() { return getToken(yaflParser.WHERE, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public WhereExprContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_whereExpr; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterWhereExpr(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitWhereExpr(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitWhereExpr(this);
			else return visitor.visitChildren(this);
		}
	}

	public final WhereExprContext whereExpr() throws RecognitionException {
		WhereExprContext _localctx = new WhereExprContext(_ctx, getState());
		enterRule(_localctx, 12, RULE_whereExpr);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(85);
			match(WHERE);
			setState(86);
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

	public static class AliasContext extends ParserRuleContext {
		public TerminalNode ALIAS() { return getToken(yaflParser.ALIAS, 0); }
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public NamedTypeContext namedType() {
			return getRuleContext(NamedTypeContext.class,0);
		}
		public TerminalNode COLON() { return getToken(yaflParser.COLON, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public AliasContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_alias; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterAlias(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitAlias(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitAlias(this);
			else return visitor.visitChildren(this);
		}
	}

	public final AliasContext alias() throws RecognitionException {
		AliasContext _localctx = new AliasContext(_ctx, getState());
		enterRule(_localctx, 14, RULE_alias);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(88);
			match(ALIAS);
			setState(89);
			match(NAME);
			setState(90);
			namedType();
			setState(91);
			match(COLON);
			setState(92);
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

	public static class VarContext extends ParserRuleContext {
		public TerminalNode VAR() { return getToken(yaflParser.VAR, 0); }
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TerminalNode COLON() { return getToken(yaflParser.COLON, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public VarContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_var; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterVar(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitVar(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitVar(this);
			else return visitor.visitChildren(this);
		}
	}

	public final VarContext var() throws RecognitionException {
		VarContext _localctx = new VarContext(_ctx, getState());
		enterRule(_localctx, 16, RULE_var);
		try {
			setState(100);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case VAR:
				enterOuterAlt(_localctx, 1);
				{
				setState(94);
				match(VAR);
				setState(95);
				match(NAME);
				{
				setState(96);
				match(COLON);
				setState(97);
				type();
				}
				}
				break;
			case T__4:
				enterOuterAlt(_localctx, 2);
				{
				{
				setState(98);
				match(T__4);
				setState(99);
				expression(0);
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

	public static class FunContext extends ParserRuleContext {
		public TerminalNode FUN() { return getToken(yaflParser.FUN, 0); }
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TupleTypeContext tupleType() {
			return getRuleContext(TupleTypeContext.class,0);
		}
		public TerminalNode COLON() { return getToken(yaflParser.COLON, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode RETURN() { return getToken(yaflParser.RETURN, 0); }
		public WhereExprContext whereExpr() {
			return getRuleContext(WhereExprContext.class,0);
		}
		public List<StatementsContext> statements() {
			return getRuleContexts(StatementsContext.class);
		}
		public StatementsContext statements(int i) {
			return getRuleContext(StatementsContext.class,i);
		}
		public FunContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_fun; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterFun(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitFun(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitFun(this);
			else return visitor.visitChildren(this);
		}
	}

	public final FunContext fun() throws RecognitionException {
		FunContext _localctx = new FunContext(_ctx, getState());
		enterRule(_localctx, 18, RULE_fun);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(102);
			match(FUN);
			setState(103);
			match(NAME);
			setState(105);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==T__2) {
				{
				setState(104);
				tupleType();
				}
			}

			setState(109);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==COLON) {
				{
				setState(107);
				match(COLON);
				setState(108);
				type();
				}
			}

			setState(127);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,13,_ctx) ) {
			case 1:
				{
				{
				setState(111);
				match(T__4);
				setState(112);
				expression(0);
				setState(114);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==WHERE) {
					{
					setState(113);
					whereExpr();
					}
				}

				}
				}
				break;
			case 2:
				{
				{
				setState(117);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==WHERE) {
					{
					setState(116);
					whereExpr();
					}
				}

				setState(122);
				_errHandler.sync(this);
				_la = _input.LA(1);
				while ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__4) | (1L << VAR) | (1L << FUN))) != 0)) {
					{
					{
					setState(119);
					statements();
					}
					}
					setState(124);
					_errHandler.sync(this);
					_la = _input.LA(1);
				}
				setState(125);
				match(RETURN);
				setState(126);
				expression(0);
				}
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

	public static class DataContext extends ParserRuleContext {
		public TerminalNode DATA() { return getToken(yaflParser.DATA, 0); }
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TupleTypeContext tupleType() {
			return getRuleContext(TupleTypeContext.class,0);
		}
		public DataContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_data; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterData(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitData(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitData(this);
			else return visitor.visitChildren(this);
		}
	}

	public final DataContext data() throws RecognitionException {
		DataContext _localctx = new DataContext(_ctx, getState());
		enterRule(_localctx, 20, RULE_data);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(129);
			match(DATA);
			setState(130);
			match(NAME);
			setState(131);
			tupleType();
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

	public static class NamedParamsContext extends ParserRuleContext {
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TerminalNode COMMA() { return getToken(yaflParser.COMMA, 0); }
		public NamedParamsContext namedParams() {
			return getRuleContext(NamedParamsContext.class,0);
		}
		public NamedParamsContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_namedParams; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterNamedParams(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitNamedParams(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitNamedParams(this);
			else return visitor.visitChildren(this);
		}
	}

	public final NamedParamsContext namedParams() throws RecognitionException {
		NamedParamsContext _localctx = new NamedParamsContext(_ctx, getState());
		enterRule(_localctx, 22, RULE_namedParams);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(135);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,14,_ctx) ) {
			case 1:
				{
				setState(133);
				match(NAME);
				setState(134);
				match(T__4);
				}
				break;
			}
			setState(137);
			expression(0);
			setState(140);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==COMMA) {
				{
				setState(138);
				match(COMMA);
				setState(139);
				namedParams();
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
	public static class CompareExpressionContext extends ExpressionContext {
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public CompareExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterCompareExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitCompareExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitCompareExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class DotExpressionContext extends ExpressionContext {
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode DOT() { return getToken(yaflParser.DOT, 0); }
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public DotExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterDotExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitDotExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitDotExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class StringExpressionContext extends ExpressionContext {
		public TerminalNode STRING() { return getToken(yaflParser.STRING, 0); }
		public StringExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterStringExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitStringExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitStringExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class NamedValueExpressionContext extends ExpressionContext {
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public NamedValueExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterNamedValueExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitNamedValueExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitNamedValueExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class AddExpressionContext extends ExpressionContext {
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public TerminalNode ADDSUB() { return getToken(yaflParser.ADDSUB, 0); }
		public AddExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterAddExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitAddExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitAddExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class IfExpressionContext extends ExpressionContext {
		public TerminalNode IF() { return getToken(yaflParser.IF, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public List<CodeBlockContext> codeBlock() {
			return getRuleContexts(CodeBlockContext.class);
		}
		public CodeBlockContext codeBlock(int i) {
			return getRuleContext(CodeBlockContext.class,i);
		}
		public TerminalNode ELSE() { return getToken(yaflParser.ELSE, 0); }
		public IfExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterIfExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitIfExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitIfExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class IntegerExpressionContext extends ExpressionContext {
		public TerminalNode INTEGER() { return getToken(yaflParser.INTEGER, 0); }
		public IntegerExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterIntegerExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitIntegerExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitIntegerExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class InvokeExpressionContext extends ExpressionContext {
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public NamedParamsContext namedParams() {
			return getRuleContext(NamedParamsContext.class,0);
		}
		public InvokeExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterInvokeExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitInvokeExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitInvokeExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class ParenthesisedExpressionContext extends ExpressionContext {
		public CodeBlockContext codeBlock() {
			return getRuleContext(CodeBlockContext.class,0);
		}
		public ParenthesisedExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterParenthesisedExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitParenthesisedExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitParenthesisedExpression(this);
			else return visitor.visitChildren(this);
		}
	}
	public static class MulExpressionContext extends ExpressionContext {
		public List<ExpressionContext> expression() {
			return getRuleContexts(ExpressionContext.class);
		}
		public ExpressionContext expression(int i) {
			return getRuleContext(ExpressionContext.class,i);
		}
		public TerminalNode MULTDIV() { return getToken(yaflParser.MULTDIV, 0); }
		public MulExpressionContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterMulExpression(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitMulExpression(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitMulExpression(this);
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
		int _startState = 24;
		enterRecursionRule(_localctx, 24, RULE_expression, _p);
		int _la;
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(156);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case IF:
				{
				_localctx = new IfExpressionContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;

				setState(143);
				match(IF);
				setState(144);
				expression(0);
				setState(145);
				codeBlock();
				setState(146);
				match(ELSE);
				setState(147);
				codeBlock();
				}
				break;
			case T__2:
				{
				_localctx = new ParenthesisedExpressionContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(149);
				match(T__2);
				setState(150);
				codeBlock();
				setState(151);
				match(T__3);
				}
				break;
			case INTEGER:
				{
				_localctx = new IntegerExpressionContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(153);
				match(INTEGER);
				}
				break;
			case STRING:
				{
				_localctx = new StringExpressionContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(154);
				match(STRING);
				}
				break;
			case NAME:
				{
				_localctx = new NamedValueExpressionContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(155);
				match(NAME);
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
			_ctx.stop = _input.LT(-1);
			setState(177);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,18,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					if ( _parseListeners!=null ) triggerExitRuleEvent();
					_prevctx = _localctx;
					{
					setState(175);
					_errHandler.sync(this);
					switch ( getInterpreter().adaptivePredict(_input,17,_ctx) ) {
					case 1:
						{
						_localctx = new MulExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(158);
						if (!(precpred(_ctx, 8))) throw new FailedPredicateException(this, "precpred(_ctx, 8)");
						setState(159);
						match(MULTDIV);
						setState(160);
						expression(9);
						}
						break;
					case 2:
						{
						_localctx = new AddExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(161);
						if (!(precpred(_ctx, 7))) throw new FailedPredicateException(this, "precpred(_ctx, 7)");
						setState(162);
						match(ADDSUB);
						setState(163);
						expression(8);
						}
						break;
					case 3:
						{
						_localctx = new CompareExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(164);
						if (!(precpred(_ctx, 6))) throw new FailedPredicateException(this, "precpred(_ctx, 6)");
						setState(165);
						_la = _input.LA(1);
						if ( !((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__0) | (1L << T__1) | (1L << T__4))) != 0)) ) {
						_errHandler.recoverInline(this);
						}
						else {
							if ( _input.LA(1)==Token.EOF ) matchedEOF = true;
							_errHandler.reportMatch(this);
							consume();
						}
						setState(166);
						expression(7);
						}
						break;
					case 4:
						{
						_localctx = new DotExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(167);
						if (!(precpred(_ctx, 10))) throw new FailedPredicateException(this, "precpred(_ctx, 10)");
						setState(168);
						match(DOT);
						setState(169);
						match(NAME);
						}
						break;
					case 5:
						{
						_localctx = new InvokeExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(170);
						if (!(precpred(_ctx, 9))) throw new FailedPredicateException(this, "precpred(_ctx, 9)");
						{
						setState(171);
						match(T__2);
						setState(172);
						namedParams();
						setState(173);
						match(T__3);
						}
						}
						break;
					}
					} 
				}
				setState(179);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,18,_ctx);
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

	public static class CodeBlockContext extends ParserRuleContext {
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public List<StatementsContext> statements() {
			return getRuleContexts(StatementsContext.class);
		}
		public StatementsContext statements(int i) {
			return getRuleContext(StatementsContext.class,i);
		}
		public CodeBlockContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_codeBlock; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterCodeBlock(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitCodeBlock(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitCodeBlock(this);
			else return visitor.visitChildren(this);
		}
	}

	public final CodeBlockContext codeBlock() throws RecognitionException {
		CodeBlockContext _localctx = new CodeBlockContext(_ctx, getState());
		enterRule(_localctx, 26, RULE_codeBlock);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(183);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__4) | (1L << VAR) | (1L << FUN))) != 0)) {
				{
				{
				setState(180);
				statements();
				}
				}
				setState(185);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(186);
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

	public static class StatementsContext extends ParserRuleContext {
		public VarContext var() {
			return getRuleContext(VarContext.class,0);
		}
		public FunContext fun() {
			return getRuleContext(FunContext.class,0);
		}
		public StatementsContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_statements; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterStatements(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitStatements(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitStatements(this);
			else return visitor.visitChildren(this);
		}
	}

	public final StatementsContext statements() throws RecognitionException {
		StatementsContext _localctx = new StatementsContext(_ctx, getState());
		enterRule(_localctx, 28, RULE_statements);
		try {
			setState(190);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case T__4:
			case VAR:
				enterOuterAlt(_localctx, 1);
				{
				setState(188);
				var();
				}
				break;
			case FUN:
				enterOuterAlt(_localctx, 2);
				{
				setState(189);
				fun();
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

	public static class DeclarationsContext extends ParserRuleContext {
		public VarContext var() {
			return getRuleContext(VarContext.class,0);
		}
		public FunContext fun() {
			return getRuleContext(FunContext.class,0);
		}
		public DataContext data() {
			return getRuleContext(DataContext.class,0);
		}
		public AliasContext alias() {
			return getRuleContext(AliasContext.class,0);
		}
		public DeclarationsContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_declarations; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterDeclarations(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitDeclarations(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitDeclarations(this);
			else return visitor.visitChildren(this);
		}
	}

	public final DeclarationsContext declarations() throws RecognitionException {
		DeclarationsContext _localctx = new DeclarationsContext(_ctx, getState());
		enterRule(_localctx, 30, RULE_declarations);
		try {
			setState(196);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case T__4:
			case VAR:
				enterOuterAlt(_localctx, 1);
				{
				setState(192);
				var();
				}
				break;
			case FUN:
				enterOuterAlt(_localctx, 2);
				{
				setState(193);
				fun();
				}
				break;
			case DATA:
				enterOuterAlt(_localctx, 3);
				{
				setState(194);
				data();
				}
				break;
			case ALIAS:
				enterOuterAlt(_localctx, 4);
				{
				setState(195);
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

	public static class ModuleContext extends ParserRuleContext {
		public TerminalNode MODULE() { return getToken(yaflParser.MODULE, 0); }
		public SimpleTypeNameContext simpleTypeName() {
			return getRuleContext(SimpleTypeNameContext.class,0);
		}
		public ModuleContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_module; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterModule(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitModule(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitModule(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ModuleContext module() throws RecognitionException {
		ModuleContext _localctx = new ModuleContext(_ctx, getState());
		enterRule(_localctx, 32, RULE_module);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(198);
			match(MODULE);
			setState(199);
			simpleTypeName();
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

	public static class ImportsContext extends ParserRuleContext {
		public TerminalNode IMPORT() { return getToken(yaflParser.IMPORT, 0); }
		public SimpleTypeNameContext simpleTypeName() {
			return getRuleContext(SimpleTypeNameContext.class,0);
		}
		public ImportsContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_imports; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterImports(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitImports(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitImports(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ImportsContext imports() throws RecognitionException {
		ImportsContext _localctx = new ImportsContext(_ctx, getState());
		enterRule(_localctx, 34, RULE_imports);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(201);
			match(IMPORT);
			setState(202);
			simpleTypeName();
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
		public TerminalNode EOF() { return getToken(yaflParser.EOF, 0); }
		public ModuleContext module() {
			return getRuleContext(ModuleContext.class,0);
		}
		public List<ImportsContext> imports() {
			return getRuleContexts(ImportsContext.class);
		}
		public ImportsContext imports(int i) {
			return getRuleContext(ImportsContext.class,i);
		}
		public List<DeclarationsContext> declarations() {
			return getRuleContexts(DeclarationsContext.class);
		}
		public DeclarationsContext declarations(int i) {
			return getRuleContext(DeclarationsContext.class,i);
		}
		public RootContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_root; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterRoot(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitRoot(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitRoot(this);
			else return visitor.visitChildren(this);
		}
	}

	public final RootContext root() throws RecognitionException {
		RootContext _localctx = new RootContext(_ctx, getState());
		enterRule(_localctx, 36, RULE_root);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(205);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==MODULE) {
				{
				setState(204);
				module();
				}
			}

			setState(210);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while (_la==IMPORT) {
				{
				{
				setState(207);
				imports();
				}
				}
				setState(212);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(216);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << T__4) | (1L << ALIAS) | (1L << VAR) | (1L << FUN) | (1L << DATA))) != 0)) {
				{
				{
				setState(213);
				declarations();
				}
				}
				setState(218);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			setState(219);
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
		case 12:
			return expression_sempred((ExpressionContext)_localctx, predIndex);
		}
		return true;
	}
	private boolean expression_sempred(ExpressionContext _localctx, int predIndex) {
		switch (predIndex) {
		case 0:
			return precpred(_ctx, 8);
		case 1:
			return precpred(_ctx, 7);
		case 2:
			return precpred(_ctx, 6);
		case 3:
			return precpred(_ctx, 10);
		case 4:
			return precpred(_ctx, 9);
		}
		return true;
	}

	public static final String _serializedATN =
		"\3\u608b\ua72a\u8133\ub9ed\u417c\u3be7\u7786\u5964\3\35\u00e0\4\2\t\2"+
		"\4\3\t\3\4\4\t\4\4\5\t\5\4\6\t\6\4\7\t\7\4\b\t\b\4\t\t\t\4\n\t\n\4\13"+
		"\t\13\4\f\t\f\4\r\t\r\4\16\t\16\4\17\t\17\4\20\t\20\4\21\t\21\4\22\t\22"+
		"\4\23\t\23\4\24\t\24\3\2\3\2\3\2\7\2,\n\2\f\2\16\2/\13\2\3\3\3\3\3\3\3"+
		"\3\7\3\65\n\3\f\3\16\38\13\3\3\3\3\3\3\4\3\4\5\4>\n\4\3\5\3\5\3\5\3\5"+
		"\7\5D\n\5\f\5\16\5G\13\5\3\5\3\5\3\6\3\6\5\6M\n\6\3\7\3\7\3\7\5\7R\n\7"+
		"\3\7\3\7\5\7V\n\7\3\b\3\b\3\b\3\t\3\t\3\t\3\t\3\t\3\t\3\n\3\n\3\n\3\n"+
		"\3\n\3\n\5\ng\n\n\3\13\3\13\3\13\5\13l\n\13\3\13\3\13\5\13p\n\13\3\13"+
		"\3\13\3\13\5\13u\n\13\3\13\5\13x\n\13\3\13\7\13{\n\13\f\13\16\13~\13\13"+
		"\3\13\3\13\5\13\u0082\n\13\3\f\3\f\3\f\3\f\3\r\3\r\5\r\u008a\n\r\3\r\3"+
		"\r\3\r\5\r\u008f\n\r\3\16\3\16\3\16\3\16\3\16\3\16\3\16\3\16\3\16\3\16"+
		"\3\16\3\16\3\16\3\16\5\16\u009f\n\16\3\16\3\16\3\16\3\16\3\16\3\16\3\16"+
		"\3\16\3\16\3\16\3\16\3\16\3\16\3\16\3\16\3\16\3\16\7\16\u00b2\n\16\f\16"+
		"\16\16\u00b5\13\16\3\17\7\17\u00b8\n\17\f\17\16\17\u00bb\13\17\3\17\3"+
		"\17\3\20\3\20\5\20\u00c1\n\20\3\21\3\21\3\21\3\21\5\21\u00c7\n\21\3\22"+
		"\3\22\3\22\3\23\3\23\3\23\3\24\5\24\u00d0\n\24\3\24\7\24\u00d3\n\24\f"+
		"\24\16\24\u00d6\13\24\3\24\7\24\u00d9\n\24\f\24\16\24\u00dc\13\24\3\24"+
		"\3\24\3\24\2\3\32\25\2\4\6\b\n\f\16\20\22\24\26\30\32\34\36 \"$&\2\3\4"+
		"\2\3\4\7\7\2\u00ed\2(\3\2\2\2\4\60\3\2\2\2\6;\3\2\2\2\b?\3\2\2\2\nL\3"+
		"\2\2\2\fN\3\2\2\2\16W\3\2\2\2\20Z\3\2\2\2\22f\3\2\2\2\24h\3\2\2\2\26\u0083"+
		"\3\2\2\2\30\u0089\3\2\2\2\32\u009e\3\2\2\2\34\u00b9\3\2\2\2\36\u00c0\3"+
		"\2\2\2 \u00c6\3\2\2\2\"\u00c8\3\2\2\2$\u00cb\3\2\2\2&\u00cf\3\2\2\2(-"+
		"\7\31\2\2)*\7\30\2\2*,\7\31\2\2+)\3\2\2\2,/\3\2\2\2-+\3\2\2\2-.\3\2\2"+
		"\2.\3\3\2\2\2/-\3\2\2\2\60\61\7\3\2\2\61\66\5\6\4\2\62\63\7\26\2\2\63"+
		"\65\5\6\4\2\64\62\3\2\2\2\658\3\2\2\2\66\64\3\2\2\2\66\67\3\2\2\2\679"+
		"\3\2\2\28\66\3\2\2\29:\7\4\2\2:\5\3\2\2\2;=\5\2\2\2<>\5\4\3\2=<\3\2\2"+
		"\2=>\3\2\2\2>\7\3\2\2\2?@\7\5\2\2@E\5\f\7\2AB\7\26\2\2BD\5\f\7\2CA\3\2"+
		"\2\2DG\3\2\2\2EC\3\2\2\2EF\3\2\2\2FH\3\2\2\2GE\3\2\2\2HI\7\6\2\2I\t\3"+
		"\2\2\2JM\5\6\4\2KM\5\b\5\2LJ\3\2\2\2LK\3\2\2\2M\13\3\2\2\2NQ\7\31\2\2"+
		"OP\7\27\2\2PR\5\n\6\2QO\3\2\2\2QR\3\2\2\2RU\3\2\2\2ST\7\7\2\2TV\5\32\16"+
		"\2US\3\2\2\2UV\3\2\2\2V\r\3\2\2\2WX\7\23\2\2XY\5\32\16\2Y\17\3\2\2\2Z"+
		"[\7\b\2\2[\\\7\31\2\2\\]\5\6\4\2]^\7\27\2\2^_\5\n\6\2_\21\3\2\2\2`a\7"+
		"\t\2\2ab\7\31\2\2bc\7\27\2\2cg\5\n\6\2de\7\7\2\2eg\5\32\16\2f`\3\2\2\2"+
		"fd\3\2\2\2g\23\3\2\2\2hi\7\n\2\2ik\7\31\2\2jl\5\b\5\2kj\3\2\2\2kl\3\2"+
		"\2\2lo\3\2\2\2mn\7\27\2\2np\5\n\6\2om\3\2\2\2op\3\2\2\2p\u0081\3\2\2\2"+
		"qr\7\7\2\2rt\5\32\16\2su\5\16\b\2ts\3\2\2\2tu\3\2\2\2u\u0082\3\2\2\2v"+
		"x\5\16\b\2wv\3\2\2\2wx\3\2\2\2x|\3\2\2\2y{\5\36\20\2zy\3\2\2\2{~\3\2\2"+
		"\2|z\3\2\2\2|}\3\2\2\2}\177\3\2\2\2~|\3\2\2\2\177\u0080\7\17\2\2\u0080"+
		"\u0082\5\32\16\2\u0081q\3\2\2\2\u0081w\3\2\2\2\u0082\25\3\2\2\2\u0083"+
		"\u0084\7\13\2\2\u0084\u0085\7\31\2\2\u0085\u0086\5\b\5\2\u0086\27\3\2"+
		"\2\2\u0087\u0088\7\31\2\2\u0088\u008a\7\7\2\2\u0089\u0087\3\2\2\2\u0089"+
		"\u008a\3\2\2\2\u008a\u008b\3\2\2\2\u008b\u008e\5\32\16\2\u008c\u008d\7"+
		"\26\2\2\u008d\u008f\5\30\r\2\u008e\u008c\3\2\2\2\u008e\u008f\3\2\2\2\u008f"+
		"\31\3\2\2\2\u0090\u0091\b\16\1\2\u0091\u0092\7\r\2\2\u0092\u0093\5\32"+
		"\16\2\u0093\u0094\5\34\17\2\u0094\u0095\7\16\2\2\u0095\u0096\5\34\17\2"+
		"\u0096\u009f\3\2\2\2\u0097\u0098\7\5\2\2\u0098\u0099\5\34\17\2\u0099\u009a"+
		"\7\6\2\2\u009a\u009f\3\2\2\2\u009b\u009f\7\34\2\2\u009c\u009f\7\35\2\2"+
		"\u009d\u009f\7\31\2\2\u009e\u0090\3\2\2\2\u009e\u0097\3\2\2\2\u009e\u009b"+
		"\3\2\2\2\u009e\u009c\3\2\2\2\u009e\u009d\3\2\2\2\u009f\u00b3\3\2\2\2\u00a0"+
		"\u00a1\f\n\2\2\u00a1\u00a2\7\24\2\2\u00a2\u00b2\5\32\16\13\u00a3\u00a4"+
		"\f\t\2\2\u00a4\u00a5\7\25\2\2\u00a5\u00b2\5\32\16\n\u00a6\u00a7\f\b\2"+
		"\2\u00a7\u00a8\t\2\2\2\u00a8\u00b2\5\32\16\t\u00a9\u00aa\f\f\2\2\u00aa"+
		"\u00ab\7\30\2\2\u00ab\u00b2\7\31\2\2\u00ac\u00ad\f\13\2\2\u00ad\u00ae"+
		"\7\5\2\2\u00ae\u00af\5\30\r\2\u00af\u00b0\7\6\2\2\u00b0\u00b2\3\2\2\2"+
		"\u00b1\u00a0\3\2\2\2\u00b1\u00a3\3\2\2\2\u00b1\u00a6\3\2\2\2\u00b1\u00a9"+
		"\3\2\2\2\u00b1\u00ac\3\2\2\2\u00b2\u00b5\3\2\2\2\u00b3\u00b1\3\2\2\2\u00b3"+
		"\u00b4\3\2\2\2\u00b4\33\3\2\2\2\u00b5\u00b3\3\2\2\2\u00b6\u00b8\5\36\20"+
		"\2\u00b7\u00b6\3\2\2\2\u00b8\u00bb\3\2\2\2\u00b9\u00b7\3\2\2\2\u00b9\u00ba"+
		"\3\2\2\2\u00ba\u00bc\3\2\2\2\u00bb\u00b9\3\2\2\2\u00bc\u00bd\5\32\16\2"+
		"\u00bd\35\3\2\2\2\u00be\u00c1\5\22\n\2\u00bf\u00c1\5\24\13\2\u00c0\u00be"+
		"\3\2\2\2\u00c0\u00bf\3\2\2\2\u00c1\37\3\2\2\2\u00c2\u00c7\5\22\n\2\u00c3"+
		"\u00c7\5\24\13\2\u00c4\u00c7\5\26\f\2\u00c5\u00c7\5\20\t\2\u00c6\u00c2"+
		"\3\2\2\2\u00c6\u00c3\3\2\2\2\u00c6\u00c4\3\2\2\2\u00c6\u00c5\3\2\2\2\u00c7"+
		"!\3\2\2\2\u00c8\u00c9\7\21\2\2\u00c9\u00ca\5\2\2\2\u00ca#\3\2\2\2\u00cb"+
		"\u00cc\7\22\2\2\u00cc\u00cd\5\2\2\2\u00cd%\3\2\2\2\u00ce\u00d0\5\"\22"+
		"\2\u00cf\u00ce\3\2\2\2\u00cf\u00d0\3\2\2\2\u00d0\u00d4\3\2\2\2\u00d1\u00d3"+
		"\5$\23\2\u00d2\u00d1\3\2\2\2\u00d3\u00d6\3\2\2\2\u00d4\u00d2\3\2\2\2\u00d4"+
		"\u00d5\3\2\2\2\u00d5\u00da\3\2\2\2\u00d6\u00d4\3\2\2\2\u00d7\u00d9\5 "+
		"\21\2\u00d8\u00d7\3\2\2\2\u00d9\u00dc\3\2\2\2\u00da\u00d8\3\2\2\2\u00da"+
		"\u00db\3\2\2\2\u00db\u00dd\3\2\2\2\u00dc\u00da\3\2\2\2\u00dd\u00de\7\2"+
		"\2\3\u00de\'\3\2\2\2\33-\66=ELQUfkotw|\u0081\u0089\u008e\u009e\u00b1\u00b3"+
		"\u00b9\u00c0\u00c6\u00cf\u00d4\u00da";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}