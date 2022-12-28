grammar Yafl;

BUILTIN     : '__builtin__' ;
PRIMITIVE   : '__primitive__';

MODULE      : 'module';
IMPORT      : 'import';
ALIAS       : 'alias';
FUN         : 'fun';
LET         : 'let';
STRUCT      : 'struct';
INTERFACE   : 'interface';
CLASS       : 'class';
OBJECT      : 'object';
ENUM        : 'enum';
LAZY        : 'lazy';
LAMBDA      : '=>';
PIPE_RIGHT  : '|>';
PIPE_MAYBE  : '?>';
NAMESPACE   : NAME '::';

NAME        : ('`' ~'`'+ '`') | ([a-zA-Z_][a-zA-Z0-9_]*) ;
INTEGER     : (('0b' [01]+)|('0o' [0-7]+)|('0x' [0-9a-fA-F]+)|([1-9][0-9]*))([sSlL]|'i8'|'i16'|'i32'|'i64')? ;
STRING      : '"' .*? '"' ;

WS          : [ \t\r\n]+ -> skip ;
COMMENT     : '#' ~'\n'+ -> skip ;



qualifiedName   : NAMESPACE* NAME ;
exprOfTuplePart : (( NAME '=' ) | unpack='*' )? expression ;
exprOfTuple     : '(' ( exprOfTuplePart ',' )* exprOfTuplePart? ')' ;

typeRef         : qualifiedName ;
typePrimitive   : PRIMITIVE NAME ;
typeOfTuplePart : ( NAME ':' )? type ;
typeOfTuple     : '(' ( typeOfTuplePart ',' )* typeOfTuplePart? ')' ;
typeOfLambda    : typeOfTuple ':' type ;

type            : typeRef               # namedType
                | typePrimitive         # primitiveType
                | typeOfTuple           # tupleType
                | typeOfLambda          # lambdaType
                ;

unpackTuplePart : unpackTuple | ( NAME ( ':' type )? ( '=' expression )? ) ;
unpackTuple     : '(' ( unpackTuplePart ',' )* unpackTuplePart? ')' ;

letWithExpr : LET ( unpackTuple | ( NAME ( ':' type )? ) ) '=' expression ;
function    : FUN NAME unpackTuple? ( ':' type )? ( LAMBDA expression )? ;


expression  : BUILTIN NAME params=exprOfTuple?                              # builtinExpr
            | left=expression operator='.' right=NAME                       # dotExpr
            | left=expression params=exprOfTuple                            # callExpr
            | left=expression operator=(PIPE_RIGHT | PIPE_MAYBE) right=expression params=exprOfTuple # applyExpr
            | left=expression operator=( '*' | '/' | '%' ) right=expression # productExpr
            | left=expression operator=( '+' | '-'       ) right=expression # sumExpr
            | left=expression operator=( '<' | '=' | '>' ) right=expression # compareExpr
            | condition=expression '?' left=expression ':' right=expression # ifExpr
            | exprOfTuple                                                   # tupleExpr
            | OBJECT ':' typeRef ( '|' typeRef )* ( '{' function* '}' )?    # objectExpr
            | letWithExpr ';'? expression                                   # letExpr
            | function ';'? expression                                      # functionExpr
            | unpackTuple ( ':' type )? LAMBDA expression                   # lambdaExpr
            | STRING                                                        # stringExpr
            | INTEGER                                                       # integerExpr
            | qualifiedName                                                 # nameExpr
            ;

extends     : ':' typeRef ( ',' typeRef )* ;
module      : MODULE typeRef ;
import_     : IMPORT typeRef ;
interface   : INTERFACE NAME extends? ( '{' function* '}' )? ;
class       : CLASS NAME unpackTuple? extends? ( '{' classMember* '}' )? ;
enum        : ENUM NAME ( '{' ( ( NAME unpackTuple? ) | function )* '}' )? ;
alias       : ALIAS NAME ':' type ;
declaration : letWithExpr | function | interface | class | enum | alias;
classMember :  function ;

root        : module import_* declaration* EOF ;

