# Prelude

Where am I?

It has been many years since I entered this domain.

Wandering, blindly taking wrong turns, I am sure.

Is that light I see, in the distance.

# Yet Another Functional Language (YAFL)

YAFL is my attempt at a language that is:
1. Safe, like those languages with managed runtimes.
2. Compact, the way that most modern languages are going.
3. Implicitly parallel, so that all of the CPU threads are used.
4. Scalable, so that you can write for micro controllers and super computers alike.
5. Easy to use.

For these I take inspiration from other languages, to varying degrees.

It's mostly functional, with some opt outs. That's not a design goal, but is a very good paradigm to follow in order to enable the parallelism design goal.

It compiles to C first, then uses the local C compiler to produce binary output. The C output is messy, because it is CPS (Continuation Passing Style), but don't worry, YAFL isn't. We just convert to CPS.

String and int (it's a big int under the covers) are built in types, primitive in language terms, despite being heap allocated. That was a tough decision, but it makes so much other stuff simpler.

# Progress

Hardly anything works, but the following program does compile and run. It's really interesting to look at the intermediate C code.

```
import System

fun main(): System::Int
    ret System::print("Hi there\n")
```

# Build and use


# TODO

* Write build and use instructions in readme
* Tidy up command line for compiler and install script for libs
* Generics
* Type inference
* Tagged unions


