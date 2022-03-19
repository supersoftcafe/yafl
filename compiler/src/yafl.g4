grammar yafl;


// Add ';' as optional separator, just for beauty on one liners.
//    Between compount statements
//    Between when cases      when x; 0 -> 'a'; _ -> 'b'
// Add '{' '}' as optional block markers, where nesting causes ambiguity


ALIAS       : 'alias';
VAR         : 'var';
FUN         : 'fun' | 'let';
DATA        : 'data';
CLASS       : 'class';

IF          : 'if';
ELSE        : 'else';
RETURN      : 'return';
OBJECT      : 'object';
MODULE      : 'module';
IMPORT      : 'import';
WHERE       : 'where';

MULTDIV     : '*' | '/' | '%';
ADDSUB      : '+' | '-';

COMMA       : ',' ;
COLON       : ':' ;
DOT         : '.' ;


NAME        : ('`' ~'`'+ '`') | ([a-zA-Z_][a-zA-Z_0-9]*) ;
WS          : [ \t\r\n] -> skip ;
COMMENT     : '#' .*? '\n' -> skip ;

INTEGER     : '-'?('0b'|'0o'|'0x')?[0-9a-fA-F_]([sSiIlL]|'i8'|'i16'|'i32'|'i64')? ;
STRING      : '"' .*? '"' ;

simpleTypeName : NAME ( DOT NAME )* ;
genericParams : '<' namedType ( COMMA namedType )* '>' ;
namedType   : simpleTypeName genericParams? ;
tupleType   : '(' parameter ( COMMA parameter )* ')' ;
type        : namedType | tupleType ;

parameter   : NAME ( COLON type )? ( '=' expression )? ;
whereExpr   : WHERE expression ;

alias       : ALIAS NAME namedType COLON type ;
var         : VAR NAME ( COLON type ) | ( '=' expression ) ;
fun         : FUN NAME tupleType? ( COLON type )? ( ( '=' expression whereExpr? ) | ( whereExpr? statements* RETURN expression ) ) ;
data        : DATA NAME tupleType ;

namedParams : COMMA? ( NAME '=' )? expression ;
expression  : expression DOT NAME                   # dotExpression
            | expression ( '(' namedParams* ')' )   # invokeExpression
            | expression MULTDIV expression         # mulExpression
            | expression ADDSUB  expression         # addExpression
            | expression ( '<' | '>' | '=' ) expression # compareExpression
            | IF expression codeBlock ELSE codeBlock# ifExpression
            | '(' codeBlock ')'                     # parenthesisedExpression
            | INTEGER                               # integerExpression
            | STRING                                # stringExpression
            | NAME                                  # namedValueExpression
            ;

codeBlock   : statements* expression ;
statements  : var | fun ;
declarations: var | fun | data | alias ;

module      : MODULE simpleTypeName ;
imports     : IMPORT simpleTypeName ;
modules     : module imports* declarations* ;

root        : modules* EOF ;



