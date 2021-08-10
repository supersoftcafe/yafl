grammar yafl;

LET         : 'let';
FUN         : 'fun';
DATA        : 'data';
CLASS       : 'class';
IF          : 'if';
ELSE        : 'else';
RETURN      : 'return';
OBJECT      : 'object';

MULTDIV     : '*' | '/' | '%';
ADDSUB      : '+' | '-';

OBRACKET    : '(' ;
CBRACKET    : ')' ;
COMMA       : ',' ;
COLON       : ':' ;
EQUALS      : '=' ;
DOT         : '.' ;

NAME        : ('`' ~'`'+ '`') | ([a-zA-Z_][a-zA-Z_0-9]*) ;
WS          : [ \t\r\n] -> skip ;
COMMENT     : '#' .*? '\n' -> skip ;

INTEGER     : [+-]?([1-9][0-9]*)|('0'([bB][0-1]+)|([xX][0-9]+)|([0-7]+)) ;


parameter   : NAME ( COLON type )? ( EQUALS expression )? ;
parameters  : parameter ( COMMA parameters )? ;
types       : type ( COMMA types )? ;

named       : NAME ( DOT named )? ;
tuple       : OBRACKET parameters CBRACKET ;
function    : tuple COLON type ;
type        : function | tuple | named ;

funDecl     : FUN NAME tuple? ( COLON type )? ;
funBody     : ( ( EQUALS expression ) | ( statements? RETURN expression ) ) ;

let         : LET NAME EQUALS expression ;
fun         : funDecl funBody ;
data        : DATA NAME OBRACKET parameters CBRACKET ;
clazz       : CLASS NAME clazzBody ;
clazzBody   : funDecl clazzBody? ;

namedParams : ( NAME EQUALS )? expression ( COMMA namedParams )? ;
expression  : expression DOT NAME                   # dotExpression
            | expression MULTDIV expression         # mulExpression
            | expression ADDSUB  expression         # addExpression
            | IF expression codeBlock ELSE codeBlock# ifExpression
            | OBRACKET codeBlock CBRACKET           # parenthesisedExpression
            | expression ( OBRACKET namedParams CBRACKET ) # invokeExpression
            | INTEGER                               # integerExpression
            | NAME                                  # namedValueExpression
            ;

codeBlock   : statements? expression ;
statements  : (let | fun) statements? ;
declarations: (let | fun | data | clazz ) declarations? ;

root        : declarations? EOF ;

