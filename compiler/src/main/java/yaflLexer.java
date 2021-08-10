// Generated from /Users/mbrown/Projects/my/yafl/compiler/src/yafl.g4 by ANTLR 4.9.1
import org.antlr.v4.runtime.Lexer;
import org.antlr.v4.runtime.CharStream;
import org.antlr.v4.runtime.Token;
import org.antlr.v4.runtime.TokenStream;
import org.antlr.v4.runtime.*;
import org.antlr.v4.runtime.atn.*;
import org.antlr.v4.runtime.dfa.DFA;
import org.antlr.v4.runtime.misc.*;

@SuppressWarnings({"all", "warnings", "unchecked", "unused", "cast"})
public class yaflLexer extends Lexer {
	static { RuntimeMetaData.checkVersion("4.9.1", RuntimeMetaData.VERSION); }

	protected static final DFA[] _decisionToDFA;
	protected static final PredictionContextCache _sharedContextCache =
		new PredictionContextCache();
	public static final int
		LET=1, FUN=2, DATA=3, CLASS=4, IF=5, ELSE=6, RETURN=7, OBJECT=8, MULTDIV=9, 
		ADDSUB=10, OBRACKET=11, CBRACKET=12, COMMA=13, COLON=14, EQUALS=15, DOT=16, 
		NAME=17, WS=18, COMMENT=19, INTEGER=20;
	public static String[] channelNames = {
		"DEFAULT_TOKEN_CHANNEL", "HIDDEN"
	};

	public static String[] modeNames = {
		"DEFAULT_MODE"
	};

