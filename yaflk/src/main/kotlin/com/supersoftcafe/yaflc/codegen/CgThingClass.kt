package com.supersoftcafe.yaflc.codegen

import kotlin.math.max

data class CgThingClass(
    val name: String,
    val dataType: CgTypeStruct,
    val functions: List<CgThingFunction>,
    val delete: CgThingFunction // Must be void(object*)
) : CgThing {
    fun toIr(context: CgContext): CgLlvmIr {
        val slots = functions.mapNotNull { function -> context.slotNameToId(function.name)?.let { slotId -> Pair(function.name, slotId) } }
        val size = max(4, (slots.size + slots.size / 2).takeHighestOneBit() * 2)
        val mask = size - 1
        val array = flattenHashTable((0..mask).map { index -> slots.filter { (_, slot) -> (slot and mask) == index }.map { (name, _) -> name } })

        val vtableInitialiser = array.joinToString { name -> if (name != null) {
            val functionName = CgValue.Global(name)
            val functionTypeName = CgValue.Register("typeof.$functionName")
            "%size_t* bitcast ( $functionTypeName* $functionName to %size_t* )"
        } else {
            "%size_t* null"
        }}

        val vtableDataName = CgValue.Global("vtable\$$name")
        val objectTypeName = CgValue.Register("typeof.object\$$name")
        val vtableTypeName = CgValue.Register("typeof.vtable\$$name")
        return CgLlvmIr(
            types = "$vtableTypeName = type { { %size_t, void(%object*)* }, [ $size x %size_t* ] }\n" +
                    "$objectTypeName = type { %object, $dataType }\n",
            declarations = "$vtableDataName = internal global $vtableTypeName { { %size_t, void(%object*)* } { %size_t $mask, void(%object*)* @${delete.name.escape()} }, [ $size x %size_t* ] [ $vtableInitialiser ] }\n\n")
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
