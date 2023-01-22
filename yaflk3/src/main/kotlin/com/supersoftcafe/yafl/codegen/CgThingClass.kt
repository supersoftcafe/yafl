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
    private fun CgType.findObjectPaths(): List<List<Int>> {
        return when (this) {
            CgTypePrimitive.OBJECT -> listOf(listOf())
            is CgTypeStruct -> this.fields.flatMapIndexed { index, type ->
                type.findObjectPaths().map { listOf(index) + it }
            }
            else -> listOf()
        }
    }

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

        val classInfo = CgClassInfo(name)

        val fieldsIr = fields.joinToString { field ->
            if (field.isArray) {
                "[ 0 x ${field.type} ]"
            } else {
                "${field.type}"
            }
        }



        val arrayField = fields.lastOrNull()?.takeIf { it.isArray }

        val deleteHead = listOf(if (arrayField != null) {
            "define internal tailcc void ${classInfo.deleteFuncName}(%object* %opaque_pointer, i32 %array_size) {"
        } else {
            "define internal tailcc void ${classInfo.deleteFuncName}(%object* %opaque_pointer) {"
        }, "entry:", "  %pointer = bitcast %object* %opaque_pointer to ${classInfo.objectTypeName}*")

        val deleteTail = fields.withIndex().reversed().flatMap { (index, field) ->
            val objectPaths = field.type.findObjectPaths()
            if (objectPaths.isEmpty()) {
                listOf()

            } else if (!field.isArray) {
                objectPaths.flatMap { path ->
                    val nameSuffix = path.joinToString("", "_$index") { "_$it" }
                    val pathForGep = path.joinToString("") { ", i32 $it" }
                    listOf(
                        "  %field$nameSuffix = getelementptr ${classInfo.objectTypeName}, ${classInfo.objectTypeName}* %pointer, i32 0, i32 1, i32 $index$pathForGep",
                        "  %value$nameSuffix = load %object*, %object** %field$nameSuffix",
                        "  tail call tailcc void @release(%object* %value$nameSuffix)")
                }

            } else {
                // TODO: Loop across array and release everything
                listOf(
                    "  br label %loop",
                    "loop:",
                    "  %index = phi i32 [ 0, %entry ], [ %next_index, %loop ]",
                    "  %is_ok = icmp ult %index, %array_size",
                    "  br i1 %is_ok, label %body, label %end",
                    "body:"
                ) + objectPaths.flatMap { path ->
                    val nameSuffix = path.joinToString("", "_$index") { "_$it" }
                    val pathForGep = path.joinToString("") { ", i32 $it" }
                    listOf(
                        "  %field$nameSuffix = getelementptr ${classInfo.objectTypeName}, ${classInfo.objectTypeName}* %pointer, i32 0, i32 1, i32 $index, i32 %index$pathForGep",
                        "  %value$nameSuffix = load %object*, %object** %field$nameSuffix",
                        "  tail call tailcc void @release(%object* %value$nameSuffix)")
                } + listOf(
                    "  %next_index = add %size_t %index, 1",
                    "  br label %loop"
                )
            }
        }

        val deleteObject = if (arrayField != null) {
            listOf(
                "  %size_as_gep = getelementptr ${classInfo.objectTypeName}, ${classInfo.objectTypeName}* null, i32 0, i32 1, i32 ${fields.size - 1}, i32 %array_size",
                "  %size_as_int = ptrtoint ${arrayField.type}* %size_as_gep to %size_t")
        } else {
            listOf(
                "  %size_as_gep = getelementptr ${classInfo.objectTypeName}, ${classInfo.objectTypeName}* null, i32 1",
                "  %size_as_int = ptrtoint ${classInfo.objectTypeName}* %size_as_gep to %size_t")
        } + "  tail call tailcc void @deleteObject(%size_t %size_as_int, %object* %opaque_pointer)"

        val deleteDeclaration = (deleteHead + if (deleteTail.lastOrNull()?.contains("@releaseActual") == true) {
            // Re-arrange last few calls to benefit from a tail call
            deleteTail.dropLast(1) + deleteObject + deleteTail.takeLast(1)
        } else {
            // No tail call is possible
            deleteTail + deleteObject
        } + "  ret void" + "}").joinToString("\n", "", "\n\n") { it }



        return CgLlvmIr(
            types = "${classInfo.vtableTypeName} = type { { %size_t, void(%object*)* }, [ $size x %size_t* ] }\n" +
                    "${classInfo.objectTypeName} = type { %object, { $fieldsIr } }\n",
            declarations = "${classInfo.vtableDataName} = internal constant ${classInfo.vtableTypeName} { { %size_t, void(%object*)* } { %size_t $mask, void(%object*)* @\"$deleteGlobalName\" }, [ $size x %size_t* ] [ $vtableInitialiser ] }\n\n" +
                    deleteDeclaration
        )
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
