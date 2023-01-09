// Generated from /Users/mbrown/Projects/yafl/yaflk3/Yafl.g4 by ANTLR 4.10.1
package com.supersoftcafe.yafl.antlr;
import org.antlr.v4.runtime.Lexer;
import org.antlr.v4.runtime.CharStream;
import org.antlr.v4.runtime.Token;
import org.antlr.v4.runtime.TokenStream;
import org.antlr.v4.runtime.*;
import org.antlr.v4.runtime.atn.*;
import org.antlr.v4.runtime.dfa.DFA;
import org.antlr.v4.runtime.misc.*;

@SuppressWarnings({"all", "warnings", "unchecked", "unused", "cast"})
public class YaflLexer extends Lexer {
	static { RuntimeMetaData.checkVersion("4.10.1", RuntimeMetaData.VERSION); }

	protected static final DFA[] _decisionToDFA;
	protected static final PredictionContextCache _sharedContextCache =
		new PredictionContextCache();
	public static final int
		T__0=1, T__1=2, T__2=3, T__3=4, T__4=5, T__5=6, T__6=7, T__7=8, T__8=9, 
		T__9=10, T__10=11, T__11=12, T__12=13, T__13=14, T__14=15, T__15=16, T__16=17, 
		T__17=18, T__18=19, T__19=20, T__20=21, LLVM_IR=22, PRIMITIVE=23, MODULE=24, 
		IMPORT=25, ALIAS=26, FUN=27, LET=28, INTERFACE=29, CLASS=30, OBJECT=31, 
		ENUM=32, LAZY=33, LAMBDA=34, PIPE_RIGHT=35, PIPE_MAYBE=36, NAMESPACE=37, 
		CMP_LE=38, CMP_GE=39, CMP_EQ=40, CMP_NE=41, SHL=42, SHR=43, NAME=44, INTEGER=45, 
		STRING=46, WS=47, COMMENT=48;
	public static String[] channelNames = {
		"DEFAULT_TOKEN_CHANNEL", "HIDDEN"
	};

	public static String[] modeNames = {
		"DEFAULT_MODE"
	};

	private static String[] makeRuleNames() {
		return new String[] {
			"T__0", "T__1", "T__2", "T__3", "T__4", "T__5", "T__6", "T__7", "T__8", 
			"T__9", "T__10", "T__11", "T__12", "T__13", "T__14", "T__15", "T__16", 
			"T__17", "T__18", "T__19", "T__20", "LLVM_IR", "PRIMITIVE", "MODULE", 
			"IMPORT", "ALIAS", "FUN", "LET", "INTERFACE", "CLASS", "OBJECT", "ENUM", 
			"LAZY", "LAMBDA", "PIPE_RIGHT", "PIPE_MAYBE", "NAMESPACE", "CMP_LE", 
			"CMP_GE", "CMP_EQ", "CMP_NE", "SHL", "SHR", "NAME", "INTEGER", "STRING", 
			"WS", "COMMENT"
		};
	}
	public static final String[] ruleNames = makeRuleNames();

