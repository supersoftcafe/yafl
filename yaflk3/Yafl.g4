grammar Yafl;

MODULE      : 'module';
USING       : 'using';
FUN         : 'fun';
LET         : 'let';
STRUCT      : 'struct';
INTERFACE   : 'interface';
CLASS       : 'class';
OBJECT      : 'object';
ENUM        : 'enum';
LAZY        : 'lazy';
DASH_ARROW  : '->';
APPLY       : '|>';

NAME        : ('`' ~'`'+ '`') | ([a-zA-Z_][a-zA-Z0-9_]*) ;
INTEGER     : '-'?(('0b' [01]+)|('0o' [0-7]+)|('0x' [0-9a-fA-F]+)|([1-9][0-9]*))([sSiIlL]|'i8'|'i16'|'i32'|'i64')? ;
STRING      : '"' .*? '"' ;

WS          : [ \t\r\n]+ -> skip ;
COMMENT     : '#' ~'\n'+ -> skip ;



exprOfTuplePart : ( NAME '=' )? expression ;
exprOfTuple     : '(' ( exprOfTuplePart ',' )* exprOfTuplePart? ')' ;

typeRef         : NAME ( '.' NAME )* ;
typeOfTuplePart : NAME ( ':' type )? ( '=' expression )? ;
typeOfTuple     : '(' ( typeOfTuplePart ',' )* typeOfTuplePart? ')' ;
typeOfLambda    : typeOfTuple DASH_ARROW type ;

type            : typeRef               # namedType
                | typeOfTuple           # tupleType
                | typeOfLambda          # lambdaType
                ;

expression  : left=expression operator='.' name=NAME                        # dotExpr
            | left=expression params=exprOfTuple                            # callExpr
            | left=expression APPLY right=expression params=exprOfTuple     # applyExpr
            | left=expression operator=( '*' | '/' | '%' ) right=expression # productExpr
            | left=expression operator=( '+' | '-'       ) right=expression # sumExpr
            | left=expression operator=( '<' | '=' | '>' ) right=expression # compareExpr
            | condition=expression '?' left=expression ':' right=expression # ifExpr
            | exprOfTuple                                                   # tupleExpr
            | OBJECT ':' typeRef ( '|' typeRef )* ( '{' function* '}' )?    # objectExpr
            | typeOfTuple DASH_ARROW expression                             # lambdaExpr
            | STRING                                                        # stringExpr
            | INTEGER                                                       # integerExpr
            | NAME                                                          # nameExpr
            ;

module      : MODULE typeRef ;
using       : USING typeRef ;
function    : FUN NAME typeOfTuple? ( ':' type )? ( '=' expression )? ;
letWithExpr : LET NAME ( ':' type )? '=' expression ;
interface   : INTERFACE NAME ( ':' typeRef ( '|' typeRef )* )? ( '{' function+ '}' )? ;
class       : CLASS NAME typeOfTuple? ( ':' typeRef ( '|' typeRef )* )? ( '{' function* '}' )? ;
struct      : STRUCT NAME typeOfTuple ( '{' function* '}' )? ;
enum        : ENUM NAME ( '{' ( ( NAME typeOfTuple? ) | function )* '}' )? ;
declaration : letWithExpr | function | interface | class | struct | enum ;

root        : module using* declaration* EOF ;

