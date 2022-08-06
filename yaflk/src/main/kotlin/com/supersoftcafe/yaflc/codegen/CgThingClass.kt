package com.supersoftcafe.yaflc.codegen

import kotlin.math.max

data class CgThingClass(
    val name: String,
    val fields: List<CgThingVariable>,
    val functions: List<CgThingFunction>,
    val delete: CgThingFunction // Must be void(object*)
) : CgThing {
    fun toIr(context: CgContext): CgLlvmIr {
        val slots = functions.mapNotNull { f -> context.slotNameToId(f.name)?.let { Pair(f.name, it) } }
        val size = max(4, (slots.size + slots.size / 2).takeHighestOneBit() * 2)
        val mask = size - 1
        val array = flattenHashTable((0..mask).map { index -> slots.filter { (_, slot) -> (slot and mask) == index }.map { (name, _) -> name } })

        val vtableInitialiser = array.joinToString { if (it == null)
            "%size_t* null"
        else
            "%size_t* bitcast ( %typeof.$it* @$it to %size_t* )"
        }

        val fieldsStr = fields.joinToString("") { ", ${it.type}" }

        return CgLlvmIr(
            types = "%typeof.vtable\$$name = type { { %size_t, void(%object*)* }, [ $size x %size_t* ] }\n" +
                    "%typeof.object\$$name = type { %object$fieldsStr }\n",
            declarations = "@$name = internal global %typeof.vtable\$$name { { %size_t, void(%object*)* } { %size_t $mask, void(%object*)* @${delete.name} }, [ $size x %size_t* ] [ $vtableInitialiser ] }\n\n")
    }

    private tailrec fun <TEntry> flattenHashTable(array: List<List<TEntry>>): List<TEntry?> {
        val overflowIndex = array.indexOfFirst { it.size > 1 }
        return if (overflowIndex < 0) {
            array.map { it.firstOrNull() }
        } else {
            val nextBlankIndex = (array.subList(overflowIndex, array.size) + array.subList(0, overflowIndex)).indexOfFirst { it.isEmpty() }
            if (nextBlankIndex < 0) throw IllegalStateException("Cannot find overflow index in vtable")

            flattenHashTable(array.mapIndexed { index, entry ->
                when (index) {
                    overflowIndex -> entry.drop(1)
                    nextBlankIndex -> array[overflowIndex].subList(0, 1)
                    else -> entry
                }
            })
        }
    }
}
