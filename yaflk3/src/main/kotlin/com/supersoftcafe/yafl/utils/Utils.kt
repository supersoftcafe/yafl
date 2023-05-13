package com.supersoftcafe.yafl.utils

fun <X, Y> List<Pair<X,Y>>.invert(): Pair<List<X>, List<Y>> {
    return Pair(map { (x, y) -> x }, map { (x, y) -> y })
}

fun <X,Y,Z> Pair<X,Y>.mapFirst(transform: (X)->Z): Pair<Z,Y> = Pair(transform(first), second)
fun <X,Y,Z> Pair<X,Y>.mapSecond(transform: (Y)->Z): Pair<X,Z> = Pair(first, transform(second))

fun <W,X,Y,Z> Triple<W,X,Y>.mapFirst(transform: (W)->Z): Triple<Z,X,Y> = Triple(transform(first), second, third)
fun <W,X,Y,Z> Triple<W,X,Y>.mapSecond(transform: (X)->Z): Triple<W,Z,Y> = Triple(first, transform(second), third)
fun <W,X,Y,Z> Triple<W,X,Y>.mapThird(transform: (Y)->Z): Triple<W,X,Z> = Triple(first, second, transform(third))

fun <K,V> merge(x: Map<K, Set<V>>, y: Map<K, Set<V>>): Map<K, Set<V>> = (x.keys + y.keys).associateWith { x.getOrDefault(it, setOf()) + y.getOrDefault(it, setOf()) }
fun <K,V> List<Map<K, Set<V>>>.merge(): Map<K, Set<V>> = fold(mapOf(), ::merge)