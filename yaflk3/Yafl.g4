grammar Yafl;

LLVM_IR     : '__llvm_ir__';
PRIMITIVE   : '__primitive__';
ASSERT      : '__assert__';
RAW_POINTER : '__raw_pointer__';
PARALLEL    : '__parallel__';

MODULE      : 'module';
IMPORT      : 'import';
ALIAS       : 'alias';
FUN         : 'fun';
LET         : 'let';
INTERFACE   : 'interface';
CLASS       : 'class';
OBJECT      : 'object';
ENUM        : 'enum';
LAZY        : 'lazy';
LAMBDA      : '=>';
PIPE_RIGHT  : '|>';
PIPE_MAYBE  : '?>';
NAMESPACE   : '::';
CMP_LE      : '<=';
CMP_GE      : '>=';
CMP_EQ      : '==';
CMP_NE      : '!=';
SHL         : '<<';
SHR         : '>>';
POW         : '**';

NAME        : ('`' ~'`'+ '`') | ([a-zA-Z_][a-zA-Z0-9_]*) ;
INTEGER     : (('0b' [01]+)|('0o' [0-7]+)|('0x' [0-9a-fA-F]+)|([1-9][0-9]*)|'0')([sSlL]|'i8'|'i16'|'i32'|'i64')? ;
STRING      : '"' .*? '"' ;

WS          : [ \t\r\n]+ -> skip ;
COMMENT     : '#' ~'\n'+ -> skip ;



qualifiedName   : ( NAME NAMESPACE )* NAME ;
exprOfTuplePart : ( NAME '=' )? expression ;
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

attributes      : '[' NAME* ']' ;

unpackTuplePart : unpackTuple | ( NAME ( '[' ( expression CMP_LE )? INTEGER ']' )? ( ':' type )? ) ;
unpackTuple     : '(' ( unpackTuplePart ',' )* unpackTuplePart? ')' ;

letWithExpr : LET ( unpackTuple | ( NAME ( ':' type )? ) ) '=' expression ';'? ;
function    : FUN attributes? (extensionType=typeRef '.' )? NAME unpackTuple? ( ':' type )? ( LAMBDA expression )? ';'? ;

expression  : LLVM_IR '<' type '>' '(' pattern=STRING ( ',' expression )* ')' # llvmirExpr
            | ASSERT '(' value=expression ',' condition=expression ',' message=STRING ')' # assertExpr
            | RAW_POINTER '(' value=expression ')'                            # rawPointerExpr
            | left=expression operator='.' right=NAME                         # dotExpr
            | left=expression params=exprOfTuple                              # callExpr
            | PARALLEL params=exprOfTuple                                     # parallelExpr
            | left=expression '[' right=expression ']'                        # arrayLookupExpr
            | left=expression operator=(PIPE_RIGHT | PIPE_MAYBE) right=expression params=exprOfTuple # applyExpr

            |                 operator=(          '+' | '-'          ) right=expression # unaryExpr
            | left=expression operator=POW                             right=expression # powerExpr
            | left=expression operator=(          '*' | '/' | '%'    ) right=expression # productExpr
            | left=expression operator=(          '+' | '-'          ) right=expression # sumExpr
            | left=expression operator=( SHL                | SHR    ) right=expression # shiftExpr
            | left=expression operator=( CMP_LE | '<' | '>' | CMP_GE ) right=expression # compareExpr
            | left=expression operator=( CMP_EQ |             CMP_NE ) right=expression # equalExpr
            | left=expression operator=           '&'                  right=expression # bitAndExpr
            | left=expression operator=           '^'                  right=expression # bitXorExpr
            | left=expression operator=           '|'                  right=expression # bitOrExpr

            | condition=expression ( '?' left=expression ':' right=expression ) # ifExpr
            | exprOfTuple                                                   # tupleExpr
            | OBJECT ':' typeRef ( '|' typeRef )* ( '{' function* '}' )?    # objectExpr
            | letWithExpr ';'? expression                                   # letExpr
            | function ';'? expression                                      # functionExpr
            | unpackTuple ( ':' type )? LAMBDA expression                   # lambdaExpr
            | '[' expression ( ',' expression )* ','? ']'                   # newArrayExpr
            | STRING                                                        # stringExpr
            | INTEGER                                                       # integerExpr
            | qualifiedName                                                 # nameExpr
            ;



//classParam  : NAME ( '[' INTEGER ']' )? ( ':' type )? ( '=' expression )? ;
//classParams : '(' ( classParam ',' )* classParam? ')' ;

extends     : ':' typeRef ( ',' typeRef )* ;
module      : MODULE typeRef ';'? ;
import_     : IMPORT typeRef ';'? ;
interface   : INTERFACE NAME extends? ( '{' function* '}' )? ';'? ;
class       : CLASS NAME unpackTuple? extends? ( '{' classMember* '}' )? ';'? ;
enum        : ENUM NAME ( '{' ( ( NAME unpackTuple? ) | function )* '}' )? ';'? ;
alias       : ALIAS NAME ':' type ';'? ;
declaration : letWithExpr | function | interface | class | enum | alias;
classMember : function ;

root        : module import_* declaration* EOF ;

