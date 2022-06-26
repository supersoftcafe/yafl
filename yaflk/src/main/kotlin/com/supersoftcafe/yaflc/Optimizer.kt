package com.supersoftcafe.yaflc

class Optimizer {

    // Inline whatever we can.

    // Replace tail recursive calls (post inlining so we can get more of them) with functional safe loops.

    // Where can we insert 'parallel' blocks for best effect based on cost analysis of sub-expressions?
    // e.g. func(create1(), create2()) might benefit from parallelizing create1/create2 if they have a high
    // cost.

    // Can we parallelize any functional safe loops?

    // Analyse 'val' declarations for begin and end scope. Does it escape into multi-thread space?
    // If not, we can use fast acquire/release without locking.
    // Only done after parallel optimisations otherwise we have nothing to look for.

    // Can an 'owned' 'val' be transferred on its final use so that we don't need to 'release' it?
    // Sometimes we might see 'val a = NewSomething()' followed by 'AnotherSomething(a)' as the last use.
    // In this case we might be able to avoid the 'acquire' and 'release' pair that would normally be
    // generated.

    // If a created object does not escape at all, we can remove all reference counting semantics.

    // If a constructed object is passed as borrowed, and we can prove that the callee never
    // does an 'acquire', we can construct the object on the stack instead.


}