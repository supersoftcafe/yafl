package com.supersoftcafe.yafl.utils

fun <X, Y> List<Pair<X,Y>>.invert(): Pair<List<X>, List<Y>> {
    return Pair(map { (x, y) -> x }, map { (x, y) -> y })
}
