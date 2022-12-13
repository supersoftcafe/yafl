# Yet Another Functional Language

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