	private static String[] makeLiteralNames() {
		return new String[] {
			null, "'('", "','", "')'", "':'", "'['", "']'", "'<'", "'>'", "'.'", 
			"'+'", "'-'", "'*'", "'/'", "'%'", "'&'", "'^'", "'|'", "'?'", "'{'", 
			"'}'", "';'", "'__llvm_ir__'", "'__primitive__'", "'module'", "'import'", 
			"'alias'", "'fun'", "'let'", "'interface'", "'class'", "'object'", "'enum'", 
			"'lazy'", "'=>'", "'|>'", "'?>'", "'::'", "'<='", "'>='", "'='", "'!='", 
			"'<<'", "'>>'"
		};
	}
	private static final String[] _LITERAL_NAMES = makeLiteralNames();
	private static String[] makeSymbolicNames() {
		return new String[] {
			null, null, null, null, null, null, null, null, null, null, null, null, 
			null, null, null, null, null, null, null, null, null, null, "LLVM_IR", 
			"PRIMITIVE", "MODULE", "IMPORT", "ALIAS", "FUN", "LET", "INTERFACE", 
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


	public YaflLexer(CharStream input) {
		super(input);
		_interp = new LexerATNSimulator(this,_ATN,_decisionToDFA,_sharedContextCache);
	}

	@Override
	public String getGrammarFileName() { return "Yafl.g4"; }

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
		"\u0004\u00000\u0157\u0006\uffff\uffff\u0002\u0000\u0007\u0000\u0002\u0001"+
		"\u0007\u0001\u0002\u0002\u0007\u0002\u0002\u0003\u0007\u0003\u0002\u0004"+
		"\u0007\u0004\u0002\u0005\u0007\u0005\u0002\u0006\u0007\u0006\u0002\u0007"+
		"\u0007\u0007\u0002\b\u0007\b\u0002\t\u0007\t\u0002\n\u0007\n\u0002\u000b"+
		"\u0007\u000b\u0002\f\u0007\f\u0002\r\u0007\r\u0002\u000e\u0007\u000e\u0002"+
		"\u000f\u0007\u000f\u0002\u0010\u0007\u0010\u0002\u0011\u0007\u0011\u0002"+
		"\u0012\u0007\u0012\u0002\u0013\u0007\u0013\u0002\u0014\u0007\u0014\u0002"+
		"\u0015\u0007\u0015\u0002\u0016\u0007\u0016\u0002\u0017\u0007\u0017\u0002"+
		"\u0018\u0007\u0018\u0002\u0019\u0007\u0019\u0002\u001a\u0007\u001a\u0002"+
		"\u001b\u0007\u001b\u0002\u001c\u0007\u001c\u0002\u001d\u0007\u001d\u0002"+
		"\u001e\u0007\u001e\u0002\u001f\u0007\u001f\u0002 \u0007 \u0002!\u0007"+
		"!\u0002\"\u0007\"\u0002#\u0007#\u0002$\u0007$\u0002%\u0007%\u0002&\u0007"+
		"&\u0002\'\u0007\'\u0002(\u0007(\u0002)\u0007)\u0002*\u0007*\u0002+\u0007"+
		"+\u0002,\u0007,\u0002-\u0007-\u0002.\u0007.\u0002/\u0007/\u0001\u0000"+
		"\u0001\u0000\u0001\u0001\u0001\u0001\u0001\u0002\u0001\u0002\u0001\u0003"+
		"\u0001\u0003\u0001\u0004\u0001\u0004\u0001\u0005\u0001\u0005\u0001\u0006"+
		"\u0001\u0006\u0001\u0007\u0001\u0007\u0001\b\u0001\b\u0001\t\u0001\t\u0001"+
		"\n\u0001\n\u0001\u000b\u0001\u000b\u0001\f\u0001\f\u0001\r\u0001\r\u0001"+
		"\u000e\u0001\u000e\u0001\u000f\u0001\u000f\u0001\u0010\u0001\u0010\u0001"+
		"\u0011\u0001\u0011\u0001\u0012\u0001\u0012\u0001\u0013\u0001\u0013\u0001"+
		"\u0014\u0001\u0014\u0001\u0015\u0001\u0015\u0001\u0015\u0001\u0015\u0001"+
		"\u0015\u0001\u0015\u0001\u0015\u0001\u0015\u0001\u0015\u0001\u0015\u0001"+
		"\u0015\u0001\u0015\u0001\u0016\u0001\u0016\u0001\u0016\u0001\u0016\u0001"+
		"\u0016\u0001\u0016\u0001\u0016\u0001\u0016\u0001\u0016\u0001\u0016\u0001"+
		"\u0016\u0001\u0016\u0001\u0016\u0001\u0016\u0001\u0017\u0001\u0017\u0001"+
		"\u0017\u0001\u0017\u0001\u0017\u0001\u0017\u0001\u0017\u0001\u0018\u0001"+
		"\u0018\u0001\u0018\u0001\u0018\u0001\u0018\u0001\u0018\u0001\u0018\u0001"+
		"\u0019\u0001\u0019\u0001\u0019\u0001\u0019\u0001\u0019\u0001\u0019\u0001"+
		"\u001a\u0001\u001a\u0001\u001a\u0001\u001a\u0001\u001b\u0001\u001b\u0001"+
		"\u001b\u0001\u001b\u0001\u001c\u0001\u001c\u0001\u001c\u0001\u001c\u0001"+
		"\u001c\u0001\u001c\u0001\u001c\u0001\u001c\u0001\u001c\u0001\u001c\u0001"+
		"\u001d\u0001\u001d\u0001\u001d\u0001\u001d\u0001\u001d\u0001\u001d\u0001"+
		"\u001e\u0001\u001e\u0001\u001e\u0001\u001e\u0001\u001e\u0001\u001e\u0001"+
		"\u001e\u0001\u001f\u0001\u001f\u0001\u001f\u0001\u001f\u0001\u001f\u0001"+
		" \u0001 \u0001 \u0001 \u0001 \u0001!\u0001!\u0001!\u0001\"\u0001\"\u0001"+
		"\"\u0001#\u0001#\u0001#\u0001$\u0001$\u0001$\u0001%\u0001%\u0001%\u0001"+
		"&\u0001&\u0001&\u0001\'\u0001\'\u0001(\u0001(\u0001(\u0001)\u0001)\u0001"+
		")\u0001*\u0001*\u0001*\u0001+\u0001+\u0004+\u0102\b+\u000b+\f+\u0103\u0001"+
		"+\u0001+\u0001+\u0005+\u0109\b+\n+\f+\u010c\t+\u0003+\u010e\b+\u0001,"+
		"\u0001,\u0001,\u0001,\u0004,\u0114\b,\u000b,\f,\u0115\u0001,\u0001,\u0001"+
		",\u0001,\u0004,\u011c\b,\u000b,\f,\u011d\u0001,\u0001,\u0001,\u0001,\u0004"+
		",\u0124\b,\u000b,\f,\u0125\u0001,\u0001,\u0005,\u012a\b,\n,\f,\u012d\t"+
		",\u0001,\u0003,\u0130\b,\u0001,\u0001,\u0001,\u0001,\u0001,\u0001,\u0001"+
		",\u0001,\u0001,\u0001,\u0001,\u0001,\u0003,\u013e\b,\u0001-\u0001-\u0005"+
		"-\u0142\b-\n-\f-\u0145\t-\u0001-\u0001-\u0001.\u0004.\u014a\b.\u000b."+
		"\f.\u014b\u0001.\u0001.\u0001/\u0001/\u0004/\u0152\b/\u000b/\f/\u0153"+
		"\u0001/\u0001/\u0001\u0143\u00000\u0001\u0001\u0003\u0002\u0005\u0003"+
		"\u0007\u0004\t\u0005\u000b\u0006\r\u0007\u000f\b\u0011\t\u0013\n\u0015"+
		"\u000b\u0017\f\u0019\r\u001b\u000e\u001d\u000f\u001f\u0010!\u0011#\u0012"+
		"%\u0013\'\u0014)\u0015+\u0016-\u0017/\u00181\u00193\u001a5\u001b7\u001c"+
		"9\u001d;\u001e=\u001f? A!C\"E#G$I%K&M\'O(Q)S*U+W,Y-[.]/_0\u0001\u0000"+
		"\u000b\u0001\u0000``\u0003\u0000AZ__az\u0004\u000009AZ__az\u0001\u0000"+
		"01\u0001\u000007\u0003\u000009AFaf\u0001\u000019\u0001\u000009\u0004\u0000"+
		"LLSSllss\u0003\u0000\t\n\r\r  \u0001\u0000\n\n\u0169\u0000\u0001\u0001"+
		"\u0000\u0000\u0000\u0000\u0003\u0001\u0000\u0000\u0000\u0000\u0005\u0001"+
		"\u0000\u0000\u0000\u0000\u0007\u0001\u0000\u0000\u0000\u0000\t\u0001\u0000"+
		"\u0000\u0000\u0000\u000b\u0001\u0000\u0000\u0000\u0000\r\u0001\u0000\u0000"+
		"\u0000\u0000\u000f\u0001\u0000\u0000\u0000\u0000\u0011\u0001\u0000\u0000"+
		"\u0000\u0000\u0013\u0001\u0000\u0000\u0000\u0000\u0015\u0001\u0000\u0000"+
		"\u0000\u0000\u0017\u0001\u0000\u0000\u0000\u0000\u0019\u0001\u0000\u0000"+
		"\u0000\u0000\u001b\u0001\u0000\u0000\u0000\u0000\u001d\u0001\u0000\u0000"+
		"\u0000\u0000\u001f\u0001\u0000\u0000\u0000\u0000!\u0001\u0000\u0000\u0000"+
		"\u0000#\u0001\u0000\u0000\u0000\u0000%\u0001\u0000\u0000\u0000\u0000\'"+
		"\u0001\u0000\u0000\u0000\u0000)\u0001\u0000\u0000\u0000\u0000+\u0001\u0000"+
		"\u0000\u0000\u0000-\u0001\u0000\u0000\u0000\u0000/\u0001\u0000\u0000\u0000"+
		"\u00001\u0001\u0000\u0000\u0000\u00003\u0001\u0000\u0000\u0000\u00005"+
		"\u0001\u0000\u0000\u0000\u00007\u0001\u0000\u0000\u0000\u00009\u0001\u0000"+
		"\u0000\u0000\u0000;\u0001\u0000\u0000\u0000\u0000=\u0001\u0000\u0000\u0000"+
		"\u0000?\u0001\u0000\u0000\u0000\u0000A\u0001\u0000\u0000\u0000\u0000C"+
		"\u0001\u0000\u0000\u0000\u0000E\u0001\u0000\u0000\u0000\u0000G\u0001\u0000"+
		"\u0000\u0000\u0000I\u0001\u0000\u0000\u0000\u0000K\u0001\u0000\u0000\u0000"+
		"\u0000M\u0001\u0000\u0000\u0000\u0000O\u0001\u0000\u0000\u0000\u0000Q"+
		"\u0001\u0000\u0000\u0000\u0000S\u0001\u0000\u0000\u0000\u0000U\u0001\u0000"+
		"\u0000\u0000\u0000W\u0001\u0000\u0000\u0000\u0000Y\u0001\u0000\u0000\u0000"+
		"\u0000[\u0001\u0000\u0000\u0000\u0000]\u0001\u0000\u0000\u0000\u0000_"+
		"\u0001\u0000\u0000\u0000\u0001a\u0001\u0000\u0000\u0000\u0003c\u0001\u0000"+
		"\u0000\u0000\u0005e\u0001\u0000\u0000\u0000\u0007g\u0001\u0000\u0000\u0000"+
		"\ti\u0001\u0000\u0000\u0000\u000bk\u0001\u0000\u0000\u0000\rm\u0001\u0000"+
		"\u0000\u0000\u000fo\u0001\u0000\u0000\u0000\u0011q\u0001\u0000\u0000\u0000"+
		"\u0013s\u0001\u0000\u0000\u0000\u0015u\u0001\u0000\u0000\u0000\u0017w"+
		"\u0001\u0000\u0000\u0000\u0019y\u0001\u0000\u0000\u0000\u001b{\u0001\u0000"+
		"\u0000\u0000\u001d}\u0001\u0000\u0000\u0000\u001f\u007f\u0001\u0000\u0000"+
		"\u0000!\u0081\u0001\u0000\u0000\u0000#\u0083\u0001\u0000\u0000\u0000%"+
		"\u0085\u0001\u0000\u0000\u0000\'\u0087\u0001\u0000\u0000\u0000)\u0089"+
		"\u0001\u0000\u0000\u0000+\u008b\u0001\u0000\u0000\u0000-\u0097\u0001\u0000"+
		"\u0000\u0000/\u00a5\u0001\u0000\u0000\u00001\u00ac\u0001\u0000\u0000\u0000"+
		"3\u00b3\u0001\u0000\u0000\u00005\u00b9\u0001\u0000\u0000\u00007\u00bd"+
		"\u0001\u0000\u0000\u00009\u00c1\u0001\u0000\u0000\u0000;\u00cb\u0001\u0000"+
		"\u0000\u0000=\u00d1\u0001\u0000\u0000\u0000?\u00d8\u0001\u0000\u0000\u0000"+
		"A\u00dd\u0001\u0000\u0000\u0000C\u00e2\u0001\u0000\u0000\u0000E\u00e5"+
		"\u0001\u0000\u0000\u0000G\u00e8\u0001\u0000\u0000\u0000I\u00eb\u0001\u0000"+
		"\u0000\u0000K\u00ee\u0001\u0000\u0000\u0000M\u00f1\u0001\u0000\u0000\u0000"+
		"O\u00f4\u0001\u0000\u0000\u0000Q\u00f6\u0001\u0000\u0000\u0000S\u00f9"+
		"\u0001\u0000\u0000\u0000U\u00fc\u0001\u0000\u0000\u0000W\u010d\u0001\u0000"+
		"\u0000\u0000Y\u012f\u0001\u0000\u0000\u0000[\u013f\u0001\u0000\u0000\u0000"+
		"]\u0149\u0001\u0000\u0000\u0000_\u014f\u0001\u0000\u0000\u0000ab\u0005"+
		"(\u0000\u0000b\u0002\u0001\u0000\u0000\u0000cd\u0005,\u0000\u0000d\u0004"+
		"\u0001\u0000\u0000\u0000ef\u0005)\u0000\u0000f\u0006\u0001\u0000\u0000"+
		"\u0000gh\u0005:\u0000\u0000h\b\u0001\u0000\u0000\u0000ij\u0005[\u0000"+
		"\u0000j\n\u0001\u0000\u0000\u0000kl\u0005]\u0000\u0000l\f\u0001\u0000"+
		"\u0000\u0000mn\u0005<\u0000\u0000n\u000e\u0001\u0000\u0000\u0000op\u0005"+
		">\u0000\u0000p\u0010\u0001\u0000\u0000\u0000qr\u0005.\u0000\u0000r\u0012"+
		"\u0001\u0000\u0000\u0000st\u0005+\u0000\u0000t\u0014\u0001\u0000\u0000"+
		"\u0000uv\u0005-\u0000\u0000v\u0016\u0001\u0000\u0000\u0000wx\u0005*\u0000"+
		"\u0000x\u0018\u0001\u0000\u0000\u0000yz\u0005/\u0000\u0000z\u001a\u0001"+
		"\u0000\u0000\u0000{|\u0005%\u0000\u0000|\u001c\u0001\u0000\u0000\u0000"+
		"}~\u0005&\u0000\u0000~\u001e\u0001\u0000\u0000\u0000\u007f\u0080\u0005"+
		"^\u0000\u0000\u0080 \u0001\u0000\u0000\u0000\u0081\u0082\u0005|\u0000"+
		"\u0000\u0082\"\u0001\u0000\u0000\u0000\u0083\u0084\u0005?\u0000\u0000"+
		"\u0084$\u0001\u0000\u0000\u0000\u0085\u0086\u0005{\u0000\u0000\u0086&"+
		"\u0001\u0000\u0000\u0000\u0087\u0088\u0005}\u0000\u0000\u0088(\u0001\u0000"+
		"\u0000\u0000\u0089\u008a\u0005;\u0000\u0000\u008a*\u0001\u0000\u0000\u0000"+
		"\u008b\u008c\u0005_\u0000\u0000\u008c\u008d\u0005_\u0000\u0000\u008d\u008e"+
		"\u0005l\u0000\u0000\u008e\u008f\u0005l\u0000\u0000\u008f\u0090\u0005v"+
		"\u0000\u0000\u0090\u0091\u0005m\u0000\u0000\u0091\u0092\u0005_\u0000\u0000"+
		"\u0092\u0093\u0005i\u0000\u0000\u0093\u0094\u0005r\u0000\u0000\u0094\u0095"+
		"\u0005_\u0000\u0000\u0095\u0096\u0005_\u0000\u0000\u0096,\u0001\u0000"+
		"\u0000\u0000\u0097\u0098\u0005_\u0000\u0000\u0098\u0099\u0005_\u0000\u0000"+
		"\u0099\u009a\u0005p\u0000\u0000\u009a\u009b\u0005r\u0000\u0000\u009b\u009c"+
		"\u0005i\u0000\u0000\u009c\u009d\u0005m\u0000\u0000\u009d\u009e\u0005i"+
		"\u0000\u0000\u009e\u009f\u0005t\u0000\u0000\u009f\u00a0\u0005i\u0000\u0000"+
		"\u00a0\u00a1\u0005v\u0000\u0000\u00a1\u00a2\u0005e\u0000\u0000\u00a2\u00a3"+
		"\u0005_\u0000\u0000\u00a3\u00a4\u0005_\u0000\u0000\u00a4.\u0001\u0000"+
		"\u0000\u0000\u00a5\u00a6\u0005m\u0000\u0000\u00a6\u00a7\u0005o\u0000\u0000"+
		"\u00a7\u00a8\u0005d\u0000\u0000\u00a8\u00a9\u0005u\u0000\u0000\u00a9\u00aa"+
		"\u0005l\u0000\u0000\u00aa\u00ab\u0005e\u0000\u0000\u00ab0\u0001\u0000"+
		"\u0000\u0000\u00ac\u00ad\u0005i\u0000\u0000\u00ad\u00ae\u0005m\u0000\u0000"+
		"\u00ae\u00af\u0005p\u0000\u0000\u00af\u00b0\u0005o\u0000\u0000\u00b0\u00b1"+
		"\u0005r\u0000\u0000\u00b1\u00b2\u0005t\u0000\u0000\u00b22\u0001\u0000"+
		"\u0000\u0000\u00b3\u00b4\u0005a\u0000\u0000\u00b4\u00b5\u0005l\u0000\u0000"+
		"\u00b5\u00b6\u0005i\u0000\u0000\u00b6\u00b7\u0005a\u0000\u0000\u00b7\u00b8"+
		"\u0005s\u0000\u0000\u00b84\u0001\u0000\u0000\u0000\u00b9\u00ba\u0005f"+
		"\u0000\u0000\u00ba\u00bb\u0005u\u0000\u0000\u00bb\u00bc\u0005n\u0000\u0000"+
		"\u00bc6\u0001\u0000\u0000\u0000\u00bd\u00be\u0005l\u0000\u0000\u00be\u00bf"+
		"\u0005e\u0000\u0000\u00bf\u00c0\u0005t\u0000\u0000\u00c08\u0001\u0000"+
		"\u0000\u0000\u00c1\u00c2\u0005i\u0000\u0000\u00c2\u00c3\u0005n\u0000\u0000"+
		"\u00c3\u00c4\u0005t\u0000\u0000\u00c4\u00c5\u0005e\u0000\u0000\u00c5\u00c6"+
		"\u0005r\u0000\u0000\u00c6\u00c7\u0005f\u0000\u0000\u00c7\u00c8\u0005a"+
		"\u0000\u0000\u00c8\u00c9\u0005c\u0000\u0000\u00c9\u00ca\u0005e\u0000\u0000"+
		"\u00ca:\u0001\u0000\u0000\u0000\u00cb\u00cc\u0005c\u0000\u0000\u00cc\u00cd"+
		"\u0005l\u0000\u0000\u00cd\u00ce\u0005a\u0000\u0000\u00ce\u00cf\u0005s"+
		"\u0000\u0000\u00cf\u00d0\u0005s\u0000\u0000\u00d0<\u0001\u0000\u0000\u0000"+
		"\u00d1\u00d2\u0005o\u0000\u0000\u00d2\u00d3\u0005b\u0000\u0000\u00d3\u00d4"+
		"\u0005j\u0000\u0000\u00d4\u00d5\u0005e\u0000\u0000\u00d5\u00d6\u0005c"+
		"\u0000\u0000\u00d6\u00d7\u0005t\u0000\u0000\u00d7>\u0001\u0000\u0000\u0000"+
		"\u00d8\u00d9\u0005e\u0000\u0000\u00d9\u00da\u0005n\u0000\u0000\u00da\u00db"+
		"\u0005u\u0000\u0000\u00db\u00dc\u0005m\u0000\u0000\u00dc@\u0001\u0000"+
		"\u0000\u0000\u00dd\u00de\u0005l\u0000\u0000\u00de\u00df\u0005a\u0000\u0000"+
		"\u00df\u00e0\u0005z\u0000\u0000\u00e0\u00e1\u0005y\u0000\u0000\u00e1B"+
		"\u0001\u0000\u0000\u0000\u00e2\u00e3\u0005=\u0000\u0000\u00e3\u00e4\u0005"+
		">\u0000\u0000\u00e4D\u0001\u0000\u0000\u0000\u00e5\u00e6\u0005|\u0000"+
		"\u0000\u00e6\u00e7\u0005>\u0000\u0000\u00e7F\u0001\u0000\u0000\u0000\u00e8"+
		"\u00e9\u0005?\u0000\u0000\u00e9\u00ea\u0005>\u0000\u0000\u00eaH\u0001"+
		"\u0000\u0000\u0000\u00eb\u00ec\u0005:\u0000\u0000\u00ec\u00ed\u0005:\u0000"+
		"\u0000\u00edJ\u0001\u0000\u0000\u0000\u00ee\u00ef\u0005<\u0000\u0000\u00ef"+
		"\u00f0\u0005=\u0000\u0000\u00f0L\u0001\u0000\u0000\u0000\u00f1\u00f2\u0005"+
		">\u0000\u0000\u00f2\u00f3\u0005=\u0000\u0000\u00f3N\u0001\u0000\u0000"+
		"\u0000\u00f4\u00f5\u0005=\u0000\u0000\u00f5P\u0001\u0000\u0000\u0000\u00f6"+
		"\u00f7\u0005!\u0000\u0000\u00f7\u00f8\u0005=\u0000\u0000\u00f8R\u0001"+
		"\u0000\u0000\u0000\u00f9\u00fa\u0005<\u0000\u0000\u00fa\u00fb\u0005<\u0000"+
		"\u0000\u00fbT\u0001\u0000\u0000\u0000\u00fc\u00fd\u0005>\u0000\u0000\u00fd"+
		"\u00fe\u0005>\u0000\u0000\u00feV\u0001\u0000\u0000\u0000\u00ff\u0101\u0005"+
		"`\u0000\u0000\u0100\u0102\b\u0000\u0000\u0000\u0101\u0100\u0001\u0000"+
		"\u0000\u0000\u0102\u0103\u0001\u0000\u0000\u0000\u0103\u0101\u0001\u0000"+
		"\u0000\u0000\u0103\u0104\u0001\u0000\u0000\u0000\u0104\u0105\u0001\u0000"+
		"\u0000\u0000\u0105\u010e\u0005`\u0000\u0000\u0106\u010a\u0007\u0001\u0000"+
		"\u0000\u0107\u0109\u0007\u0002\u0000\u0000\u0108\u0107\u0001\u0000\u0000"+
		"\u0000\u0109\u010c\u0001\u0000\u0000\u0000\u010a\u0108\u0001\u0000\u0000"+
		"\u0000\u010a\u010b\u0001\u0000\u0000\u0000\u010b\u010e\u0001\u0000\u0000"+
		"\u0000\u010c\u010a\u0001\u0000\u0000\u0000\u010d\u00ff\u0001\u0000\u0000"+
		"\u0000\u010d\u0106\u0001\u0000\u0000\u0000\u010eX\u0001\u0000\u0000\u0000"+
		"\u010f\u0110\u00050\u0000\u0000\u0110\u0111\u0005b\u0000\u0000\u0111\u0113"+
		"\u0001\u0000\u0000\u0000\u0112\u0114\u0007\u0003\u0000\u0000\u0113\u0112"+
		"\u0001\u0000\u0000\u0000\u0114\u0115\u0001\u0000\u0000\u0000\u0115\u0113"+
		"\u0001\u0000\u0000\u0000\u0115\u0116\u0001\u0000\u0000\u0000\u0116\u0130"+
		"\u0001\u0000\u0000\u0000\u0117\u0118\u00050\u0000\u0000\u0118\u0119\u0005"+
		"o\u0000\u0000\u0119\u011b\u0001\u0000\u0000\u0000\u011a\u011c\u0007\u0004"+
		"\u0000\u0000\u011b\u011a\u0001\u0000\u0000\u0000\u011c\u011d\u0001\u0000"+
		"\u0000\u0000\u011d\u011b\u0001\u0000\u0000\u0000\u011d\u011e\u0001\u0000"+
		"\u0000\u0000\u011e\u0130\u0001\u0000\u0000\u0000\u011f\u0120\u00050\u0000"+
		"\u0000\u0120\u0121\u0005x\u0000\u0000\u0121\u0123\u0001\u0000\u0000\u0000"+
		"\u0122\u0124\u0007\u0005\u0000\u0000\u0123\u0122\u0001\u0000\u0000\u0000"+
		"\u0124\u0125\u0001\u0000\u0000\u0000\u0125\u0123\u0001\u0000\u0000\u0000"+
		"\u0125\u0126\u0001\u0000\u0000\u0000\u0126\u0130\u0001\u0000\u0000\u0000"+
		"\u0127\u012b\u0007\u0006\u0000\u0000\u0128\u012a\u0007\u0007\u0000\u0000"+
		"\u0129\u0128\u0001\u0000\u0000\u0000\u012a\u012d\u0001\u0000\u0000\u0000"+
		"\u012b\u0129\u0001\u0000\u0000\u0000\u012b\u012c\u0001\u0000\u0000\u0000"+
		"\u012c\u0130\u0001\u0000\u0000\u0000\u012d\u012b\u0001\u0000\u0000\u0000"+
		"\u012e\u0130\u00050\u0000\u0000\u012f\u010f\u0001\u0000\u0000\u0000\u012f"+
		"\u0117\u0001\u0000\u0000\u0000\u012f\u011f\u0001\u0000\u0000\u0000\u012f"+
		"\u0127\u0001\u0000\u0000\u0000\u012f\u012e\u0001\u0000\u0000\u0000\u0130"+
		"\u013d\u0001\u0000\u0000\u0000\u0131\u013e\u0007\b\u0000\u0000\u0132\u0133"+
		"\u0005i\u0000\u0000\u0133\u013e\u00058\u0000\u0000\u0134\u0135\u0005i"+
		"\u0000\u0000\u0135\u0136\u00051\u0000\u0000\u0136\u013e\u00056\u0000\u0000"+
		"\u0137\u0138\u0005i\u0000\u0000\u0138\u0139\u00053\u0000\u0000\u0139\u013e"+
		"\u00052\u0000\u0000\u013a\u013b\u0005i\u0000\u0000\u013b\u013c\u00056"+
		"\u0000\u0000\u013c\u013e\u00054\u0000\u0000\u013d\u0131\u0001\u0000\u0000"+
		"\u0000\u013d\u0132\u0001\u0000\u0000\u0000\u013d\u0134\u0001\u0000\u0000"+
		"\u0000\u013d\u0137\u0001\u0000\u0000\u0000\u013d\u013a\u0001\u0000\u0000"+
		"\u0000\u013d\u013e\u0001\u0000\u0000\u0000\u013eZ\u0001\u0000\u0000\u0000"+
		"\u013f\u0143\u0005\"\u0000\u0000\u0140\u0142\t\u0000\u0000\u0000\u0141"+
		"\u0140\u0001\u0000\u0000\u0000\u0142\u0145\u0001\u0000\u0000\u0000\u0143"+
		"\u0144\u0001\u0000\u0000\u0000\u0143\u0141\u0001\u0000\u0000\u0000\u0144"+
		"\u0146\u0001\u0000\u0000\u0000\u0145\u0143\u0001\u0000\u0000\u0000\u0146"+
		"\u0147\u0005\"\u0000\u0000\u0147\\\u0001\u0000\u0000\u0000\u0148\u014a"+
		"\u0007\t\u0000\u0000\u0149\u0148\u0001\u0000\u0000\u0000\u014a\u014b\u0001"+
		"\u0000\u0000\u0000\u014b\u0149\u0001\u0000\u0000\u0000\u014b\u014c\u0001"+
		"\u0000\u0000\u0000\u014c\u014d\u0001\u0000\u0000\u0000\u014d\u014e\u0006"+
		".\u0000\u0000\u014e^\u0001\u0000\u0000\u0000\u014f\u0151\u0005#\u0000"+
		"\u0000\u0150\u0152\b\n\u0000\u0000\u0151\u0150\u0001\u0000\u0000\u0000"+
		"\u0152\u0153\u0001\u0000\u0000\u0000\u0153\u0151\u0001\u0000\u0000\u0000"+
		"\u0153\u0154\u0001\u0000\u0000\u0000\u0154\u0155\u0001\u0000\u0000\u0000"+
		"\u0155\u0156\u0006/\u0000\u0000\u0156`\u0001\u0000\u0000\u0000\r\u0000"+
		"\u0103\u010a\u010d\u0115\u011d\u0125\u012b\u012f\u013d\u0143\u014b\u0153"+
		"\u0001\u0006\u0000\u0000";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}