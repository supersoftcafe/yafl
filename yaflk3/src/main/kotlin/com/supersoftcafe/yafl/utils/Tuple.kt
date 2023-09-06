package com.supersoftcafe.yafl.utils

data class Tuple1<V1>(val first: V1)
fun <V1,R1> Tuple1<V1>.map(f: (V1) -> Tuple1<R1>) = f(first)

typealias Tuple2<V1, V2> = Pair<V1, V2>
fun <V1, R1, V2, R2> Tuple2<V1, V2>.map(f: (V1,V2) -> Tuple2<R1,R2>) = f(first, second)

typealias Tuple3<V1, V2, V3> = Triple<V1, V2, V3>
fun <V1, R1, V2, R2, V3, R3> Tuple3<V1, V2, V3>.map(f: (V1,V2,V3) -> Tuple3<R1,R2,R3>) = f(first, second, third)

data class Tuple4<V1, V2, V3, V4>(val first: V1, val second: V2, val third: V3, val fourth: V4)
fun <V1, R1, V2, R2, V3, R3, V4, R4> Tuple4<V1, V2, V3, V4>.map(f: (V1,V2,V3,V4) -> Tuple4<R1,R2,R3,R4>) = f(first, second, third, fourth)

data class Tuple5<V1, V2, V3, V4, V5>(val first: V1, val second: V2, val third: V3, val fourth: V4, val fifth: V5)
fun <V1, R1, V2, R2, V3, R3, V4, R4, V5, R5> Tuple5<V1, V2, V3, V4, V5>.map(f: (V1,V2,V3,V4,V5) -> Tuple5<R1,R2,R3,R4,R5>) = f(first, second, third, fourth, fifth)

data class Tuple6<V1, V2, V3, V4, V5, V6>(val first: V1, val second: V2, val third: V3, val fourth: V4, val fifth: V5, val sixth: V6)
fun <V1, R1, V2, R2, V3, R3, V4, R4, V5, R5, V6, R6> Tuple6<V1, V2, V3, V4, V5, V6>.map(f: (V1,V2,V3,V4,V5,V6) -> Tuple6<R1,R2,R3,R4,R5,R6>) = f(first, second, third, fourth, fifth, sixth)

fun <V1> tupleOf(v1: V1) = Tuple1(v1)
fun <V1, V2> tupleOf(v1: V1, v2: V2) = Tuple2(v1, v2)
fun <V1, V2, V3> tupleOf(v1: V1, v2: V2, v3: V3) = Tuple3(v1, v2, v3)
fun <V1, V2, V3, V4> tupleOf(v1: V1, v2: V2, v3: V3, v4: V4) = Tuple4(v1, v2, v3, v4)
fun <V1, V2, V3, V4, V5> tupleOf(v1: V1, v2: V2, v3: V3, v4: V4, v5: V5) = Tuple5(v1, v2, v3, v4, v5)
fun <V1, V2, V3, V4, V5, V6> tupleOf(v1: V1, v2: V2, v3: V3, v4: V4, v5: V5, v6: V6) = Tuple6(v1, v2, v3, v4, v5, v6)

operator fun <V1,V2> Tuple1<V1>.plus(x: Tuple1<V2>) = tupleOf(first, x.first)
operator fun <V1,V2,V3> Tuple1<V1>.plus(x: Tuple2<V2,V3>) = tupleOf(first, x.first, x.second)
operator fun <V1,V2,V3,V4> Tuple1<V1>.plus(x: Tuple3<V2,V3,V4>) = tupleOf(first, x.first, x.second, x.third)
operator fun <V1,V2,V3,V4,V5> Tuple1<V1>.plus(x: Tuple4<V2,V3,V4,V5>) = tupleOf(first, x.first, x.second, x.third, x.fourth)
operator fun <V1,V2,V3,V4,V5,V6> Tuple1<V1>.plus(x: Tuple5<V2,V3,V4,V5,V6>) = tupleOf(first, x.first, x.second, x.third, x.fourth, x.fifth)

operator fun <V1,V2,V3> Tuple2<V1,V2>.plus(x: Tuple1<V3>) = tupleOf(first, second, x.first)
operator fun <V1,V2,V3,V4> Tuple2<V1,V2>.plus(x: Tuple2<V3,V4>) = tupleOf(first, second, x.first, x.second)
operator fun <V1,V2,V3,V4,V5> Tuple2<V1,V2>.plus(x: Tuple3<V3,V4,V5>) = tupleOf(first, second, x.first, x.second, x.third)
operator fun <V1,V2,V3,V4,V5,V6> Tuple2<V1,V2>.plus(x: Tuple4<V3,V4,V5,V6>) = tupleOf(first, second, x.first, x.second, x.third, x.fourth)

operator fun <V1,V2,V3,V4> Tuple3<V1,V2,V3>.plus(x: Tuple1<V4>) = tupleOf(first, second, third, x.first)
operator fun <V1,V2,V3,V4,V5> Tuple3<V1,V2,V3>.plus(x: Tuple2<V4,V5>) = tupleOf(first, second, third, x.first, x.second)
operator fun <V1,V2,V3,V4,V5,V6> Tuple3<V1,V2,V3>.plus(x: Tuple3<V4,V5,V6>) = tupleOf(first, second, third, x.first, x.second, x.third)

operator fun <V1,V2,V3,V4,V5> Tuple4<V1,V2,V3,V4>.plus(x: Tuple1<V5>) = tupleOf(first, second, third, fourth, x.first)
operator fun <V1,V2,V3,V4,V5,V6> Tuple4<V1,V2,V3,V4>.plus(x: Tuple2<V5,V6>) = tupleOf(first, second, third, fourth, x.first, x.second)

operator fun <V1,V2,V3,V4,V5,V6> Tuple5<V1,V2,V3,V4,V5>.plus(x: Tuple1<V6>) = tupleOf(first, second, third, fourth, fifth, x.first)