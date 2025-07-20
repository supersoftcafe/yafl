YAFL Architecture
=================

The underlying architecture behind YAFL is guided by the language goals of transparent parallelism and ease of use.

Recursive descent parser
------------------------

I for a long time strongly believe that parsers are hard, and stuck firmly with parser libraries. I used ANTLR because of past experience and because it is very powerful, but one of my design decisions kept conflicting with ANTLR.

Indentation as a language feature, like python (but better). After a long time of butting my head against a wall trying to make these parsers behave as I wanted, I gave up and swallowed my pride, and got on with writing my own recursive descent parser.

Firstly, they are more work, don't let people convince you that they're easy when they aren't. However when your design requirements are hard to achieve with out of the box parsers, a roll your own approach can be very rewarding.

Hard, but not impossible, and very well understood. Thus, documentation is very accessible. My suggestion, give it a go, and see what you can do. Start simple, and do what the guides say, at least until you find your feet and feel confident enough to try new ideas.

What you loose is a nice grammar description. What you gain is control. In the end that trumped convenience.

C in between
------------

Early on I was aiming for LLVM IR, which was working, but slowly I hit barriers with integrating with other libraries, or with ease of cross platform portability. In C I can do 'sizeof(void*)', or I can emit '#if WORD_SIZE == 64'. In short, my compiler doesn't need to know anything about the target architecture, it can stay focussed on the language and high level jobs, leaving low level decisions to the C compiler.

There are dis-advantages, the biggest of which is that I can't enforce tail calling convention. It means that I need to experiment on each architecture to see if tail calls are used where appropriate. For now, benefits outweigh costs.

Whole application build
-----------------------

There are no libraries, unless they are source code. There is no incremental build. YAFL builds a whole application into a binary. This is mostly for convenience, not for performance reasons. Other architectural decisions have been made easier by this decision.

Thread pool
-----------

On startup a thread pool is created with exactly one thread per CPU thread. Work is scheduled on to threads by enqueueing it to their individual work queues as a function pointer (more on those later). Great effort is put into reducing the need for thread safe primitives in queue management, but they can't be entirely avoided. I feel that this innocently small area of code will end up being an area for huge optimisation efforts.

It's important to note that the YAFL programmer will know nothing about this thread pool, nor indeed threads. They get it all for free thanks to the compiler.

CPS (Continuation Passing Style)
--------------------------------

Most, but not all, functions are converted to CPS, which means that most calls become jumps, and most stack frames become heap frames. In many ways it is similar to C# async functions or Kotlin co-routines.

A function call in CPS passes the usual parameters and an additional function pointer to be called on completion. The function should never return, and the compiler must emit code that uses tail calls, which the underlying C compiler should convert to jumps on the target architecture.

Not all functions will be converted. If a function can be proved to not invoke any other CPS function, and it can be proven to be not recursive, it will be kept as a standard stack based function.

C# developers will recognise this pattern in large projects, where one or two async functions act like a catalyst, and they end up converting most of the code-base to async. The difference here is that it's not explicit, and we start on the assumption that everything is async and work backwards, finding those that don't need to be async.

The purpose behind this is so that the runtime can have a fixed number of worker threads independent of IO. Also, it is so that we can fork some jobs to take advantage of thread pools. More on that later.

Fat function pointers
---------------------

A function pointer doesn't just point to a function, it also has a pointer to a heap allocated context that is passed as the first parameter. All functions take this first parameter, even if they don't use it, so that all functions can be expressed in this way and have their pointers passed around.

This makes some functional aspects of the language easier to realise. If all function calls follow the same pattern, we don't need to have different flavours of function pointer. The moral equivalent of a C#/Java static function will take a null pointer as this first argument. It's an acceptable cost for flexibility.

Hashed virtual tables
---------------------

Objects, interfaces, classes, whatever you call them in your favourite language, need a way to dispatch virtual function calls. We use a relatively standard heap layout, where the first word of an object is a class pointer. The class structure itself describes this object and works with garbage collection, but also it has a table of function pointers, the declared and inherited functions.

Every function in the table is a pair, the pointer to the first instruction and an integer word that is a global unique identity for that specific function. Sub-classes that override a function must use the same identity in the vtable. The vtable itself is a binary size, in that its size is 16, 32, 64 etc entries. This makes it very easy to use a mask when looking up a function id.

The vtable itself is, clearly, a hash table. However, the assignment of ids is done globally in order to optimise as many hash tables as possible to be perfect, hopefully all of them. For each id, because we build a whole application, we can know for certain if it gets its first choice slot in every hash table, and therefore if we need to scan a vtable or not.

The function look up takes an id, masks it using the mask provided in class descriptor for the referenced object, and starts scanning forwards from there. It doesn't wrap around, it just scans forward. The vtable itself might be a bit larger than the specific power of 2 size to accommodate this scanning strategy, and must terminate on a null.

We could leave all call sites doing a proper scan, in the knowledge that it'll rarely need to loop, but optimising known perfect hash calls is an easy win, and covers most if not all function ids.

Memory management
-----------------

A mark sweep garbage collector is being developed specifically to take advantage of YAFLs runtime architecture. Ultimately I want to develop a compacting GC, but the initial version will not be. Stacks don't get scanned, only global roots and the heap. We have intimate knowledge of heap layout, so we only scan true pointers, but those pointers may in some cases point at an object that is not heap managed. Such objects will be marked in some way.

The lack of stack scanning is down to the CPS conversion and thread pool approach for work management. Each thread regularly exits all the way back to an event loop, where we know that there are no object references. To move between the major stages of a GC we need to wait for each thread in the thread pool to confirm that it has iterated once, which proves that all stacks have emptied since the decision to advance the GC stage.

There are more details I want to write, but this may require a dedicated document.

Tuples not precedence
---------------------

All types are equivalent to the tuple of that type. A function that takes a parameter that is 'int' can also take 'tuple of int'.

This largely affects the parser. Think of C# (and possibly python) where brackets are used for precedence in expressions and for specifying tuples, but a tuple of a single element has that redundant comma in there so that the compiler know that you mean tuple. In YAFL brackets always mean tuple, but because tuple of N is equivalent to N, we get precedence for free.



