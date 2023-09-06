package com.supersoftcafe.yafl.models.llir

import com.supersoftcafe.yafl.utils.Namer

sealed class CgOp {
    abstract val result: CgValue.Register
    abstract val inputs: List<CgValue>
    abstract fun toIr(context: CgContext): String

    open fun updateLabels(labelMap: (String) -> String): CgOp = this
    open fun updateRegisters(registerMap: (String) -> String): CgOp = this

    data class Alloca(override val result: CgValue.Register) : CgOp() {
        constructor(resultName: String, type: CgType) : this(CgValue.Register(resultName, CgTypePointer(type)))

        init {
            assert(result.type is CgTypePointer)
        }

        override fun toIr(context: CgContext): String {
            val type = result.type as CgTypePointer
            return "  $result = alloca ${type.target}\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap)
            )
        }

        override val inputs: List<CgValue> = listOf()
    }

//    class Abort() : CgOp() {
//        override val result: CgValue.Register get() = CgValue.VOID
//        override fun toIr(context: CgContext): String {
//            return  "  call void @abort()\n"
//        }
//
//        override val inputs: List<CgValue> = listOf()
//    }

    data class Assert(val condition: CgValue, val message: String): CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext): String {
            // val messageGlobal = context.literalStringToGlobalRef(message)
            return  "  call void @assertWithMessage(${condition.type} $condition, i8* getelementptr([12 x i8], [12 x i8]* @arrayerrorstr, i32 0, i32 0))\n"
        }
        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(condition = condition.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(condition)
    }

    data class CheckArrayAccess(val index: CgValue, val size: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext): String {
            return "  call void @checkArrayAccess(i32 $index, i32 $size)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                index = index.updateRegisters(registerMap),
                size = size.updateRegisters(registerMap),
            )
        }

        override val inputs: List<CgValue> = listOf(index, size)
    }

    data class BinaryMath(override val result: CgValue.Register, val op: String, val left: CgValue, val right: CgValue) : CgOp() {
        override fun toIr(context: CgContext) = "  $result = $op ${left.type} $left, $right\n"

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                left   = left  .updateRegisters(registerMap),
                right  = right .updateRegisters(registerMap)
            )
        }

        override val inputs: List<CgValue> = listOf(result, left, right)
    }

    data class Label(val name: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext) = "\"$name\":\n"
        override fun updateLabels(labelMap: (String) -> String) = copy(name = labelMap(name))
        override val inputs: List<CgValue> = listOf()
    }

    data class Jump(val dest: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext) = "  br label %\"$dest\"\n"
        override fun updateLabels(labelMap: (String) -> String) = copy(dest = labelMap(dest))
        override val inputs: List<CgValue> = listOf()
    }

    data class Branch(val boolValue: CgValue, val ifTrue: String, val ifFalse: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext): String {
            return "  br i1 $boolValue, label %\"$ifTrue\", label %\"$ifFalse\"\n"
        }

        override fun updateLabels(labelMap: (String) -> String): CgOp {
            return copy(ifTrue = labelMap(ifTrue), ifFalse = labelMap(ifFalse))
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(boolValue = boolValue.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(boolValue)
    }

    data class Switch(val intValue: CgValue, val defaultDest: String, val lookup: List<Pair<Int, String>>) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext): String {
            return lookup.joinToString(separator = " ", postfix = "\n",
                prefix = "  switch ${intValue.type} $intValue, label %\"$defaultDest\" ",
            ) { (value, label) -> "${intValue.type} $value, label %\"$label\"" }
        }

        override fun updateLabels(labelMap: (String) -> String): CgOp {
            return copy(
                defaultDest = labelMap(defaultDest),
                lookup = lookup.map { (value, label) -> value to labelMap(label) } )
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(intValue = intValue.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(intValue)
    }


    // Fork/ParallelBlock/Join do nothing, and if they are not transformed have no effect on the generated code.
    // This results in absolutely correct serial execution. But if transformed we get correct parallel execution.
    data class Fork(val id: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext) = ""
        override val inputs: List<CgValue> = listOf()
    }

    data class ParallelBlock(val id: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext) = ""
        override val inputs: List<CgValue> = listOf()
    }

    data class Join(val id: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext) = ""
        override val inputs: List<CgValue> = listOf()
    }


    data class Phi(override val result: CgValue.Register, val sources: List<Pair<CgValue, String>>) : CgOp() {
        override fun toIr(context: CgContext): String {
            val sourceStr = sources.joinToString { (value, label) -> "[ $value, %\"$label\" ]" }
            return "  $result = phi ${result.type} $sourceStr\n"
        }

        override fun updateLabels(labelMap: (String) -> String): CgOp {
            return copy(
                sources = sources.map { (value, label) -> Pair(value, labelMap(label)) }
            )
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                sources = sources.map { (value, label) -> Pair(value.updateRegisters(registerMap), label) }
            )
        }

        override val inputs: List<CgValue> = sources.map { it.first }
    }

    data class LlvmIr(override val result: CgValue.Register, val pattern: String, override val inputs: List<CgValue>) : CgOp() {
        override fun toIr(context: CgContext): String {
            val p = (listOf(result) + inputs).foldIndexed(pattern) { index, pattern, value ->
                pattern.replace("\${$index}", value.toString())
            }
            return "  $p\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                inputs = inputs.map { it.updateRegisters(registerMap) }
            )
        }
    }

    data class GetElementPtr(
        override val result: CgValue.Register,
        val pointer: CgValue,
        val fieldIndexes: IntArray
    ) : CgOp() {
        init {
            if (result.type !is CgTypePointer || pointer.type !is CgTypePointer)
                throw IllegalArgumentException("Only pointer types allowed")
        }

        override fun toIr(context: CgContext): String {
            val dataType = (pointer.type as CgTypePointer).target
            val indexes = fieldIndexes.joinToString { "i32 $it" }
            return "  $result = getelementptr $dataType, $dataType* $pointer, i32 0, $indexes\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), pointer = pointer.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOfNotNull(pointer)
    }

    data class GetObjectFieldPtr(
        override val result: CgValue.Register,
        val pointer: CgValue,
        val objectName: String,
        val fieldIndex: Int,
        val arrayIndex: CgValue? = null
    ) : CgOp() {
        override fun toIr(context: CgContext): String {
            val dataType = "%\"typeof.object\$$objectName\""
            val arrayIndexStr = arrayIndex?.let { ", ${it.type} $it" } ?: ""
            return "  $result = getelementptr $dataType, ptr $pointer, i32 0, i32 1, i32 $fieldIndex$arrayIndexStr\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                pointer = pointer.updateRegisters(registerMap),
                arrayIndex = arrayIndex?.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOfNotNull(pointer, arrayIndex)
    }

    data class PointerToInt(
        override val result: CgValue.Register,
        val pointer: CgValue
    ) : CgOp() {
        override fun toIr(context: CgContext): String {
            return "  $result = ptrtoint ${pointer.type} $pointer to ${result.type}\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), pointer = pointer.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(pointer)
    }

    data class Load(override val result: CgValue.Register, val pointer: CgValue) : CgOp() {
        override fun toIr(context: CgContext): String {
            return "  $result = load ${result.type}, ${result.type}* $pointer\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), pointer = pointer.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(pointer)
    }

    data class Store(val targetType: CgType, val pointer: CgValue, val value: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            return "  store $targetType $value, $targetType* $pointer\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(pointer = pointer.updateRegisters(registerMap), value = value.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(pointer, value)
    }

    data class ExtractValue(override val result: CgValue.Register, val tuple: CgValue, val fieldIndexes: IntArray) :
        CgOp() {
        constructor(resultName: String, tuple: CgValue, fieldIndexes: IntArray) : this(
            CgValue.Register(
                resultName,
                fieldIndexes.fold(tuple.type) { acc, fieldIndex -> (acc as CgTypeStruct).fields[fieldIndex] }),
            tuple,
            fieldIndexes
        )

        constructor(resultName: Namer, tuple: CgValue, fieldIndexes: IntArray) : this(resultName.toString(), tuple, fieldIndexes)

        override fun toIr(context: CgContext): String {
            return "  $result = extractvalue ${tuple.type} $tuple" + fieldIndexes.joinToString("") { fieldIndex -> ", $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), tuple = tuple.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(tuple)
    }

    data class InsertValue(
        override val result: CgValue.Register,
        val tuple: CgValue,
        val fieldIndexes: IntArray,
        val value: CgValue
    ) : CgOp() {
        constructor(resultName: String, tuple: CgValue, fieldIndexes: IntArray, value: CgValue) : this(
            CgValue.Register(
                resultName,
                tuple.type
            ), tuple, fieldIndexes, value
        )

        constructor(result: CgValue.Register, fieldIndexes: IntArray, value: CgValue) : this(
            result,
            CgValue.undef(result.type),
            fieldIndexes,
            value
        )

        override fun toIr(context: CgContext): String {
            return "  $result = insertvalue ${tuple.type} $tuple, ${value.type} $value" + fieldIndexes.joinToString("") { fieldIndex -> ", $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                tuple = tuple.updateRegisters(registerMap),
                value = value.updateRegisters(registerMap)
            )
        }

        override val inputs: List<CgValue> = listOf(tuple, value)
    }

    data class LoadStaticCallable(
        override val result: CgValue.Register,
        val pointer: CgValue,
        val nameOfFunction: String
    ) : CgOp() {
        constructor(resultName: String, pointer: CgValue, nameOfFunction: String) : this(
            CgValue.Register(
                resultName,
                CgTypeStruct.functionPointer
            ), pointer, nameOfFunction
        )

        init {
            if (result.type != CgTypeStruct.functionPointer)
                throw IllegalArgumentException("LoadStaticCallable result must be CgTypeStruct.functionPointer")
        }

        override fun toIr(context: CgContext): String {
            val tempResult1 = "%\"${result.name}.1\""
            return "  $tempResult1 = insertvalue ${CgTypeStruct.functionPointer} undef, %funptr @\"$nameOfFunction\", 0\n" +
                   "  $result = insertvalue ${CgTypeStruct.functionPointer} $tempResult1, %object* $pointer, 1\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                pointer = pointer.updateRegisters(registerMap)
            )
        }

        override val inputs: List<CgValue> = listOf(pointer)
    }

    data class LoadVirtualCallable(
        override val result: CgValue.Register,
        val pointer: CgValue,
        val nameOfSlot: String
    ) : CgOp() {
        constructor(resultName: String, pointer: CgValue, nameOfSlot: String) : this(
            CgValue.Register(
                resultName,
                CgTypeStruct.functionPointer
            ), pointer, nameOfSlot
        )

        init {
            if (result.type != CgTypeStruct.functionPointer)
                throw IllegalArgumentException("LoadStaticCallable result must be CgTypeStruct.functionPointer")
        }

        override fun toIr(context: CgContext): String {
            val slotId = context.slotNameToId(nameOfSlot)
            val funptr = "%\"${result.name}.funptr\""
            val tmp = "%\"${result.name}.tmp\""
            return "  $funptr = call %funptr @lookupVirtualMethod(%object* $pointer, %size_t $slotId)\n" +
                    "  $tmp = insertvalue ${CgTypeStruct.functionPointer} undef, %funptr $funptr, 0\n" +
                    "  $result = insertvalue ${CgTypeStruct.functionPointer} $tmp, %object* %pointer, 1\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                pointer = pointer.updateRegisters(registerMap)
            )
        }

        override val inputs: List<CgValue> = listOf(pointer)
    }

    data class Call(override val result: CgValue.Register, val methodReg: CgValue, val params: List<CgValue>) : CgOp() {
        init {
            if (result.name.isEmpty())
                throw IllegalArgumentException("Result name must not be empty")
        }

        override fun toIr(context: CgContext): String {
            val paramDecl = params.joinToString("") { ", ${it.type}" }
            val paramStr = params.joinToString("") { ", ${it.type} $it" }
            val prefix = if (result.type == CgTypePrimitive.VOID) "" else "$result = "
            val tempResult1 = "%\"${result.name}.1\""
            val tempResult2 = "%\"${result.name}.2\""
            val tempResult3 = "%\"${result.name}.3\""
            return "  $tempResult1 = extractvalue ${CgTypeStruct.functionPointer} $methodReg, 0\n" +
                    "  $tempResult2 = extractvalue ${CgTypeStruct.functionPointer} $methodReg, 1\n" +
                    "  $tempResult3 = bitcast %size_t* $tempResult1 to ${result.type}(%object*$paramDecl)*\n" +
                    "  ${prefix}call ${result.type} $tempResult3(%object* $tempResult2$paramStr)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                methodReg = methodReg.updateRegisters(registerMap),
                params = params.map { it.updateRegisters(registerMap) })
        }

        override val inputs: List<CgValue> = params + methodReg
    }

    data class CallStatic(
        override val result: CgValue.Register,
        val pointer: CgValue,
        val nameOfFunction: String,
        val params: List<CgValue>
    ) : CgOp() {

        override fun toIr(context: CgContext): String {
            val paramStr = params.joinToString("") { ", ${it.type} $it" }
            val prefix = if (result.type == CgTypePrimitive.VOID) "" else "$result = "
            return "  ${prefix}call ${result.type} @\"$nameOfFunction\"(ptr $pointer$paramStr)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                pointer = pointer.updateRegisters(registerMap),
                params = params.map { it.updateRegisters(registerMap) })
        }

        override val inputs: List<CgValue> = params + pointer
    }

    data class CallVirtual(
        override val result: CgValue.Register,
        val pointer: CgValue,
        val nameOfSlot: String,
        val params: List<CgValue>
    ) : CgOp() {
        init {
            if (result.name.isEmpty())
                throw IllegalArgumentException("Result name must not be empty")
        }

        override fun toIr(context: CgContext): String {
            val slotId = context.slotNameToId(nameOfSlot)
            val paramStr = params.joinToString("") { ", ${it.type} $it" }
            val prefix = if (result.type == CgTypePrimitive.VOID) "" else "$result = "
            val funptr = "%\"${result.name}.funptr\""
            return "  $funptr = call %funptr @lookupVirtualMethod(%object* $pointer, %size_t $slotId)\n" +
                    "  ${prefix}call ${result.type} $funptr(%object* $pointer$paramStr)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                pointer = pointer.updateRegisters(registerMap),
                params = params.map { it.updateRegisters(registerMap) })
        }

        override val inputs: List<CgValue> = params + pointer
    }


    data class DummyObjectOnStack(
        override val result: CgValue.Register,
        val className: String,
        val initValues: List<CgValue>
    ) : CgOp() {
        override fun toIr(context: CgContext): String {
            val objectTypeName = "%\"typeof.object\$$className\""
            val     pointerReg = "%\"${result.name}.ptr\""

            return "  $pointerReg = alloca $objectTypeName\n" +
                    initValues.withIndex().joinToString { (index, value) ->
                        "  %\"${result.name}.$index\" = getelementptr $objectTypeName, $objectTypeName* $pointerReg, i32 0, i32 1, i32 $index\n" +
                        "  store ${value.type} $value, ${value.type}* %\"${result.name}.$index\"\n" } +
                   "  $result = bitcast $objectTypeName* $pointerReg to %object*\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                initValues = initValues.map { it.updateRegisters(registerMap) }
            )
        }

        override val inputs: List<CgValue> = initValues
    }

    data class New(override val result: CgValue.Register, val className: String) : CgOp() {
        override fun toIr(context: CgContext): String {
            val classInfo = CgClassInfo(className)
            return "  $result = call %object* @obj_create(%size_t ptrtoint(${classInfo.objectTypeName}* getelementptr (${classInfo.objectTypeName}, ${classInfo.objectTypeName}* null, i32 1) to %size_t), %vtable* bitcast(${classInfo.vtableTypeName}* ${classInfo.vtableDataName} to %vtable*))\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf()
    }

    data class NewArray(override val result: CgValue.Register, val className: String, val arrayFieldType: CgType, val arrayField: Int, val arraySize: CgValue) : CgOp() {
        override fun toIr(context: CgContext): String {
            val classInfo = CgClassInfo(className)
            val objectEndPtrReg = CgValue.Register("${result.name}.end", CgTypePointer(arrayFieldType))
            val   objectSizeReg = CgValue.Register("${result.name}.size", CgTypePrimitive.INT32)
            return "  $objectEndPtrReg = getelementptr ${classInfo.objectTypeName}, ${classInfo.objectTypeName}* null, i32 0, i32 1, i32 $arrayField, ${arraySize.type} $arraySize\n" +
                   "  $objectSizeReg = ptrtoint $arrayFieldType* $objectEndPtrReg to %size_t\n" +
                   "  $result = call %object* @obj_create(%size_t $objectSizeReg, %vtable* bitcast(${classInfo.vtableTypeName}* ${classInfo.vtableDataName} to %vtable*))\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(arraySize)
    }

    data class Delete(val pointer: CgValue.Register, val className: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            val classInfo = CgClassInfo(className)
            return "  call void ${classInfo.deleteFuncName}(%object* $pointer)\n"
//            return "  call void @deleteObject(%size_t ptrtoint(${classInfo.objectTypeName}* getelementptr (${classInfo.objectTypeName}, ${classInfo.objectTypeName}* null, i32 1) to %size_t), %object* $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(pointer = pointer.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(pointer)
    }

    data class DeleteArray(val pointer: CgValue.Register, val className: String, val arraySize: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            val classInfo = CgClassInfo(className)
            return "  call void ${classInfo.deleteFuncName}(%object* $pointer, i32 $arraySize)\n"
//            val objectEndPtrReg = CgValue.Register("${pointer.name}.end", CgTypePointer(arrayFieldType))
//            val   objectSizeReg = CgValue.Register("${pointer.name}.size", CgTypePrimitive.INT32)
//            return "  $objectEndPtrReg = getelementptr ${classInfo.objectTypeName}, ${classInfo.objectTypeName}* null, i32 0, i32 1, i32 $arrayField, ${arraySize.type} $arraySize\n" +
//                    "  $objectSizeReg = ptrtoint $arrayFieldType* $objectEndPtrReg to %size_t\n" +
//                    "  call %object* @deleteObject(%size_t $objectSizeReg, %object* $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(pointer = pointer.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(arraySize)
    }

    data class Acquire(val pointer: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            return "  call void @obj_acquire(%object* $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(pointer = pointer.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(pointer)
    }

    data class Release(val pointer: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            return "  call void @obj_releaseRef(%object** $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(pointer = pointer.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(pointer)
    }

    data class Return(val returnValue: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            return "  ret ${returnValue.type} $returnValue\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(returnValue = returnValue.updateRegisters(registerMap))
        }

        override val inputs: List<CgValue> = listOf(returnValue)
    }
}
