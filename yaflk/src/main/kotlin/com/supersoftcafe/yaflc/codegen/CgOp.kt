package com.supersoftcafe.yaflc.codegen

sealed class CgOp {
    abstract val result: String
    abstract val resultType: CgType
    abstract fun toIr(context: CgContext): String

    open fun updateLabels(labelMap: (String) -> String): CgOp = this
    open fun updateRegisters(registerMap: (String) -> String): CgOp = this

    data class Label(val name: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID
        override fun toIr(context: CgContext) = "${name.escape()}:\n"
        override fun updateLabels(labelMap: (String) -> String) = copy(name = labelMap(name))
    }

    data class Jump(val dest: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID
        override fun toIr(context: CgContext) = "  br label %${dest.escape()}\n"
        override fun updateLabels(labelMap: (String) -> String) = copy(dest = labelMap(dest))
    }

    data class Branch(val boolReg: String, val ifTrue: String, val ifFalse: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID
        override fun toIr(context: CgContext): String {
            return "  br i1 $boolReg, label %${ifTrue.escape()}, label %${ifFalse.escape()}\n"
        }

        override fun updateLabels(labelMap: (String) -> String): CgOp {
            return copy(ifTrue = labelMap(ifTrue), ifFalse = labelMap(ifFalse))
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(boolReg = registerMap(boolReg))
        }
    }

    data class Phi(override val result: String, override val resultType: CgType, val sources: List<Pair<CgValue, String>>) : CgOp() {
        override fun toIr(context: CgContext): String {
            val sourceStr = sources.joinToString { (value, label) -> "[ $value, %${label.escape()} ]" }
            return "  %${result.escape()} = phi $resultType $sourceStr\n"
        }

