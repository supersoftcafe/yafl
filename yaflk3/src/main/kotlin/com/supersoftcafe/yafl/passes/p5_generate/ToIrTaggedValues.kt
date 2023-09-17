package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.ast.TypeRef
import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.utils.tupleOf





class TaggedValuesExtractEntry(
    val transportIndex: Int,
    val originalPath: IntArray,
    val type: CgTypePrimitive
)

class TaggedValuesTypeEntry(
    val tagName: String,
    val tagValue: Int,
    val tagType: CgTypeStruct,
    val mappings: List<TaggedValuesExtractEntry>
)

class TaggedValuesRuntimeInfo(
    val transportType: CgTypeStruct,
    val tagMaps: List<TaggedValuesTypeEntry>
)

// Convert to transport tuple representation
fun createTaggedValuesInfo(type: TypeRef.TaggedValues, globals: Globals): TaggedValuesRuntimeInfo {
    fun CgType.findAllPrimitives(pathPrefix: IntArray = intArrayOf()): List<Pair<CgTypePrimitive, IntArray>> {
        return when (this) {
            is CgTypePrimitive -> listOf(Pair(this, pathPrefix))
            is CgTypeStruct -> fields.flatMapIndexed { index, type -> type.findAllPrimitives(pathPrefix + index) }
            else -> throw IllegalArgumentException("Cannot flatten $this")
        }
    }

    fun List<Pair<CgTypePrimitive, IntArray>>.indexUniqueInstances(): List<Pair<Pair<CgTypePrimitive, Int>, IntArray>> {
        return map { it.first }.distinct().flatMap { instance ->
            filter { it.first == instance }.mapIndexed { index, (type, path) -> Pair(Pair(type, index), path) }
        }
    }

    val analysedMembers = type.tags.map { (type, name) ->
        val tagType = type.toCgType(globals)
        val mapping = tagType.findAllPrimitives().indexUniqueInstances()
        tupleOf(name, tagType, mapping)
    }

    val transportSlotsInOrder = analysedMembers
        .flatMap { (tagName, tagType, mapping) -> mapping.map { (typeSlot, originalPath) -> typeSlot }}
        .distinct().sortedWith(compareBy({ (type,_) -> type },{ (_,index) -> index }))

    return TaggedValuesRuntimeInfo(
        transportType = CgTypeStruct(transportSlotsInOrder.map { (type,_) -> type } + CgTypePrimitive.INT8),
        tagMaps = analysedMembers.mapIndexed { index, (tagName, tagType, mapping) ->
            TaggedValuesTypeEntry(tagName, index, tagType, mapping.map { ( typeAndIndex, originalPath) ->
                TaggedValuesExtractEntry(
                    transportIndex = transportSlotsInOrder.indexOf(typeAndIndex),
                    originalPath = originalPath,
                    type = typeAndIndex.first
                )
            })
        }
    )
}
