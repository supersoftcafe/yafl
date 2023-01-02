# Yet Another Functional Language (YAFL)

Like many before me, I have issues with the current crop of programming languages. So I am going to create my own. Crazy yes?

Actually, I have been working on it for some time. Maybe half a year, or more. I have lost count.

So, here it is. YAFL. The design goals are as follows:

1. Highly scalable both in terms of memory and compute. For this I mean that it should be a highly capable language for targeting small embedded systems with a single slow core and memory measured in Kbytes up to 96 core 128 Tbyte beasts, and be highly effective at using all of the resources available.
2. No threads and no locking, at least not explicitly. Just write the logic of your program, and the compiler takes care of the rest.
3. Concise, but not too concise. Haskell is bloody concise, and as a result is unreadable. Java is overtly obtuse, and as a result is unmaintainable. Kotlin does well, but doesn't go far enough. There is a happy sweet spot that I hope to achieve.
4. Remove anti-patterns. There is heated debate on what is an anti-patttern, so for the sake of argument just assume that my word is law and I know best. I'll not be having class hierarchies for example.
5. No null. Just doesn't exist. Get over it.

Functional is not a design goal, but is a useful paradigm to achieve these goals. It helps to simplify both the automatic memory management and auto parallelism. Pure functional isn't a goal either, and I don't intend to go that far, but balancing mutable vs immutable will be interesting. I am thinking of having islands of mutability.

To keep things simple, nearly all operators are functions. "1 + 2" will always compile to "`+`(1, 2)", which is a function call to `+`. We will rely on the LLVM optimiser to remove the extra bloat, but what we get is super simple operator overloading.

Overloads are a thing. Even Rust that eschews overloads actually does have them, just by another mechanism. Just imagine having a 'println' method that can't take a variety of input types. What a pain. In my world overloading is simple, just define multiple variants of a function with slightly different signatures.

Type inference is a big thing. You can write a program almost never having to provide type information, despite this being a strongly typed language.

# Progress

Currently the compiler works. It's a big manual, but really it does useful stuff and generates beautiful LLVM IR that when compiled does work. Automatic heap management is mostly working. Type inference mostly works. It's a beautiful language!

No io, strings or generics yet. This is a big problem, and made bigger because I have to do them in a particular order that means that we won't get string support until relatively late.

This program builds, and works. It produces a shit-tonne of LLVM IR, and it's beautiful.

```
module Test

import Io
import System

class Thing(height, age) {
    fun both(value) => height + age + value
}

fun doSomethingWith(value, getter: (Int32) : Int32) => print(getter(value))

fun main() => doSomethingWith(27, Thing(180, 48).both)
```

