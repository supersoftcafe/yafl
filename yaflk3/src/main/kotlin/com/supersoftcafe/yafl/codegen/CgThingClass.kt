package com.supersoftcafe.yafl.codegen

import kotlin.math.max

data class CgClassField(
    val type: CgType,
    val isArray: Boolean = false
)

data class CgThingClass(
    val name: String,
    val fields: List<CgClassField>,
    val functions: Map<String, String>, // Signature to Global name
    val deleteGlobalName: String // Must be void(object*)
) : CgThing {
    fun toIr(context: CgContext): CgLlvmIr {
        val slots = functions
            .mapNotNull { (nameOfSlot, globalName) -> context.slotNameToId(nameOfSlot)?.let { slotId -> Pair(globalName, slotId) } }

        val size = max(4, (slots.size + slots.size / 2).takeHighestOneBit() * 2)
        val mask = size - 1
        val array = flattenHashTable((0..mask)
            .map { index -> slots.filter { (_, slot) -> (slot and mask) == index }.map { (name, _) -> name } })

        val vtableInitialiser = array.joinToString { name -> if (name != null) {
            "%size_t* bitcast ( %\"typeof.$name\"* @\"$name\" to %size_t* )"
        } else {
            "%size_t* null"
        }}

        val vtableDataName = "@\"vtable\$$name\""
        val objectTypeName = "%\"typeof.object\$$name\""
        val vtableTypeName = "%\"typeof.vtable\$$name\""

        val fieldsIr = fields.joinToString { field ->
            if (field.isArray) {
                "[ 0 x ${field.type} ]"
            } else {
                "${field.type}"
            }
        }

        return CgLlvmIr(
            types = "$vtableTypeName = type { { %size_t, void(%object*)* }, [ $size x %size_t* ] }\n" +
                    "$objectTypeName = type { %object, { $fieldsIr } }\n",
            declarations = "$vtableDataName = internal global $vtableTypeName { { %size_t, void(%object*)* } { %size_t $mask, void(%object*)* @\"$deleteGlobalName\" }, [ $size x %size_t* ] [ $vtableInitialiser ] }\n\n")
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