	private static String[] makeRuleNames() {
		return new String[] {
			"LET", "FUN", "DATA", "CLASS", "IF", "ELSE", "RETURN", "OBJECT", "MULTDIV", 
			"ADDSUB", "OBRACKET", "CBRACKET", "COMMA", "COLON", "EQUALS", "DOT", 
			"NAME", "WS", "COMMENT", "INTEGER"
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


	public yaflLexer(CharStream input) {
		super(input);
		_interp = new LexerATNSimulator(this,_ATN,_decisionToDFA,_sharedContextCache);
	}

	@Override
	public String getGrammarFileName() { return "yafl.g4"; }

	@Override
	public String[] getRuleNames() { return ruleNames; }

	@Override
	public String getSerializedATN() { return _serializedATN; }

	@Override
	public String[] getChannelNames() { return channelNames; }

	@Override
	public String[] getModeNames() { return modeNames; }

	@Override
	public ATN getATN() { return _ATN; }

	public static final String _serializedATN =
		"\3\u608b\ua72a\u8133\ub9ed\u417c\u3be7\u7786\u5964\2\26\u00a3\b\1\4\2"+
		"\t\2\4\3\t\3\4\4\t\4\4\5\t\5\4\6\t\6\4\7\t\7\4\b\t\b\4\t\t\t\4\n\t\n\4"+
		"\13\t\13\4\f\t\f\4\r\t\r\4\16\t\16\4\17\t\17\4\20\t\20\4\21\t\21\4\22"+
		"\t\22\4\23\t\23\4\24\t\24\4\25\t\25\3\2\3\2\3\2\3\2\3\3\3\3\3\3\3\3\3"+
		"\4\3\4\3\4\3\4\3\4\3\5\3\5\3\5\3\5\3\5\3\5\3\6\3\6\3\6\3\7\3\7\3\7\3\7"+
		"\3\7\3\b\3\b\3\b\3\b\3\b\3\b\3\b\3\t\3\t\3\t\3\t\3\t\3\t\3\t\3\n\3\n\3"+
		"\13\3\13\3\f\3\f\3\r\3\r\3\16\3\16\3\17\3\17\3\20\3\20\3\21\3\21\3\22"+
		"\3\22\6\22g\n\22\r\22\16\22h\3\22\3\22\3\22\7\22n\n\22\f\22\16\22q\13"+
		"\22\5\22s\n\22\3\23\3\23\3\23\3\23\3\24\3\24\7\24{\n\24\f\24\16\24~\13"+
		"\24\3\24\3\24\3\24\3\24\3\25\5\25\u0085\n\25\3\25\3\25\7\25\u0089\n\25"+
		"\f\25\16\25\u008c\13\25\3\25\3\25\3\25\6\25\u0091\n\25\r\25\16\25\u0092"+
		"\3\25\3\25\6\25\u0097\n\25\r\25\16\25\u0098\3\25\6\25\u009c\n\25\r\25"+
		"\16\25\u009d\5\25\u00a0\n\25\5\25\u00a2\n\25\3|\2\26\3\3\5\4\7\5\t\6\13"+
		"\7\r\b\17\t\21\n\23\13\25\f\27\r\31\16\33\17\35\20\37\21!\22#\23%\24\'"+
		"\25)\26\3\2\16\5\2\'\',,\61\61\4\2--//\3\2bb\5\2C\\aac|\6\2\62;C\\aac"+
		"|\5\2\13\f\17\17\"\"\3\2\63;\3\2\62;\4\2DDdd\3\2\62\63\4\2ZZzz\3\2\62"+
		"9\2\u00ae\2\3\3\2\2\2\2\5\3\2\2\2\2\7\3\2\2\2\2\t\3\2\2\2\2\13\3\2\2\2"+
		"\2\r\3\2\2\2\2\17\3\2\2\2\2\21\3\2\2\2\2\23\3\2\2\2\2\25\3\2\2\2\2\27"+
		"\3\2\2\2\2\31\3\2\2\2\2\33\3\2\2\2\2\35\3\2\2\2\2\37\3\2\2\2\2!\3\2\2"+
		"\2\2#\3\2\2\2\2%\3\2\2\2\2\'\3\2\2\2\2)\3\2\2\2\3+\3\2\2\2\5/\3\2\2\2"+
		"\7\63\3\2\2\2\t8\3\2\2\2\13>\3\2\2\2\rA\3\2\2\2\17F\3\2\2\2\21M\3\2\2"+
		"\2\23T\3\2\2\2\25V\3\2\2\2\27X\3\2\2\2\31Z\3\2\2\2\33\\\3\2\2\2\35^\3"+
		"\2\2\2\37`\3\2\2\2!b\3\2\2\2#r\3\2\2\2%t\3\2\2\2\'x\3\2\2\2)\u00a1\3\2"+
		"\2\2+,\7n\2\2,-\7g\2\2-.\7v\2\2.\4\3\2\2\2/\60\7h\2\2\60\61\7w\2\2\61"+
		"\62\7p\2\2\62\6\3\2\2\2\63\64\7f\2\2\64\65\7c\2\2\65\66\7v\2\2\66\67\7"+
		"c\2\2\67\b\3\2\2\289\7e\2\29:\7n\2\2:;\7c\2\2;<\7u\2\2<=\7u\2\2=\n\3\2"+
		"\2\2>?\7k\2\2?@\7h\2\2@\f\3\2\2\2AB\7g\2\2BC\7n\2\2CD\7u\2\2DE\7g\2\2"+
		"E\16\3\2\2\2FG\7t\2\2GH\7g\2\2HI\7v\2\2IJ\7w\2\2JK\7t\2\2KL\7p\2\2L\20"+
		"\3\2\2\2MN\7q\2\2NO\7d\2\2OP\7l\2\2PQ\7g\2\2QR\7e\2\2RS\7v\2\2S\22\3\2"+
		"\2\2TU\t\2\2\2U\24\3\2\2\2VW\t\3\2\2W\26\3\2\2\2XY\7*\2\2Y\30\3\2\2\2"+
		"Z[\7+\2\2[\32\3\2\2\2\\]\7.\2\2]\34\3\2\2\2^_\7<\2\2_\36\3\2\2\2`a\7?"+
		"\2\2a \3\2\2\2bc\7\60\2\2c\"\3\2\2\2df\7b\2\2eg\n\4\2\2fe\3\2\2\2gh\3"+
		"\2\2\2hf\3\2\2\2hi\3\2\2\2ij\3\2\2\2js\7b\2\2ko\t\5\2\2ln\t\6\2\2ml\3"+
		"\2\2\2nq\3\2\2\2om\3\2\2\2op\3\2\2\2ps\3\2\2\2qo\3\2\2\2rd\3\2\2\2rk\3"+
		"\2\2\2s$\3\2\2\2tu\t\7\2\2uv\3\2\2\2vw\b\23\2\2w&\3\2\2\2x|\7%\2\2y{\13"+
		"\2\2\2zy\3\2\2\2{~\3\2\2\2|}\3\2\2\2|z\3\2\2\2}\177\3\2\2\2~|\3\2\2\2"+
		"\177\u0080\7\f\2\2\u0080\u0081\3\2\2\2\u0081\u0082\b\24\2\2\u0082(\3\2"+
		"\2\2\u0083\u0085\t\3\2\2\u0084\u0083\3\2\2\2\u0084\u0085\3\2\2\2\u0085"+
		"\u0086\3\2\2\2\u0086\u008a\t\b\2\2\u0087\u0089\t\t\2\2\u0088\u0087\3\2"+
		"\2\2\u0089\u008c\3\2\2\2\u008a\u0088\3\2\2\2\u008a\u008b\3\2\2\2\u008b"+
		"\u00a2\3\2\2\2\u008c\u008a\3\2\2\2\u008d\u008e\7\62\2\2\u008e\u0090\t"+
		"\n\2\2\u008f\u0091\t\13\2\2\u0090\u008f\3\2\2\2\u0091\u0092\3\2\2\2\u0092"+
		"\u0090\3\2\2\2\u0092\u0093\3\2\2\2\u0093\u00a0\3\2\2\2\u0094\u0096\t\f"+
		"\2\2\u0095\u0097\t\t\2\2\u0096\u0095\3\2\2\2\u0097\u0098\3\2\2\2\u0098"+
		"\u0096\3\2\2\2\u0098\u0099\3\2\2\2\u0099\u00a0\3\2\2\2\u009a\u009c\t\r"+
		"\2\2\u009b\u009a\3\2\2\2\u009c\u009d\3\2\2\2\u009d\u009b\3\2\2\2\u009d"+
		"\u009e\3\2\2\2\u009e\u00a0\3\2\2\2\u009f\u008d\3\2\2\2\u009f\u0094\3\2"+
		"\2\2\u009f\u009b\3\2\2\2\u00a0\u00a2\3\2\2\2\u00a1\u0084\3\2\2\2\u00a1"+
		"\u009f\3\2\2\2\u00a2*\3\2\2\2\16\2hor|\u0084\u008a\u0092\u0098\u009d\u009f"+
		"\u00a1\3\b\2\2";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}