        override fun updateLabels(labelMap: (String) -> String): CgOp {
            return copy(sources = sources.map { (value, label) -> Pair(value, labelMap(label)) })
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), sources = sources.map { (value, label) -> Pair(value.updateRegisters(registerMap), label) })
        }
    }

    data class Binary(override val result: String, override val resultType: CgType, val op: CgBinaryOp, val input1: String, val input2: String) : CgOp() {
        override fun toIr(context: CgContext): String {
            return "  %${result.escape()} = $op $resultType $input1, $input2\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), input1 = registerMap(input1), input2 = registerMap(input2))
        }
    }

    data class GetObjectFieldPtr(override val result: String, val pointer: CgValue, val dataType: CgType, val fieldIndexes: IntArray) : CgOp() {
        override val resultType = CgTypePointer( fieldIndexes.fold(dataType) { acc, fieldIndex -> (acc as CgTypeStruct).fields[fieldIndex] })

        override fun toIr(context: CgContext): String {
            val tempRegister = CgValue.Register("$result.object")
            return "  $tempRegister = bitcast %object* $pointer to $dataType*\n" +
                   "  %${result.escape()} = getelementptr $dataType, $dataType* $tempRegister, i32 0, i32 1" + fieldIndexes.joinToString("") { fieldIndex -> ", i32 $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Load(override val result: String, override val resultType: CgType, val pointer: CgValue) : CgOp() {
        override fun toIr(context: CgContext): String {
            return "  %${result.escape()} = load $resultType, $resultType* $pointer\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Store(val targetType: CgType, val pointer: CgValue, val value: CgValue) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID

        override fun toIr(context: CgContext): String {
            return "  store $targetType $value, $targetType* $pointer\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(pointer = pointer.updateRegisters(registerMap), value = value.updateRegisters(registerMap))
        }
    }

    data class ExtractValue(override val result: String, val tuple: CgValue, val structType: CgType, val fieldIndexes: IntArray) : CgOp() {
        override val resultType = fieldIndexes.fold(structType) { acc, fieldIndex -> (acc as CgTypeStruct).fields[fieldIndex] }

        override fun toIr(context: CgContext): String {
            return "  %${result.escape()} = extractvalue $structType $tuple" + fieldIndexes.joinToString("") { fieldIndex -> ", $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), tuple = tuple.updateRegisters(registerMap))
        }
    }

    data class InsertValue(override val result: String, val tuple: CgValue, val structType: CgTypeStruct, val fieldIndexes: IntArray, val value: CgValue, val valueType: CgType) : CgOp() {
        override val resultType: CgType get() = structType

        override fun toIr(context: CgContext): String {
            return "  %${result.escape()} = insertvalue $structType $tuple, $valueType $value" + fieldIndexes.joinToString("") { fieldIndex -> ", $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), tuple = tuple.updateRegisters(registerMap), value = value.updateRegisters(registerMap))
        }
    }

    data class LoadStaticCallable(override val result: String, val pointer: CgValue, val nameOfFunction: String) : CgOp() {
        override val resultType: CgType get() = CgTypePrimitive.CALLABLE
        override fun toIr(context: CgContext): String {
            val typeOfFunctionName = "typeof.$nameOfFunction"
            val tempResult2 = CgValue.Register("$result.2")
            val tempResult1 = CgValue.Register("$result.1")
            return "  $tempResult2 = bitcast %${typeOfFunctionName.escape()}* @${nameOfFunction.escape()} to %size_t*" +
                   "  $tempResult1 = insertvalue %lambda undef, %size_t* $tempResult2, 0\n" +
                   "  %${result.escape()} = insertvalue %lambda $tempResult1, %object* $pointer, 1\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class LoadVirtualCallable(override val result: String, val pointer: CgValue, val nameOfSlot: String) : CgOp() {
        override val resultType: CgType get() = CgTypePrimitive.CALLABLE

        override fun toIr(context: CgContext): String {
            val slotId = context.slotNameToId(nameOfSlot)
            return "  %${result.escape()} = call %lambda @lookupVirtualMethod(%object* $pointer, %size_t $slotId)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Call(override val result: String, override val resultType: CgType, val methodReg: CgValue, val params: List<Pair<CgType, CgValue>>) : CgOp() {
        init {
            if (result.isEmpty())
                throw IllegalArgumentException("Result must not be empty")
        }

        override fun toIr(context: CgContext): String {
            val paramDecl = params.joinToString("") { (type, _) -> ", $type" }
            val paramStr = params.joinToString("") { (type, value) -> ", $type $value" }
            val prefix = if (resultType == CgTypePrimitive.VOID) "" else "%${result.escape()} = "
            val tempResult1 = CgValue.Register("$result.1")
            val tempResult2 = CgValue.Register("$result.2")
            val tempResult3 = CgValue.Register("$result.3")
            return "  $tempResult1 = extractvalue %lambda $methodReg, 0\n" +
                   "  $tempResult2 = extractvalue %lambda $methodReg, 1\n" +
                   "  $tempResult3 = bitcast %size_t* $tempResult1 to $resultType(%object*$paramDecl)*\n" +
                   "  ${prefix}tail call tailcc $resultType $tempResult3(%object* $tempResult2$paramStr)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), methodReg = methodReg.updateRegisters(registerMap), params = params.map { (type, value) -> Pair(type, value.updateRegisters(registerMap)) })
        }
    }

    data class New(override val result: String, val className: String) : CgOp() {
        override val resultType: CgType get() = CgTypePrimitive.OBJECT
        override fun toIr(context: CgContext): String {
            val vtableDataName = CgValue.Global("vtable\$$className")
            val objectTypeName = CgValue.Register("typeof.object\$$className")
            val vtableTypeName = CgValue.Register("typeof.vtable\$$className")
            return "  ${result.escape()} = tail call tailcc %object* @newObject(%size_t ptrtoint($objectTypeName* getelementptr ($objectTypeName, $objectTypeName* null, i32 1) to %size_t), %vtable* bitcast($vtableTypeName* $vtableDataName to %vtable*))\n"
        }
    }

    data class Acquire(val pointer: CgValue) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID

        override fun toIr(context: CgContext): String {
            return "  tail call tailcc void @acquire(%object* $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return Acquire(pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Release(val pointer: CgValue) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID

        override fun toIr(context: CgContext): String {
            return "  tail call tailcc void @release(%object** $pointer)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return Release(pointer = pointer.updateRegisters(registerMap))
        }
    }

    data class Return(val returnType: CgType, val returnValue: CgValue) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID

        override fun toIr(context: CgContext): String {
            return "  ret $returnType $returnValue\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(returnValue = returnValue.updateRegisters(registerMap))
        }
    }
}
