
# YAFL (Yet Another Functional Language)

I've read about so many programming languages and worked in a few of them. C, C++, Python, Kotlin,
C#, Java, Modula-2, Miranda, BBC Basic, Visual Basic, various forms of assembly language. I love
watching presentations about Rust and Haskell on t'internet but haven't had a chance to dabble yet.
I have read so many books and papers on compiler design, on register allocators, on optimisation
strategies.

What I am trying to say here, is that I love this stuff, and that I have formed my own opinion
about what a good programming language should be. This project is me trying to bring it to life.

# AI/LLMs

I have re-started this project many times over the years, switching the language I used to build
the compiler, re-doing the parser, and trying to belanance work, family and YAFL. It was becoming
an issue and I really wanted to share this work with somebody, but there was nobody. Until Claude
came along. Claude is my junior developer buddy. I can point Claude at some work, and let Claude
get on with it whilst I have family time. It has accelerated the development of this project
tenfold at least, but at a cost. I have less control over the output quality. I still have control
but that takes time, so I find myself compromising and just merging, with a mental promise to
review/fix regressions later.

Before I started using Claude I had the GC complete, the parser was quite mature and robust but
language features were getting harder and harder to introduce to the compiler. Plus tests were
thin on the ground. This is where I started using Claude, and slowly trusting it bit-by-bit to
do small constrained jobs, and slowly increasing the scope of those jobs as my trust improved.

Recently I have been able to leave it dealing with some quite complex refactors, or adding a
big feature, and with good guidance it does a good job. Then I review, give review feedback
and it fixes those issues. It's working quite well. Case-in-point the async IO module was
specified by me, for simplicity and portability above all other things, and implemented by
Claude.

Does this mean that I'll accept AI PRs. No. Only human PRs. My philosophy is, if you aren't
willing to take personal responsibility for changes, then I can't trust you. It's the same
approach my employer is taking, each individual is free to use AI, but the PR is done by a human
who takes personal responsibility for it.

# Key language features

- Read-only by default. Rust certainly gets this right, a highly functional language in my
  opinion. It should be hard to declare something as mutable not just for correctness, but also
  because it has consequences for efficiency.
- Code layout as syntax. A lot like python, indentation means something, it means that what follows
  is a block that belongs to the first statement. No semi-colons, no curley braces, just tidy code.
- Ambiguity is an error. You can declare what you like. You can even declare the same function with
  the same parameters multiple times, and the compiler will not complain. If you try to call that
  function, then you'll have problems. In nearly all evaluations the compiler treats any kind of
  referential ambiguity as an error.
- Functions are data. You can reference a function by name, and what is returned is a function. You
  can pass that around, store it, and call it later. Most modern popular languages do this.
- There is no guarentee of the order of evaluation. Left to right, right to left. A sequence of
  lets could be swapped around, or even run in parallel. There is a basic assumption that nothing
  has side effects and it is safe to re-order the code whilst respecting chained dependencies. No
  concept like Haskell has of the IO monad. If code is written that has side effects, the programmer
  must be aware and must code defensively. For the vast majority of non-library code, this should
  not be a concern.
- Linear types enforce sequential logic and cleanup for IO.
- Integers have no min/max. They are unbounded, similar to python.
- Traits. Borrowed from Rust, this is a brilliant way of thinking about generics, much better
  than the Java/Kotlin/C# approaches. Declare a local generic name TVal, and then express that it
  must support numeric functions, or certain IO functions, or maybe functions that can stringify
  it. Very powerful.
- OO. We still have the OO concepts from C#/Java. Classes, interfaces, inheritance, overloading.

# Key runtime features

- All functions are async. Think about C# and the async keyword, it spreads like a virus throughout
  a code-base, until you're wondering why the keyword even exists. In YAFL everything is async
  under the covers unless the compiler can prove otherwise. The programmer is ignorant to this fact.
- Any tuple creation could be transformed into parallel execution by the compiler. All function
  calls have a tuple construction for their parameters. Any sequence of lets might be transformedd
  into a tuple construction by the compiler. It is free to make these decisions for any reason, but
  will take into account a cost/benefit estimator.
- Worker threads only do CPU work. All IO is async.
- Heap is GC managed. There is no concept of a finalizer or of the C# IDisposable. This need is
  covered by linear types at the language level.
- Integers and strings are heap managed, unless they are small enough to be packed into a pointer
  sized object. The runtime uses this, and with some GC help, to avoid heap allocations.

# Garbage Collector

This is a concurrent compacting mark sweep garbage collector. There is no generational optimisation
here, so it just walks the entire heap every time. For now I need something that works without
pausing the runtime, and this is it.

There is no GC thread. All work happens on the main worker threads as a side-quest of any heap
allocation calls, and of checkpoint code that is injected into the generated code from the YAFL
compiler.

There is a strong assumption that the worker threads are running YAFL code, which is known to
yield often. That matters because the start/end of a GC is marked by all worker threads passing
a checkpoint.

All GC managed heap must be comprised of well behaved well structured YAFL objects, with a
descriptor that tells GC exactly where to find pointers. Not things that might be pointers, but
fields in the heap that are definately pointers to other well structured objects. However, there
is a global rule that allows the YAFL runtime to pack other data into pointer fields. If any of
the lower bits are not zero, then the GC will skip the pointer.

Compaction only works on read-only objects. This is defined as an object that is initialised only
and where that initialisation is completed before any other call to a heap allocation function
or to a check-point function. This is the window of opportunity where the runtime can be confident
that this newly allocated object is not being compacted. During compaction two copies of a read-only
object may exist at the same time whilst GC is re-writing referencing pointers. This keeps the
runtime safe and happy. At the end of GC, after the all threads have gone through at least one
cycle of returning to the outer event loop, GC is in a known safe state where none of the old heap
is referenced and then releases those pages. This is yet another assumption that we are running
with the YAFL compiler, where everything is read-only by default.

# IO

Eventually I want IO to have platform optimised modules, but that's not an early requirement.
Right now async IO uses the C stdio API as a standard platform agnostic way of doing IO and
a thread pool separate from worker threads to do the actual IO. It's simple, it adds overhead
but it gets the ideas in there early. Later we can use io_uring on Linux, and whatever platform
specific accelarated APIs exist when porting. On embedded devices this then also maps nicely
into an interrupt driven model.

# Build and use

Requirements.
* Python 3
* PyInstaller
* CMake
* A C compiler like gcc, clang or msvc

Building 'compiler' and 'yafllib'. It's the same commands in each folder.
```
Unix like OSs                           |   Microsoft Windows
--------------------------------------------------------------------------------
cmake --preset debug-unix               |   cmake --preset debug-windows
cmake --build --preset debug-unix       |   cmake --build --preset debug-windows
sudo cmake --install build/debug-unix   |   cmake --install build\debug-windows

or

cmake --preset debug-unix && cmake --build --preset debug-unix && sudo cmake --install build/debug-unix
```

On Unix like OSs you may have to set the library path in order to run the resulting executables like so:
```
export LD_LIBRARY_PATH=/usr/local/lib
```

You can test that the compiler is installed and working like so:
```
cd examples
yafl -o test hellowWorld.yafl
./test
```

If you like, you can examine the intermediate C code like so:
```
cd examples
yafl -c test.c hellowWorld.yafl
more test.c
```



