// Generated from /Users/mbrown/Projects/my/yaflc/src/yafl.g4 by ANTLR 4.9.1
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
	static { RuntimeMetaData.checkVersion("4.9.1", RuntimeMetaData.VERSION); }

	protected static final DFA[] _decisionToDFA;
	protected static final PredictionContextCache _sharedContextCache =
		new PredictionContextCache();
	public static final int
		LET=1, FUN=2, DATA=3, CLASS=4, IF=5, ELSE=6, RETURN=7, OBJECT=8, MULTDIV=9, 
		ADDSUB=10, OBRACKET=11, CBRACKET=12, COMMA=13, COLON=14, EQUALS=15, DOT=16, 
		NAME=17, WS=18, COMMENT=19, INTEGER=20;
	public static final int
		RULE_parameter = 0, RULE_parameters = 1, RULE_types = 2, RULE_named = 3, 
		RULE_tuple = 4, RULE_function = 5, RULE_type = 6, RULE_funDecl = 7, RULE_funBody = 8, 
		RULE_let = 9, RULE_fun = 10, RULE_data = 11, RULE_clazz = 12, RULE_clazzBody = 13, 
		RULE_namedParams = 14, RULE_expression = 15, RULE_codeBlock = 16, RULE_statements = 17, 
		RULE_declarations = 18, RULE_root = 19;
	private static String[] makeRuleNames() {
		return new String[] {
			"parameter", "parameters", "types", "named", "tuple", "function", "type", 
			"funDecl", "funBody", "let", "fun", "data", "clazz", "clazzBody", "namedParams", 
			"expression", "codeBlock", "statements", "declarations", "root"
		};
	}
	public static final String[] ruleNames = makeRuleNames();

	private static String[] makeLiteralNames() {
		return new String[] {
			null, "'let'", "'fun'", "'data'", "'class'", "'if'", "'else'", "'return'", 
			"'object'", null, null, "'('", "')'", "','", "':'", "'='", "'.'"
		};
	}
	private static final String[] _LITERAL_NAMES = makeLiteralNames();
	private static String[] makeSymbolicNames() {
		return new String[] {
			null, "LET", "FUN", "DATA", "CLASS", "IF", "ELSE", "RETURN", "OBJECT", 
			"MULTDIV", "ADDSUB", "OBRACKET", "CBRACKET", "COMMA", "COLON", "EQUALS", 
			"DOT", "NAME", "WS", "COMMENT", "INTEGER"
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

	public static class ParameterContext extends ParserRuleContext {
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TerminalNode COLON() { return getToken(yaflParser.COLON, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public TerminalNode EQUALS() { return getToken(yaflParser.EQUALS, 0); }
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
		enterRule(_localctx, 0, RULE_parameter);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(40);
			match(NAME);
			setState(43);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==COLON) {
				{
				setState(41);
				match(COLON);
				setState(42);
				type();
				}
			}

			setState(47);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==EQUALS) {
				{
				setState(45);
				match(EQUALS);
				setState(46);
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

	public static class ParametersContext extends ParserRuleContext {
		public ParameterContext parameter() {
			return getRuleContext(ParameterContext.class,0);
		}
		public TerminalNode COMMA() { return getToken(yaflParser.COMMA, 0); }
		public ParametersContext parameters() {
			return getRuleContext(ParametersContext.class,0);
		}
		public ParametersContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_parameters; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterParameters(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitParameters(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitParameters(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ParametersContext parameters() throws RecognitionException {
		ParametersContext _localctx = new ParametersContext(_ctx, getState());
		enterRule(_localctx, 2, RULE_parameters);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(49);
			parameter();
			setState(52);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==COMMA) {
				{
				setState(50);
				match(COMMA);
				setState(51);
				parameters();
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

	public static class TypesContext extends ParserRuleContext {
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public TerminalNode COMMA() { return getToken(yaflParser.COMMA, 0); }
		public TypesContext types() {
			return getRuleContext(TypesContext.class,0);
		}
		public TypesContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_types; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterTypes(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitTypes(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitTypes(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TypesContext types() throws RecognitionException {
		TypesContext _localctx = new TypesContext(_ctx, getState());
		enterRule(_localctx, 4, RULE_types);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(54);
			type();
			setState(57);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,3,_ctx) ) {
			case 1:
				{
				setState(55);
				match(COMMA);
				setState(56);
				types();
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

	public static class NamedContext extends ParserRuleContext {
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TerminalNode DOT() { return getToken(yaflParser.DOT, 0); }
		public NamedContext named() {
			return getRuleContext(NamedContext.class,0);
		}
		public NamedContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_named; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterNamed(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitNamed(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitNamed(this);
			else return visitor.visitChildren(this);
		}
	}

	public final NamedContext named() throws RecognitionException {
		NamedContext _localctx = new NamedContext(_ctx, getState());
		enterRule(_localctx, 6, RULE_named);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(59);
			match(NAME);
			setState(62);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==DOT) {
				{
				setState(60);
				match(DOT);
				setState(61);
				named();
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

	public static class TupleContext extends ParserRuleContext {
		public TerminalNode OBRACKET() { return getToken(yaflParser.OBRACKET, 0); }
		public ParametersContext parameters() {
			return getRuleContext(ParametersContext.class,0);
		}
		public TerminalNode CBRACKET() { return getToken(yaflParser.CBRACKET, 0); }
		public TupleContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_tuple; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterTuple(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitTuple(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitTuple(this);
			else return visitor.visitChildren(this);
		}
	}

	public final TupleContext tuple() throws RecognitionException {
		TupleContext _localctx = new TupleContext(_ctx, getState());
		enterRule(_localctx, 8, RULE_tuple);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(64);
			match(OBRACKET);
			setState(65);
			parameters();
			setState(66);
			match(CBRACKET);
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
		public TupleContext tuple() {
			return getRuleContext(TupleContext.class,0);
		}
		public TerminalNode COLON() { return getToken(yaflParser.COLON, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public FunctionContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_function; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterFunction(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitFunction(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitFunction(this);
			else return visitor.visitChildren(this);
		}
	}

	public final FunctionContext function() throws RecognitionException {
		FunctionContext _localctx = new FunctionContext(_ctx, getState());
		enterRule(_localctx, 10, RULE_function);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(68);
			tuple();
			setState(69);
			match(COLON);
			setState(70);
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
		public FunctionContext function() {
			return getRuleContext(FunctionContext.class,0);
		}
		public TupleContext tuple() {
			return getRuleContext(TupleContext.class,0);
		}
		public NamedContext named() {
			return getRuleContext(NamedContext.class,0);
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
		enterRule(_localctx, 12, RULE_type);
		try {
			setState(75);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,5,_ctx) ) {
			case 1:
				enterOuterAlt(_localctx, 1);
				{
				setState(72);
				function();
				}
				break;
			case 2:
				enterOuterAlt(_localctx, 2);
				{
				setState(73);
				tuple();
				}
				break;
			case 3:
				enterOuterAlt(_localctx, 3);
				{
				setState(74);
				named();
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

	public static class FunDeclContext extends ParserRuleContext {
		public TerminalNode FUN() { return getToken(yaflParser.FUN, 0); }
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TupleContext tuple() {
			return getRuleContext(TupleContext.class,0);
		}
		public TerminalNode COLON() { return getToken(yaflParser.COLON, 0); }
		public TypeContext type() {
			return getRuleContext(TypeContext.class,0);
		}
		public FunDeclContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_funDecl; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterFunDecl(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitFunDecl(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitFunDecl(this);
			else return visitor.visitChildren(this);
		}
	}

	public final FunDeclContext funDecl() throws RecognitionException {
		FunDeclContext _localctx = new FunDeclContext(_ctx, getState());
		enterRule(_localctx, 14, RULE_funDecl);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(77);
			match(FUN);
			setState(78);
			match(NAME);
			setState(80);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==OBRACKET) {
				{
				setState(79);
				tuple();
				}
			}

			setState(84);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==COLON) {
				{
				setState(82);
				match(COLON);
				setState(83);
				type();
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

	public static class FunBodyContext extends ParserRuleContext {
		public TerminalNode EQUALS() { return getToken(yaflParser.EQUALS, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode RETURN() { return getToken(yaflParser.RETURN, 0); }
		public StatementsContext statements() {
			return getRuleContext(StatementsContext.class,0);
		}
		public FunBodyContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_funBody; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterFunBody(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitFunBody(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitFunBody(this);
			else return visitor.visitChildren(this);
		}
	}

	public final FunBodyContext funBody() throws RecognitionException {
		FunBodyContext _localctx = new FunBodyContext(_ctx, getState());
		enterRule(_localctx, 16, RULE_funBody);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(93);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case EQUALS:
				{
				{
				setState(86);
				match(EQUALS);
				setState(87);
				expression(0);
				}
				}
				break;
			case LET:
			case FUN:
			case RETURN:
				{
				{
				setState(89);
				_errHandler.sync(this);
				_la = _input.LA(1);
				if (_la==LET || _la==FUN) {
					{
					setState(88);
					statements();
					}
				}

				setState(91);
				match(RETURN);
				setState(92);
				expression(0);
				}
				}
				break;
			default:
				throw new NoViableAltException(this);
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

	public static class LetContext extends ParserRuleContext {
		public TerminalNode LET() { return getToken(yaflParser.LET, 0); }
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TerminalNode EQUALS() { return getToken(yaflParser.EQUALS, 0); }
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public LetContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_let; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterLet(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitLet(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitLet(this);
			else return visitor.visitChildren(this);
		}
	}

	public final LetContext let() throws RecognitionException {
		LetContext _localctx = new LetContext(_ctx, getState());
		enterRule(_localctx, 18, RULE_let);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(95);
			match(LET);
			setState(96);
			match(NAME);
			setState(97);
			match(EQUALS);
			setState(98);
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

	public static class FunContext extends ParserRuleContext {
		public FunDeclContext funDecl() {
			return getRuleContext(FunDeclContext.class,0);
		}
		public FunBodyContext funBody() {
			return getRuleContext(FunBodyContext.class,0);
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
		enterRule(_localctx, 20, RULE_fun);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(100);
			funDecl();
			setState(101);
			funBody();
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
		public TerminalNode OBRACKET() { return getToken(yaflParser.OBRACKET, 0); }
		public ParametersContext parameters() {
			return getRuleContext(ParametersContext.class,0);
		}
		public TerminalNode CBRACKET() { return getToken(yaflParser.CBRACKET, 0); }
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
		enterRule(_localctx, 22, RULE_data);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(103);
			match(DATA);
			setState(104);
			match(NAME);
			setState(105);
			match(OBRACKET);
			setState(106);
			parameters();
			setState(107);
			match(CBRACKET);
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

	public static class ClazzContext extends ParserRuleContext {
		public TerminalNode CLASS() { return getToken(yaflParser.CLASS, 0); }
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public ClazzBodyContext clazzBody() {
			return getRuleContext(ClazzBodyContext.class,0);
		}
		public ClazzContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_clazz; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterClazz(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitClazz(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitClazz(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ClazzContext clazz() throws RecognitionException {
		ClazzContext _localctx = new ClazzContext(_ctx, getState());
		enterRule(_localctx, 24, RULE_clazz);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(109);
			match(CLASS);
			setState(110);
			match(NAME);
			setState(111);
			clazzBody();
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

	public static class ClazzBodyContext extends ParserRuleContext {
		public FunDeclContext funDecl() {
			return getRuleContext(FunDeclContext.class,0);
		}
		public ClazzBodyContext clazzBody() {
			return getRuleContext(ClazzBodyContext.class,0);
		}
		public ClazzBodyContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_clazzBody; }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterClazzBody(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitClazzBody(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitClazzBody(this);
			else return visitor.visitChildren(this);
		}
	}

	public final ClazzBodyContext clazzBody() throws RecognitionException {
		ClazzBodyContext _localctx = new ClazzBodyContext(_ctx, getState());
		enterRule(_localctx, 26, RULE_clazzBody);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(113);
			funDecl();
			setState(115);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,10,_ctx) ) {
			case 1:
				{
				setState(114);
				clazzBody();
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

	public static class NamedParamsContext extends ParserRuleContext {
		public ExpressionContext expression() {
			return getRuleContext(ExpressionContext.class,0);
		}
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public TerminalNode EQUALS() { return getToken(yaflParser.EQUALS, 0); }
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
		enterRule(_localctx, 28, RULE_namedParams);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(119);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,11,_ctx) ) {
			case 1:
				{
				setState(117);
				match(NAME);
				setState(118);
				match(EQUALS);
				}
				break;
			}
			setState(121);
			expression(0);
			setState(124);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==COMMA) {
				{
				setState(122);
				match(COMMA);
				setState(123);
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
	public static class NamedValueContext extends ExpressionContext {
		public TerminalNode NAME() { return getToken(yaflParser.NAME, 0); }
		public NamedValueContext(ExpressionContext ctx) { copyFrom(ctx); }
		@Override
		public void enterRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).enterNamedValue(this);
		}
		@Override
		public void exitRule(ParseTreeListener listener) {
			if ( listener instanceof yaflListener ) ((yaflListener)listener).exitNamedValue(this);
		}
		@Override
		public <T> T accept(ParseTreeVisitor<? extends T> visitor) {
			if ( visitor instanceof yaflVisitor ) return ((yaflVisitor<? extends T>)visitor).visitNamedValue(this);
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
		public TerminalNode OBRACKET() { return getToken(yaflParser.OBRACKET, 0); }
		public NamedParamsContext namedParams() {
			return getRuleContext(NamedParamsContext.class,0);
		}
		public TerminalNode CBRACKET() { return getToken(yaflParser.CBRACKET, 0); }
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
		public TerminalNode OBRACKET() { return getToken(yaflParser.OBRACKET, 0); }
		public CodeBlockContext codeBlock() {
			return getRuleContext(CodeBlockContext.class,0);
		}
		public TerminalNode CBRACKET() { return getToken(yaflParser.CBRACKET, 0); }
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
		int _startState = 30;
		enterRecursionRule(_localctx, 30, RULE_expression, _p);
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(139);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case IF:
				{
				_localctx = new IfExpressionContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;

				setState(127);
				match(IF);
				setState(128);
				expression(0);
				setState(129);
				codeBlock();
				setState(130);
				match(ELSE);
				setState(131);
				codeBlock();
				}
				break;
			case OBRACKET:
				{
				_localctx = new ParenthesisedExpressionContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(133);
				match(OBRACKET);
				setState(134);
				codeBlock();
				setState(135);
				match(CBRACKET);
				}
				break;
			case INTEGER:
				{
				_localctx = new IntegerExpressionContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(137);
				match(INTEGER);
				}
				break;
			case NAME:
				{
				_localctx = new NamedValueContext(_localctx);
				_ctx = _localctx;
				_prevctx = _localctx;
				setState(138);
				match(NAME);
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
			_ctx.stop = _input.LT(-1);
			setState(157);
			_errHandler.sync(this);
			_alt = getInterpreter().adaptivePredict(_input,15,_ctx);
			while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER ) {
				if ( _alt==1 ) {
					if ( _parseListeners!=null ) triggerExitRuleEvent();
					_prevctx = _localctx;
					{
					setState(155);
					_errHandler.sync(this);
					switch ( getInterpreter().adaptivePredict(_input,14,_ctx) ) {
					case 1:
						{
						_localctx = new MulExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(141);
						if (!(precpred(_ctx, 7))) throw new FailedPredicateException(this, "precpred(_ctx, 7)");
						setState(142);
						match(MULTDIV);
						setState(143);
						expression(8);
						}
						break;
					case 2:
						{
						_localctx = new AddExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(144);
						if (!(precpred(_ctx, 6))) throw new FailedPredicateException(this, "precpred(_ctx, 6)");
						setState(145);
						match(ADDSUB);
						setState(146);
						expression(7);
						}
						break;
					case 3:
						{
						_localctx = new DotExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(147);
						if (!(precpred(_ctx, 8))) throw new FailedPredicateException(this, "precpred(_ctx, 8)");
						setState(148);
						match(DOT);
						setState(149);
						match(NAME);
						}
						break;
					case 4:
						{
						_localctx = new InvokeExpressionContext(new ExpressionContext(_parentctx, _parentState));
						pushNewRecursionContext(_localctx, _startState, RULE_expression);
						setState(150);
						if (!(precpred(_ctx, 3))) throw new FailedPredicateException(this, "precpred(_ctx, 3)");
						{
						setState(151);
						match(OBRACKET);
						setState(152);
						namedParams();
						setState(153);
						match(CBRACKET);
						}
						}
						break;
					}
					} 
				}
				setState(159);
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,15,_ctx);
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
		public StatementsContext statements() {
			return getRuleContext(StatementsContext.class,0);
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
		enterRule(_localctx, 32, RULE_codeBlock);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(161);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==LET || _la==FUN) {
				{
				setState(160);
				statements();
				}
			}

			setState(163);
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
		public LetContext let() {
			return getRuleContext(LetContext.class,0);
		}
		public FunContext fun() {
			return getRuleContext(FunContext.class,0);
		}
		public StatementsContext statements() {
			return getRuleContext(StatementsContext.class,0);
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
		enterRule(_localctx, 34, RULE_statements);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(167);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case LET:
				{
				setState(165);
				let();
				}
				break;
			case FUN:
				{
				setState(166);
				fun();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
			setState(170);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if (_la==LET || _la==FUN) {
				{
				setState(169);
				statements();
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

	public static class DeclarationsContext extends ParserRuleContext {
		public LetContext let() {
			return getRuleContext(LetContext.class,0);
		}
		public FunContext fun() {
			return getRuleContext(FunContext.class,0);
		}
		public DataContext data() {
			return getRuleContext(DataContext.class,0);
		}
		public ClazzContext clazz() {
			return getRuleContext(ClazzContext.class,0);
		}
		public DeclarationsContext declarations() {
			return getRuleContext(DeclarationsContext.class,0);
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
		enterRule(_localctx, 36, RULE_declarations);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(176);
			_errHandler.sync(this);
			switch (_input.LA(1)) {
			case LET:
				{
				setState(172);
				let();
				}
				break;
			case FUN:
				{
				setState(173);
				fun();
				}
				break;
			case DATA:
				{
				setState(174);
				data();
				}
				break;
			case CLASS:
				{
				setState(175);
				clazz();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
			setState(179);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << LET) | (1L << FUN) | (1L << DATA) | (1L << CLASS))) != 0)) {
				{
				setState(178);
				declarations();
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

	public static class RootContext extends ParserRuleContext {
		public TerminalNode EOF() { return getToken(yaflParser.EOF, 0); }
		public DeclarationsContext declarations() {
			return getRuleContext(DeclarationsContext.class,0);
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
		enterRule(_localctx, 38, RULE_root);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(182);
			_errHandler.sync(this);
			_la = _input.LA(1);
			if ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << LET) | (1L << FUN) | (1L << DATA) | (1L << CLASS))) != 0)) {
				{
				setState(181);
				declarations();
				}
			}

			setState(184);
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
		case 15:
			return expression_sempred((ExpressionContext)_localctx, predIndex);
		}
		return true;
	}
	private boolean expression_sempred(ExpressionContext _localctx, int predIndex) {
		switch (predIndex) {
		case 0:
			return precpred(_ctx, 7);
		case 1:
			return precpred(_ctx, 6);
		case 2:
			return precpred(_ctx, 8);
		case 3:
			return precpred(_ctx, 3);
		}
		return true;
	}

	public static final String _serializedATN =
		"\3\u608b\ua72a\u8133\ub9ed\u417c\u3be7\u7786\u5964\3\26\u00bd\4\2\t\2"+
		"\4\3\t\3\4\4\t\4\4\5\t\5\4\6\t\6\4\7\t\7\4\b\t\b\4\t\t\t\4\n\t\n\4\13"+
		"\t\13\4\f\t\f\4\r\t\r\4\16\t\16\4\17\t\17\4\20\t\20\4\21\t\21\4\22\t\22"+
		"\4\23\t\23\4\24\t\24\4\25\t\25\3\2\3\2\3\2\5\2.\n\2\3\2\3\2\5\2\62\n\2"+
		"\3\3\3\3\3\3\5\3\67\n\3\3\4\3\4\3\4\5\4<\n\4\3\5\3\5\3\5\5\5A\n\5\3\6"+
		"\3\6\3\6\3\6\3\7\3\7\3\7\3\7\3\b\3\b\3\b\5\bN\n\b\3\t\3\t\3\t\5\tS\n\t"+
		"\3\t\3\t\5\tW\n\t\3\n\3\n\3\n\5\n\\\n\n\3\n\3\n\5\n`\n\n\3\13\3\13\3\13"+
		"\3\13\3\13\3\f\3\f\3\f\3\r\3\r\3\r\3\r\3\r\3\r\3\16\3\16\3\16\3\16\3\17"+
		"\3\17\5\17v\n\17\3\20\3\20\5\20z\n\20\3\20\3\20\3\20\5\20\177\n\20\3\21"+
		"\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\5\21\u008e"+
		"\n\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21\3\21"+
		"\3\21\7\21\u009e\n\21\f\21\16\21\u00a1\13\21\3\22\5\22\u00a4\n\22\3\22"+
		"\3\22\3\23\3\23\5\23\u00aa\n\23\3\23\5\23\u00ad\n\23\3\24\3\24\3\24\3"+
		"\24\5\24\u00b3\n\24\3\24\5\24\u00b6\n\24\3\25\5\25\u00b9\n\25\3\25\3\25"+
		"\3\25\2\3 \26\2\4\6\b\n\f\16\20\22\24\26\30\32\34\36 \"$&(\2\2\2\u00c5"+
		"\2*\3\2\2\2\4\63\3\2\2\2\68\3\2\2\2\b=\3\2\2\2\nB\3\2\2\2\fF\3\2\2\2\16"+
		"M\3\2\2\2\20O\3\2\2\2\22_\3\2\2\2\24a\3\2\2\2\26f\3\2\2\2\30i\3\2\2\2"+
		"\32o\3\2\2\2\34s\3\2\2\2\36y\3\2\2\2 \u008d\3\2\2\2\"\u00a3\3\2\2\2$\u00a9"+
		"\3\2\2\2&\u00b2\3\2\2\2(\u00b8\3\2\2\2*-\7\23\2\2+,\7\20\2\2,.\5\16\b"+
		"\2-+\3\2\2\2-.\3\2\2\2.\61\3\2\2\2/\60\7\21\2\2\60\62\5 \21\2\61/\3\2"+
		"\2\2\61\62\3\2\2\2\62\3\3\2\2\2\63\66\5\2\2\2\64\65\7\17\2\2\65\67\5\4"+
		"\3\2\66\64\3\2\2\2\66\67\3\2\2\2\67\5\3\2\2\28;\5\16\b\29:\7\17\2\2:<"+
		"\5\6\4\2;9\3\2\2\2;<\3\2\2\2<\7\3\2\2\2=@\7\23\2\2>?\7\22\2\2?A\5\b\5"+
		"\2@>\3\2\2\2@A\3\2\2\2A\t\3\2\2\2BC\7\r\2\2CD\5\4\3\2DE\7\16\2\2E\13\3"+
		"\2\2\2FG\5\n\6\2GH\7\20\2\2HI\5\16\b\2I\r\3\2\2\2JN\5\f\7\2KN\5\n\6\2"+
		"LN\5\b\5\2MJ\3\2\2\2MK\3\2\2\2ML\3\2\2\2N\17\3\2\2\2OP\7\4\2\2PR\7\23"+
		"\2\2QS\5\n\6\2RQ\3\2\2\2RS\3\2\2\2SV\3\2\2\2TU\7\20\2\2UW\5\16\b\2VT\3"+
		"\2\2\2VW\3\2\2\2W\21\3\2\2\2XY\7\21\2\2Y`\5 \21\2Z\\\5$\23\2[Z\3\2\2\2"+
		"[\\\3\2\2\2\\]\3\2\2\2]^\7\t\2\2^`\5 \21\2_X\3\2\2\2_[\3\2\2\2`\23\3\2"+
		"\2\2ab\7\3\2\2bc\7\23\2\2cd\7\21\2\2de\5 \21\2e\25\3\2\2\2fg\5\20\t\2"+
		"gh\5\22\n\2h\27\3\2\2\2ij\7\5\2\2jk\7\23\2\2kl\7\r\2\2lm\5\4\3\2mn\7\16"+
		"\2\2n\31\3\2\2\2op\7\6\2\2pq\7\23\2\2qr\5\34\17\2r\33\3\2\2\2su\5\20\t"+
		"\2tv\5\34\17\2ut\3\2\2\2uv\3\2\2\2v\35\3\2\2\2wx\7\23\2\2xz\7\21\2\2y"+
		"w\3\2\2\2yz\3\2\2\2z{\3\2\2\2{~\5 \21\2|}\7\17\2\2}\177\5\36\20\2~|\3"+
		"\2\2\2~\177\3\2\2\2\177\37\3\2\2\2\u0080\u0081\b\21\1\2\u0081\u0082\7"+
		"\7\2\2\u0082\u0083\5 \21\2\u0083\u0084\5\"\22\2\u0084\u0085\7\b\2\2\u0085"+
		"\u0086\5\"\22\2\u0086\u008e\3\2\2\2\u0087\u0088\7\r\2\2\u0088\u0089\5"+
		"\"\22\2\u0089\u008a\7\16\2\2\u008a\u008e\3\2\2\2\u008b\u008e\7\26\2\2"+
		"\u008c\u008e\7\23\2\2\u008d\u0080\3\2\2\2\u008d\u0087\3\2\2\2\u008d\u008b"+
		"\3\2\2\2\u008d\u008c\3\2\2\2\u008e\u009f\3\2\2\2\u008f\u0090\f\t\2\2\u0090"+
		"\u0091\7\13\2\2\u0091\u009e\5 \21\n\u0092\u0093\f\b\2\2\u0093\u0094\7"+
		"\f\2\2\u0094\u009e\5 \21\t\u0095\u0096\f\n\2\2\u0096\u0097\7\22\2\2\u0097"+
		"\u009e\7\23\2\2\u0098\u0099\f\5\2\2\u0099\u009a\7\r\2\2\u009a\u009b\5"+
		"\36\20\2\u009b\u009c\7\16\2\2\u009c\u009e\3\2\2\2\u009d\u008f\3\2\2\2"+
		"\u009d\u0092\3\2\2\2\u009d\u0095\3\2\2\2\u009d\u0098\3\2\2\2\u009e\u00a1"+
		"\3\2\2\2\u009f\u009d\3\2\2\2\u009f\u00a0\3\2\2\2\u00a0!\3\2\2\2\u00a1"+
		"\u009f\3\2\2\2\u00a2\u00a4\5$\23\2\u00a3\u00a2\3\2\2\2\u00a3\u00a4\3\2"+
		"\2\2\u00a4\u00a5\3\2\2\2\u00a5\u00a6\5 \21\2\u00a6#\3\2\2\2\u00a7\u00aa"+
		"\5\24\13\2\u00a8\u00aa\5\26\f\2\u00a9\u00a7\3\2\2\2\u00a9\u00a8\3\2\2"+
		"\2\u00aa\u00ac\3\2\2\2\u00ab\u00ad\5$\23\2\u00ac\u00ab\3\2\2\2\u00ac\u00ad"+
		"\3\2\2\2\u00ad%\3\2\2\2\u00ae\u00b3\5\24\13\2\u00af\u00b3\5\26\f\2\u00b0"+
		"\u00b3\5\30\r\2\u00b1\u00b3\5\32\16\2\u00b2\u00ae\3\2\2\2\u00b2\u00af"+
		"\3\2\2\2\u00b2\u00b0\3\2\2\2\u00b2\u00b1\3\2\2\2\u00b3\u00b5\3\2\2\2\u00b4"+
		"\u00b6\5&\24\2\u00b5\u00b4\3\2\2\2\u00b5\u00b6\3\2\2\2\u00b6\'\3\2\2\2"+
		"\u00b7\u00b9\5&\24\2\u00b8\u00b7\3\2\2\2\u00b8\u00b9\3\2\2\2\u00b9\u00ba"+
		"\3\2\2\2\u00ba\u00bb\7\2\2\3\u00bb)\3\2\2\2\30-\61\66;@MRV[_uy~\u008d"+
		"\u009d\u009f\u00a3\u00a9\u00ac\u00b2\u00b5\u00b8";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}