package com.supersoftcafe.yafl.utils

data class Tuple1<V1>(val v1: V1) {
    fun <R1> map(f: (V1) -> Tuple1<R1>) = f(v1)
}

data class Tuple2<V1, V2>(val v1: V1, val v2: V2) {
    fun <R1,R2> map(f: (V1,V2) -> Tuple2<R1,R2>) = f(v1,v2)
}

data class Tuple3<V1, V2, V3>(val v1: V1, val v2: V2, val v3: V3) {
    fun <R1,R2,R3> map(f: (V1,V2,V3) -> Tuple3<R1,R2,R3>) = f(v1,v2,v3)
}

data class Tuple4<V1, V2, V3, V4>(val v1: V1, val v2: V2, val v3: V3, val v4: V4) {
    fun <R1,R2,R3,R4> map(f: (V1,V2,V3,V4) -> Tuple4<R1,R2,R3,R4>) = f(v1,v2,v3,v4)
}

data class Tuple5<V1, V2, V3, V4, V5>(val v1: V1, val v2: V2, val v3: V3, val v4: V4, val v5: V5) {
    fun <R1,R2,R3,R4,R5> map(f: (V1,V2,V3,V4,V5) -> Tuple5<R1,R2,R3,R4,R5>) = f(v1,v2,v3,v4,v5)
}

data class Tuple6<V1, V2, V3, V4, V5, V6>(val v1: V1, val v2: V2, val v3: V3, val v4: V4, val v5: V5, val v6: V6) {
    fun <R1,R2,R3,R4,R5,R6> map(f: (V1,V2,V3,V4,V5,V6) -> Tuple6<R1,R2,R3,R4,R5,R6>) = f(v1,v2,v3,v4,v5,v6)
}

fun <V1> tupleOf(v1: V1) = Tuple1(v1)
fun <V1, V2> tupleOf(v1: V1, v2: V2) = Tuple2(v1, v2)
fun <V1, V2, V3> tupleOf(v1: V1, v2: V2, v3: V3) = Tuple3(v1, v2, v3)
fun <V1, V2, V3, V4> tupleOf(v1: V1, v2: V2, v3: V3, v4: V4) = Tuple4(v1, v2, v3, v4)
fun <V1, V2, V3, V4, V5> tupleOf(v1: V1, v2: V2, v3: V3, v4: V4, v5: V5) = Tuple5(v1, v2, v3, v4, v5)
fun <V1, V2, V3, V4, V5, V6> tupleOf(v1: V1, v2: V2, v3: V3, v4: V4, v5: V5, v6: V6) = Tuple6(v1, v2, v3, v4, v5, v6)

operator fun <V1,V2> Tuple1<V1>.plus(x: Tuple1<V2>) = tupleOf(v1, x.v1)
operator fun <V1,V2,V3> Tuple1<V1>.plus(x: Tuple2<V2,V3>) = tupleOf(v1, x.v1, x.v2)
operator fun <V1,V2,V3,V4> Tuple1<V1>.plus(x: Tuple3<V2,V3,V4>) = tupleOf(v1, x.v1, x.v2, x.v3)
operator fun <V1,V2,V3,V4,V5> Tuple1<V1>.plus(x: Tuple4<V2,V3,V4,V5>) = tupleOf(v1, x.v1, x.v2, x.v3, x.v4)
operator fun <V1,V2,V3,V4,V5,V6> Tuple1<V1>.plus(x: Tuple5<V2,V3,V4,V5,V6>) = tupleOf(v1, x.v1, x.v2, x.v3, x.v4, x.v5)

operator fun <V1,V2,V3> Tuple2<V1,V2>.plus(x: Tuple1<V3>) = tupleOf(v1, v2, x.v1)
operator fun <V1,V2,V3,V4> Tuple2<V1,V2>.plus(x: Tuple2<V3,V4>) = tupleOf(v1, v2, x.v1, x.v2)
operator fun <V1,V2,V3,V4,V5> Tuple2<V1,V2>.plus(x: Tuple3<V3,V4,V5>) = tupleOf(v1, v2, x.v1, x.v2, x.v3)
operator fun <V1,V2,V3,V4,V5,V6> Tuple2<V1,V2>.plus(x: Tuple4<V3,V4,V5,V6>) = tupleOf(v1, v2, x.v1, x.v2, x.v3, x.v4)

operator fun <V1,V2,V3,V4> Tuple3<V1,V2,V3>.plus(x: Tuple1<V4>) = tupleOf(v1, v2, v3, x.v1)
operator fun <V1,V2,V3,V4,V5> Tuple3<V1,V2,V3>.plus(x: Tuple2<V4,V5>) = tupleOf(v1, v2, v3, x.v1, x.v2)
operator fun <V1,V2,V3,V4,V5,V6> Tuple3<V1,V2,V3>.plus(x: Tuple3<V4,V5,V6>) = tupleOf(v1, v2, v3, x.v1, x.v2, x.v3)

operator fun <V1,V2,V3,V4,V5> Tuple4<V1,V2,V3,V4>.plus(x: Tuple1<V5>) = tupleOf(v1, v2, v3, v4, x.v1)
operator fun <V1,V2,V3,V4,V5,V6> Tuple4<V1,V2,V3,V4>.plus(x: Tuple2<V5,V6>) = tupleOf(v1, v2, v3, v4, x.v1, x.v2)

operator fun <V1,V2,V3,V4,V5,V6> Tuple5<V1,V2,V3,V4,V5>.plus(x: Tuple1<V6>) = tupleOf(v1, v2, v3, v4, v5, x.v1)