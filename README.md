# Yet Another Functional Language

## Goals

YAFL is an attempt to realise my ideal programming language and runtime. It should have the following features:

1. Use all cores of the host CPU without any effort from the programmer. This deals with my core itch, that modern languages don't do modern CPUs justice. They are still mostly linear, requiring use of threading libraries to really use all the compute power available. So, no threads, no locks, just straight forward functional code.
2. Hide all aspects of memory management, without a large runtime overhead. Most modern languages do this with a garbage collector of some sort, either tracing or reference counting (or a hybrid in the case of Python). Unfortunately tracing garbage collectors are big and complicated things, so I'll be targeting reference counting.
3. Simple grammer that is familiar to coders from a non-functional background. This is harder, because you just can't have loops if it's functional. Still, we can use a syntax that reminds the coder of familiar languages like Java/C# etc.
4. Generics like in C#, but expressed like in Rust.
5. Still OO, for when it makes sense.

These lofty goals have consequences, in design decisions:

1. It's hard to be pure functional if you want to do actual useful work. Ideally the language will strongly encourage functional design, but make it easy enough to dip into imperative and mutable code near the edges. Doing this without damaging implicit multicore support is going to be interesting. At a high level I am thinking of clearly demarking the mutable and non-mutable zones.
2. In pure functional code, it's easy enough to do things at once implicitly, but it's nice to have a clear rule to follow. That rule is, every tuple construction can implicitly parallel execute the expression building each member value. All function calls include a tuple construction for parameters.
3. Having familiarity in the grammer means no auto currying, so no functional calling style. The functional calling style of a language like Haskell is to my eye unclear and muddies the waters. It also provides no functional advantage over lambdas as a mechanism for currying, but lambdas are cumbersome. There is I hope a middle path.
4. F# supports both functional calling style and tuple calling style. It only supports overloading of functions with the tuple calling style, which makes sense. I consider overloading to be a very important language feature, so this is another reason to not support the functional calling style at all.

And then some things I'll do just because I want to:

1. Whole application compile. No binary libraries, no shared libraries. We just build one monolithic binary that is the application.
2. Very low runtime overhead. I want a simple program to be very small, and I want to target everything from huge multicore platforms down to simple memory constrained embedded systems.
3. Lock free. Ideally. Let's see how this goes.
4. Pure async all the way, under the covers. At a language level you should never realise that it's async. Just write functional linear(ish) code.

## Compiler

The compiler is written in Kotlin, being a language close to my target in terms of syntax. It is written to be as functional as possible, but some areas are outside of my control like the parser generator. The phases of compilation are:

1. Parsing. Using Antlr4. It does a fine job, but is crap at indentation formatting as used by Python. For now it uses curley braces around some structures, until I can solve the indentation parsing problem.
2. Convert to AST. Takes the parse tree and with some tweaks emits an AST (Abstract Syntax Tree). This does not exactly reflect the code as written, but rather the intent of the code. For example, a class definition in the parse tree is placed in the AST as a class and a separate function that acts as the constructor.
3. Resolve type references. Each time a type is referenced in the code it is not well resolved, because we don't know which module it comes from. This phase looks to ensure all provided type references are resolved and well defined by looking them up in the imports path. Aliases are also resolved in this phase, so by the end every available type is concrete. If a type is not available, it is not resolved.
4. Inference. This is a recursive operation that seeks to find the type of all parts of the AST that do not have a well defined type by infering them from neighbouring nodes and/or referencing nodes. It is the success of this step that ensures the correctness of the program.
5. Convert to IR. There is an internal IR (Intermediate Representation) that is similar to LLVM-IR, with some bits removed and others added to bring it closer to the YAFL domain. The AST is converted to IR.
6. ARC. Scan IR to ensure that all references are acquired and released correctly, because we're using reference counting garbage collection, and don't want to think about it. The basic algorithm is to scan the function for all the times that it comes into ownership of a referenced, and at each site add that reference to a cleanup list. At the end of the function the return reference will be acquired, and then all references in the list released. This is a simple and slightly inefficient way of ensuring correct reference counts without accidently releasing the returned object as well. We can do better.
7. Write LLVM-IR. The hop from IR to LLVM-IR is small.
8. Compile with llvm.






