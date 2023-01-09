package com.supersoftcafe.yafl.codegen

sealed class CgOp {
    abstract val result: CgValue.Register
    abstract fun toIr(context: CgContext): String

    open fun updateLabels(labelMap: (String) -> String): CgOp = this
    open fun updateRegisters(registerMap: (String) -> String): CgOp = this

    data class Alloca(override val result: CgValue.Register) : CgOp() {
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
    }

    data class CheckArrayAccess(val index: CgValue, val size: Int): CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext): String {
            return "  call tailcc void @checkArrayAccess(i32 $index, i32 $size)\n"
        }
        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(index = index.updateRegisters(registerMap))
        }
    }

    data class Label(val name: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext) = "\"$name\":\n"
        override fun updateLabels(labelMap: (String) -> String) = copy(name = labelMap(name))
    }

    data class Jump(val dest: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID
        override fun toIr(context: CgContext) = "  br label %\"$dest\"\n"
        override fun updateLabels(labelMap: (String) -> String) = copy(dest = labelMap(dest))
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
    }

    data class LlvmIr(override val result: CgValue.Register, val pattern: String, val inputs: List<CgValue>): CgOp() {
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

    data class GetElementPtr(override val result: CgValue.Register, val pointer: CgValue, val indexes: List<CgValue>) : CgOp() {
        override fun toIr(context: CgContext): String {
            val dataType = when (pointer) {
                is CgValue.Register -> when (val type = pointer.type) {
                    is CgTypePointer -> type.target.toString()
                    else -> throw IllegalArgumentException("Registers must be of pointer type")
                }
                is CgValue.Global -> when (val type = pointer.type) {
                    is CgTypeStruct, is CgTypeArray -> type.toString()
                    else -> throw IllegalArgumentException("Globals must be of struct or array type")
                }
                else -> throw IllegalArgumentException("pointer must be register or global")
            }

            return indexes.joinToString("", "  $result = getelementptr $dataType, $dataType* $pointer", "\n") { ", i32 $it" }
        }
    }

    data class GetObjectFieldPtr(override val result: CgValue.Register, val pointer: CgValue, val objectName: String, val fieldIndex: Int = -1) : CgOp() {
        override fun toIr(context: CgContext): String {
            val dataType = "%\"typeof.object\$$objectName\""
            val tempRegister = "%\"${result.name}.object\""
            return "  $tempRegister = bitcast %object* $pointer to $dataType*\n" +
                   "  $result = getelementptr $dataType, $dataType* $tempRegister, i32 0, i32 1" + (if (fieldIndex >= 0) ", i32 $fieldIndex\n" else "\n")
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Load(override val result: CgValue.Register, val pointer: CgValue) : CgOp() {
        override fun toIr(context: CgContext): String {
            return "  $result = load ${result.type}, ${result.type}* $pointer\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Store(val targetType: CgType, val pointer: CgValue, val value: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            return "  store $targetType $value, $targetType* $pointer\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(pointer = pointer.updateRegisters(registerMap), value = value.updateRegisters(registerMap))
        }
    }

    data class ExtractValue(override val result: CgValue.Register, val tuple: CgValue, val fieldIndexes: IntArray) : CgOp() {
        constructor(resultName: String, tuple: CgValue, fieldIndexes: IntArray) : this(CgValue.Register(resultName, fieldIndexes.fold(tuple.type) { acc, fieldIndex -> (acc as CgTypeStruct).fields[fieldIndex] }), tuple, fieldIndexes)

        override fun toIr(context: CgContext): String {
            return "  $result = extractvalue ${tuple.type} $tuple" + fieldIndexes.joinToString("") { fieldIndex -> ", $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), tuple = tuple.updateRegisters(registerMap))
        }
    }

    data class InsertValue(override val result: CgValue.Register, val tuple: CgValue, val fieldIndexes: IntArray, val value: CgValue) : CgOp() {
        constructor(resultName: String, tuple: CgValue, fieldIndexes: IntArray, value: CgValue) : this(CgValue.Register(resultName, tuple.type), tuple, fieldIndexes, value)
        constructor(result: CgValue.Register, fieldIndexes: IntArray, value: CgValue) : this(result, CgValue.undef(result.type), fieldIndexes, value)

        override fun toIr(context: CgContext): String {
            return "  $result = insertvalue ${tuple.type} $tuple, ${value.type} $value" + fieldIndexes.joinToString("") { fieldIndex -> ", $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), tuple = tuple.updateRegisters(registerMap), value = value.updateRegisters(registerMap))
        }
    }

    data class LoadStaticCallable(override val result: CgValue.Register, val pointer: CgValue, val nameOfFunction: String) : CgOp() {
        constructor(resultName: String, pointer: CgValue, nameOfFunction: String) : this(CgValue.Register(resultName, CgTypeStruct.functionPointer), pointer, nameOfFunction)

        init {
            if (result.type != CgTypeStruct.functionPointer)
                throw IllegalArgumentException("LoadStaticCallable result must be CgTypeStruct.functionPointer")
        }

        override fun toIr(context: CgContext): String {
            val typeOfFunctionName = "%\"typeof.$nameOfFunction\""
            val tempResult2 = "%\"${result.name}.2\""
            val tempResult1 = "%\"${result.name}.1\""
            return "  $tempResult2 = bitcast $typeOfFunctionName* @\"$nameOfFunction\" to %funptr\n" +
                   "  $tempResult1 = insertvalue ${CgTypeStruct.functionPointer} undef, %funptr $tempResult2, 0\n" +
                   "  $result = insertvalue ${CgTypeStruct.functionPointer} $tempResult1, %object* $pointer, 1\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                pointer = pointer.updateRegisters(registerMap)
            )
        }
    }

    data class LoadVirtualCallable(override val result: CgValue.Register, val pointer: CgValue, val nameOfSlot: String) : CgOp() {
        constructor(resultName: String, pointer: CgValue, nameOfSlot: String) : this(CgValue.Register(resultName, CgTypeStruct.functionPointer), pointer, nameOfSlot)

        init {
            if (result.type != CgTypeStruct.functionPointer)
                throw IllegalArgumentException("LoadStaticCallable result must be CgTypeStruct.functionPointer")
        }

        override fun toIr(context: CgContext): String {
            val slotId = context.slotNameToId(nameOfSlot)
            val funptr = "%\"${result.name}.funptr\""
            val tmp = "%\"${result.name}.tmp\""
            return "  $funptr = tail call tailcc %funptr @lookupVirtualMethod(%object* $pointer, %size_t $slotId)\n" +
                   "  $tmp = insertvalue ${CgTypeStruct.functionPointer} undef, %funptr $funptr, 0\n" +
                   "  $result = insertvalue ${CgTypeStruct.functionPointer} $tmp, %object* %pointer, 1\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(
                result = result.updateRegisters(registerMap),
                pointer = pointer.updateRegisters(registerMap)
            )
        }
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
                   "  ${prefix}tail call tailcc ${result.type} $tempResult3(%object* $tempResult2$paramStr)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), methodReg = methodReg.updateRegisters(registerMap), params = params.map { it.updateRegisters(registerMap) })
        }
    }

    data class CallStatic(override val result: CgValue.Register, val pointer: CgValue, val nameOfFunction: String, val params: List<CgValue>) : CgOp() {
        init {
            if (result.name.isEmpty())
                throw IllegalArgumentException("Result name must not be empty")
        }

        override fun toIr(context: CgContext): String {
            val paramStr = params.joinToString("") { ", ${it.type} $it" }
            val prefix = if (result.type == CgTypePrimitive.VOID) "" else "$result = "
            return "  ${prefix}tail call tailcc ${result.type} @\"$nameOfFunction\"(%object* $pointer$paramStr)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), pointer = pointer.updateRegisters(registerMap), params = params.map { it.updateRegisters(registerMap) })
        }
    }

    data class CallVirtual(override val result: CgValue.Register, val pointer: CgValue, val nameOfSlot: String, val params: List<CgValue>): CgOp() {
        init {
            if (result.name.isEmpty())
                throw IllegalArgumentException("Result name must not be empty")
        }

        override fun toIr(context: CgContext): String {
            val slotId = context.slotNameToId(nameOfSlot)
            val paramStr = params.joinToString("") { ", ${it.type} $it" }
            val prefix = if (result.type == CgTypePrimitive.VOID) "" else "$result = "
            val funptr = "%\"${result.name}.funptr\""
            return "  $funptr = tail call tailcc %funptr @lookupVirtualMethod(%object* $pointer, %size_t $slotId)\n" +
                   "  ${prefix}tail call tailcc ${result.type} $funptr(%object* $pointer$paramStr)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap), pointer = pointer.updateRegisters(registerMap), params = params.map { it.updateRegisters(registerMap) })
        }
    }

    data class New(override val result: CgValue.Register, val className: String) : CgOp() {
        override fun toIr(context: CgContext): String {
            val vtableDataName = "@\"vtable\$$className\""
            val objectTypeName = "%\"typeof.object\$$className\""
            val vtableTypeName = "%\"typeof.vtable\$$className\""
            return "  $result = tail call tailcc %object* @newObject(%size_t ptrtoint($objectTypeName* getelementptr ($objectTypeName, $objectTypeName* null, i32 1) to %size_t), %vtable* bitcast($vtableTypeName* $vtableDataName to %vtable*))\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = result.updateRegisters(registerMap))
        }
    }

    data class Delete(val pointer: CgValue, val className: String) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            val vtableDataName = "@\"vtable\$$className\""
            val objectTypeName = "%\"typeof.object\$$className\""
            val vtableTypeName = "%\"typeof.vtable\$$className\""
            return "  tail call tailcc void @deleteObject(%size_t ptrtoint($objectTypeName* getelementptr ($objectTypeName, $objectTypeName* null, i32 1) to %size_t), %object* $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return Acquire(pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Acquire(val pointer: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            return "  tail call tailcc void @acquire(%object* $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return Acquire(pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Release(val pointer: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            return "  tail call tailcc void @release(%object** $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return Release(pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Return(val returnValue: CgValue) : CgOp() {
        override val result: CgValue.Register get() = CgValue.VOID

        override fun toIr(context: CgContext): String {
            return "  ret ${returnValue.type} $returnValue\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(returnValue = returnValue.updateRegisters(registerMap))
        }
    }
}
