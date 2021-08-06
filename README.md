# Yet Another Functional Language

This has been ticking over in my mind for years. The obsession of a seasoned developer, of many before me. What is the perfect progamming language. Not just imperitive vs functional, or functional vs oo which is to my mind a silly comparison as they are not mutually exclusive. It's more about what are the various paradigms and languages bringing to the table that we love, that help to improve reliability, performance and maintainability, and do that by making our jobs as programmers easier. No pressure.

## Goals

Influences on my thinking so far have been Kotlin and Haskell, with a hint of Python. Here are my takes on the positives each of these languages bring.
### Clear and easy to visually parse
Kotlin has a very clear syntax. It's compact and yet easy to visually parse at the same time. This is in contrast to Haskell which is extremely compact, but at the expense of visual parsability. Python is worth a mention here, as it brings good visual parsing to the table by another mechanism, which is indentation as a part of the grammar. The goal here is to have much of the clarity of Kotlin but without the curley braces everywhere, more like python. No list comprehensions, again leaning on the clear English approach of Kotlin. No direct use of indentation as a part of the grammar either. It's a really fine line to walk, but I have prototyped and am getting towards a regular grammar that does not require the use of braces or indentation.
### Names and concepts that are familiar to imperative programmers
Obviously Haskell will fail this one. Kotlin again wins out with its policy of using clear English words for actions instead of symbols, and the terms used are more familar to the imperative programmer. However it at the same times borrows heavily from some base functional principles to achieve many of the same results.
### Implicit parallelism
Ah...   This is of course absolute idealism, and none of the languages do this. Kotlin has coroutines, which are absolutely amazing, but you still have to use them, you still have to plan and think about parallelism. My goal is to make it absolutely invisible to the programmer. You run your software on a computer, that's all. If it has more cores, it uses them, end of.
### Low overhead
No standard library. The simplest hello world program should be tiny. This is one of the stated goals of Rust, and I fully buy into it having come from a Java background and living with the multiple tonnes of runtime dependencies every Java program has. The goal here is to compile for a target physical architecture, and get a small binary at the end.
### Implicit memory management
Each of these languages solves this in a different way, and Kotlin even solves it in different ways depending on the underlying platform being targeted. Unfortunately garbage collection whilst amazing is a heavy weight solution that breaks the "low overhead" goal many times over. Python solves this with reference counting, but brings in other performance killers like the global interpreter lock. Objective-C and Swift are the gold standard of ARC (automatic reference counting) for memory management. I hope to follow in those footsteps, but take advantage of a functional focus to reduce the overheads further.
### Functional does not exactly have to mean immutable
It's a thorny topic, but if you get down to basics functional programming is about having a black box. For a given set of inputs the outputs will always be the same, and what happens in the box doesn't matter. Of course that box is a function, and the idea is that nothing outside of the function should be able to influence the result. Some of the immutability of functional languages is how that promise is kept, but one area does not contribute, and that is the immutability of locally defined values within the function, the *val* vs *var* debate. I think that we need to allow some amount of mutability so long as we maintain the black box promise. This is a complex subject that has serious impact on the goals of implicit parallelism and implicit memory management. It needs some serious thought.

## Examples

Some untested examples to try out the syntax for visual appeal. This is an ultra simple persistent list.
Note the lack of curley braces for code blocks. Also note the extensive use of captures for object members.
It's largely following a functional style but with the gramatical trappings of an imperitive language.

    # Something between a Haskell type class and a Rust trait.
    # No implementations here. But defaults can be provided later.
    class Vec<Element>
        fun at(index:Int):Element
        fun count:Int

    # Use of assignment and implicit result. 'object' keyword as used in Kotlin.
    fun vecOf<Element> = object: Vec<Element>
        fun at(index) = throw("Not found")
        fun count = 0

    # Here we have the builtin 'lookup' function, using a 'pair' syntax to give
    # it a set of options. This doesn't replace Kotlin's 'when', but makes for
    # a nice compact alternative.
    fun vecOf<Element>(el0: Element) = object: Vec<Element>
        fun at(index) = lookup(index, 0 -> el0)
        fun count = 1

    fun vecOf<Element>(el0: Element, el1: Element) = object: Vec<Element>
        fun at(index) = lookup(index, 0 -> el0, 1 -> el1)
        fun count = 2

    # Use of 'return' keyword instead of assignment. It feels more tidy here.
    fun concat<Element>(vec0: Vec<Element>, vec1: Vec<Element>)
        fun createVector = Vec<Element>
            fun count = vec0.count + vec1.count
            fun at(index) = index < vec0.count ? vec0.at(index) : vec1.at(index - vec0.count)
        return lookup(0, vec0.count -> vec1, vec1.count -> vec0, 0 -> createVector)

The builtin 'lookup' function and also an equivalent of Kotlin's 'when' deviate from both Kotlin's standard
approach and that of functional languages in that I will not require them to be exhaustive. I might add
a keyword that indicates that the programmer wants them to be exhaustive, but that's all. If absent, and
a match is not found an exception will automatically be thrown. I see this as being very similar to divide by
zero. We don't demand checks for zero before division operators, we runtime error because the inputs were invalid.

