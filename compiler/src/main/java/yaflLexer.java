// Generated from /Users/mbrown/Projects/my/yafl/compiler/src/yafl.g4 by ANTLR 4.9.2
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
	static { RuntimeMetaData.checkVersion("4.9.2", RuntimeMetaData.VERSION); }

	protected static final DFA[] _decisionToDFA;
	protected static final PredictionContextCache _sharedContextCache =
		new PredictionContextCache();
	public static final int
		T__0=1, T__1=2, T__2=3, T__3=4, T__4=5, ALIAS=6, VAR=7, FUN=8, DATA=9, 
		CLASS=10, IF=11, ELSE=12, RETURN=13, OBJECT=14, MODULE=15, IMPORT=16, 
		WHERE=17, MULTDIV=18, ADDSUB=19, COMMA=20, COLON=21, DOT=22, NAME=23, 
		WS=24, COMMENT=25, INTEGER=26, STRING=27;
	public static String[] channelNames = {
		"DEFAULT_TOKEN_CHANNEL", "HIDDEN"
	};

	public static String[] modeNames = {
		"DEFAULT_MODE"
	};

	private static String[] makeRuleNames() {
		return new String[] {
			"T__0", "T__1", "T__2", "T__3", "T__4", "ALIAS", "VAR", "FUN", "DATA", 
			"CLASS", "IF", "ELSE", "RETURN", "OBJECT", "MODULE", "IMPORT", "WHERE", 
			"MULTDIV", "ADDSUB", "COMMA", "COLON", "DOT", "NAME", "WS", "COMMENT", 
			"INTEGER", "STRING"
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
		"\3\u608b\ua72a\u8133\ub9ed\u417c\u3be7\u7786\u5964\2\35\u00d6\b\1\4\2"+
		"\t\2\4\3\t\3\4\4\t\4\4\5\t\5\4\6\t\6\4\7\t\7\4\b\t\b\4\t\t\t\4\n\t\n\4"+
		"\13\t\13\4\f\t\f\4\r\t\r\4\16\t\16\4\17\t\17\4\20\t\20\4\21\t\21\4\22"+
		"\t\22\4\23\t\23\4\24\t\24\4\25\t\25\4\26\t\26\4\27\t\27\4\30\t\30\4\31"+
		"\t\31\4\32\t\32\4\33\t\33\4\34\t\34\3\2\3\2\3\3\3\3\3\4\3\4\3\5\3\5\3"+
		"\6\3\6\3\7\3\7\3\7\3\7\3\7\3\7\3\b\3\b\3\b\3\b\3\t\3\t\3\t\3\t\3\t\3\t"+
		"\5\tT\n\t\3\n\3\n\3\n\3\n\3\n\3\13\3\13\3\13\3\13\3\13\3\13\3\f\3\f\3"+
		"\f\3\r\3\r\3\r\3\r\3\r\3\16\3\16\3\16\3\16\3\16\3\16\3\16\3\17\3\17\3"+
		"\17\3\17\3\17\3\17\3\17\3\20\3\20\3\20\3\20\3\20\3\20\3\20\3\21\3\21\3"+
		"\21\3\21\3\21\3\21\3\21\3\22\3\22\3\22\3\22\3\22\3\22\3\23\3\23\3\24\3"+
		"\24\3\25\3\25\3\26\3\26\3\27\3\27\3\30\3\30\6\30\u0097\n\30\r\30\16\30"+
		"\u0098\3\30\3\30\3\30\7\30\u009e\n\30\f\30\16\30\u00a1\13\30\5\30\u00a3"+
		"\n\30\3\31\3\31\3\31\3\31\3\32\3\32\7\32\u00ab\n\32\f\32\16\32\u00ae\13"+
		"\32\3\32\3\32\3\32\3\32\3\33\5\33\u00b5\n\33\3\33\3\33\3\33\3\33\3\33"+
		"\3\33\5\33\u00bd\n\33\3\33\3\33\3\33\3\33\3\33\3\33\3\33\3\33\3\33\3\33"+
		"\3\33\3\33\3\33\5\33\u00cc\n\33\3\34\3\34\7\34\u00d0\n\34\f\34\16\34\u00d3"+
		"\13\34\3\34\3\34\4\u00ac\u00d1\2\35\3\3\5\4\7\5\t\6\13\7\r\b\17\t\21\n"+
		"\23\13\25\f\27\r\31\16\33\17\35\20\37\21!\22#\23%\24\'\25)\26+\27-\30"+
		"/\31\61\32\63\33\65\34\67\35\3\2\n\5\2\'\',,\61\61\4\2--//\3\2bb\5\2C"+
		"\\aac|\6\2\62;C\\aac|\5\2\13\f\17\17\"\"\6\2\62;CHaach\b\2KKNNUUkknnu"+
		"u\2\u00e4\2\3\3\2\2\2\2\5\3\2\2\2\2\7\3\2\2\2\2\t\3\2\2\2\2\13\3\2\2\2"+
		"\2\r\3\2\2\2\2\17\3\2\2\2\2\21\3\2\2\2\2\23\3\2\2\2\2\25\3\2\2\2\2\27"+
		"\3\2\2\2\2\31\3\2\2\2\2\33\3\2\2\2\2\35\3\2\2\2\2\37\3\2\2\2\2!\3\2\2"+
		"\2\2#\3\2\2\2\2%\3\2\2\2\2\'\3\2\2\2\2)\3\2\2\2\2+\3\2\2\2\2-\3\2\2\2"+
		"\2/\3\2\2\2\2\61\3\2\2\2\2\63\3\2\2\2\2\65\3\2\2\2\2\67\3\2\2\2\39\3\2"+
		"\2\2\5;\3\2\2\2\7=\3\2\2\2\t?\3\2\2\2\13A\3\2\2\2\rC\3\2\2\2\17I\3\2\2"+
		"\2\21S\3\2\2\2\23U\3\2\2\2\25Z\3\2\2\2\27`\3\2\2\2\31c\3\2\2\2\33h\3\2"+
		"\2\2\35o\3\2\2\2\37v\3\2\2\2!}\3\2\2\2#\u0084\3\2\2\2%\u008a\3\2\2\2\'"+
		"\u008c\3\2\2\2)\u008e\3\2\2\2+\u0090\3\2\2\2-\u0092\3\2\2\2/\u00a2\3\2"+
		"\2\2\61\u00a4\3\2\2\2\63\u00a8\3\2\2\2\65\u00b4\3\2\2\2\67\u00cd\3\2\2"+
		"\29:\7>\2\2:\4\3\2\2\2;<\7@\2\2<\6\3\2\2\2=>\7*\2\2>\b\3\2\2\2?@\7+\2"+
		"\2@\n\3\2\2\2AB\7?\2\2B\f\3\2\2\2CD\7c\2\2DE\7n\2\2EF\7k\2\2FG\7c\2\2"+
		"GH\7u\2\2H\16\3\2\2\2IJ\7x\2\2JK\7c\2\2KL\7t\2\2L\20\3\2\2\2MN\7h\2\2"+
		"NO\7w\2\2OT\7p\2\2PQ\7n\2\2QR\7g\2\2RT\7v\2\2SM\3\2\2\2SP\3\2\2\2T\22"+
		"\3\2\2\2UV\7f\2\2VW\7c\2\2WX\7v\2\2XY\7c\2\2Y\24\3\2\2\2Z[\7e\2\2[\\\7"+
		"n\2\2\\]\7c\2\2]^\7u\2\2^_\7u\2\2_\26\3\2\2\2`a\7k\2\2ab\7h\2\2b\30\3"+
		"\2\2\2cd\7g\2\2de\7n\2\2ef\7u\2\2fg\7g\2\2g\32\3\2\2\2hi\7t\2\2ij\7g\2"+
		"\2jk\7v\2\2kl\7w\2\2lm\7t\2\2mn\7p\2\2n\34\3\2\2\2op\7q\2\2pq\7d\2\2q"+
		"r\7l\2\2rs\7g\2\2st\7e\2\2tu\7v\2\2u\36\3\2\2\2vw\7o\2\2wx\7q\2\2xy\7"+
		"f\2\2yz\7w\2\2z{\7n\2\2{|\7g\2\2| \3\2\2\2}~\7k\2\2~\177\7o\2\2\177\u0080"+
		"\7r\2\2\u0080\u0081\7q\2\2\u0081\u0082\7t\2\2\u0082\u0083\7v\2\2\u0083"+
		"\"\3\2\2\2\u0084\u0085\7y\2\2\u0085\u0086\7j\2\2\u0086\u0087\7g\2\2\u0087"+
		"\u0088\7t\2\2\u0088\u0089\7g\2\2\u0089$\3\2\2\2\u008a\u008b\t\2\2\2\u008b"+
		"&\3\2\2\2\u008c\u008d\t\3\2\2\u008d(\3\2\2\2\u008e\u008f\7.\2\2\u008f"+
		"*\3\2\2\2\u0090\u0091\7<\2\2\u0091,\3\2\2\2\u0092\u0093\7\60\2\2\u0093"+
		".\3\2\2\2\u0094\u0096\7b\2\2\u0095\u0097\n\4\2\2\u0096\u0095\3\2\2\2\u0097"+
		"\u0098\3\2\2\2\u0098\u0096\3\2\2\2\u0098\u0099\3\2\2\2\u0099\u009a\3\2"+
		"\2\2\u009a\u00a3\7b\2\2\u009b\u009f\t\5\2\2\u009c\u009e\t\6\2\2\u009d"+
		"\u009c\3\2\2\2\u009e\u00a1\3\2\2\2\u009f\u009d\3\2\2\2\u009f\u00a0\3\2"+
		"\2\2\u00a0\u00a3\3\2\2\2\u00a1\u009f\3\2\2\2\u00a2\u0094\3\2\2\2\u00a2"+
		"\u009b\3\2\2\2\u00a3\60\3\2\2\2\u00a4\u00a5\t\7\2\2\u00a5\u00a6\3\2\2"+
		"\2\u00a6\u00a7\b\31\2\2\u00a7\62\3\2\2\2\u00a8\u00ac\7%\2\2\u00a9\u00ab"+
		"\13\2\2\2\u00aa\u00a9\3\2\2\2\u00ab\u00ae\3\2\2\2\u00ac\u00ad\3\2\2\2"+
		"\u00ac\u00aa\3\2\2\2\u00ad\u00af\3\2\2\2\u00ae\u00ac\3\2\2\2\u00af\u00b0"+
		"\7\f\2\2\u00b0\u00b1\3\2\2\2\u00b1\u00b2\b\32\2\2\u00b2\64\3\2\2\2\u00b3"+
		"\u00b5\7/\2\2\u00b4\u00b3\3\2\2\2\u00b4\u00b5\3\2\2\2\u00b5\u00bc\3\2"+
		"\2\2\u00b6\u00b7\7\62\2\2\u00b7\u00bd\7d\2\2\u00b8\u00b9\7\62\2\2\u00b9"+
		"\u00bd\7q\2\2\u00ba\u00bb\7\62\2\2\u00bb\u00bd\7z\2\2\u00bc\u00b6\3\2"+
		"\2\2\u00bc\u00b8\3\2\2\2\u00bc\u00ba\3\2\2\2\u00bc\u00bd\3\2\2\2\u00bd"+
		"\u00be\3\2\2\2\u00be\u00cb\t\b\2\2\u00bf\u00cc\t\t\2\2\u00c0\u00c1\7k"+
		"\2\2\u00c1\u00cc\7:\2\2\u00c2\u00c3\7k\2\2\u00c3\u00c4\7\63\2\2\u00c4"+
		"\u00cc\78\2\2\u00c5\u00c6\7k\2\2\u00c6\u00c7\7\65\2\2\u00c7\u00cc\7\64"+
		"\2\2\u00c8\u00c9\7k\2\2\u00c9\u00ca\78\2\2\u00ca\u00cc\7\66\2\2\u00cb"+
		"\u00bf\3\2\2\2\u00cb\u00c0\3\2\2\2\u00cb\u00c2\3\2\2\2\u00cb\u00c5\3\2"+
		"\2\2\u00cb\u00c8\3\2\2\2\u00cb\u00cc\3\2\2\2\u00cc\66\3\2\2\2\u00cd\u00d1"+
		"\7$\2\2\u00ce\u00d0\13\2\2\2\u00cf\u00ce\3\2\2\2\u00d0\u00d3\3\2\2\2\u00d1"+
		"\u00d2\3\2\2\2\u00d1\u00cf\3\2\2\2\u00d2\u00d4\3\2\2\2\u00d3\u00d1\3\2"+
		"\2\2\u00d4\u00d5\7$\2\2\u00d58\3\2\2\2\f\2S\u0098\u009f\u00a2\u00ac\u00b4"+
		"\u00bc\u00cb\u00d1\3\b\2\2";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}