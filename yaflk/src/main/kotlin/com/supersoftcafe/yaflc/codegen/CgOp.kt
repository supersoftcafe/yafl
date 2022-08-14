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
        override fun toIr(context: CgContext) = "$name:\n"
        override fun updateLabels(labelMap: (String) -> String) = copy(name = labelMap(name))
    }

    data class Jump(val dest: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID
        override fun toIr(context: CgContext) = "  br label %$dest\n"
        override fun updateLabels(labelMap: (String) -> String) = copy(dest = labelMap(dest))
    }

    data class Branch(val boolReg: String, val ifTrue: String, val ifFalse: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID
        override fun toIr(context: CgContext): String {
            return "  br i1 $boolReg, label %$ifTrue, label %$ifFalse\n"
        }

        override fun updateLabels(labelMap: (String) -> String): CgOp {
            return copy(ifTrue = labelMap(ifTrue), ifFalse = labelMap(ifFalse))
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(boolReg = registerMap(boolReg))
        }
    }

    data class Phi(override val result: String, override val resultType: CgType, val sources: List<Pair<String, String>>) : CgOp() {
        override fun toIr(context: CgContext): String {
            val sourceStr = sources.joinToString { (value, label) -> "[ $value, %$label ]" }
            return "  $result = phi $resultType $sourceStr\n"
        }

        override fun updateLabels(labelMap: (String) -> String): CgOp {
            return copy(sources = sources.map { (value, label) -> Pair(value, labelMap(label)) })
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), sources = sources.map { (value, label) -> Pair(registerMap(value), label) })
        }
    }

    data class Binary(override val result: String, override val resultType: CgType, val op: CgBinaryOp, val input1: String, val input2: String) : CgOp() {
        override fun toIr(context: CgContext): String {
            return "  $result = $op $resultType $input1, $input2\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), input1 = registerMap(input1), input2 = registerMap(input2))
        }
    }

    data class GetObjectFieldPtr(override val result: String, val pointer: String, val dataType: CgType, val fieldIndexes: IntArray) : CgOp() {
        override val resultType = CgTypePointer( fieldIndexes.fold(dataType) { acc, fieldIndex -> (acc as CgTypeStruct).fields[fieldIndex] })

        override fun toIr(context: CgContext): String {
            return "  $result.object = bitcast %object* $pointer to $dataType*\n" +
                   "  $result = getelementptr $dataType, $dataType* $result.object, i32 0, i32 1" + fieldIndexes.joinToString("") { fieldIndex -> ", i32 $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), pointer = registerMap(pointer))
        }
    }

    data class Load(override val result: String, override val resultType: CgType, val name: String) : CgOp() {
        override fun toIr(context: CgContext): String {
            return "  $result = load $resultType, $resultType* $name\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), name = registerMap(name))
        }
    }

    data class Store(val targetType: CgType, val name: String, val value: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID

        override fun toIr(context: CgContext): String {
            return "  store $targetType $value, $targetType* $name\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(name = registerMap(name), value = registerMap(value))
        }
    }

    data class ExtractValue(override val result: String, val structReg: String, val structType: CgType, val fieldIndexes: IntArray) : CgOp() {
        override val resultType = fieldIndexes.fold(structType) { acc, fieldIndex -> (acc as CgTypeStruct).fields[fieldIndex] }

        override fun toIr(context: CgContext): String {
            return "  $result = extractvalue $structType $structReg" + fieldIndexes.joinToString("") { fieldIndex -> ", $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), structReg = registerMap(structReg))
        }
    }

    data class InsertValue(override val result: String, val structReg: String, val structType: CgTypeStruct, val fieldIndexes: IntArray, val value: String, val valueType: CgType) : CgOp() {
        override val resultType: CgType get() = structType

        override fun toIr(context: CgContext): String {
            return "  $result = insertvalue $structType $structReg, $valueType $value" + fieldIndexes.joinToString("") { fieldIndex -> ", $fieldIndex" } + "\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), structReg = registerMap(structReg), value = registerMap(value))
        }
    }

    data class LoadStaticCallable(override val result: String, val objectReg: String, val nameOfFunction: String) : CgOp() {
        override val resultType: CgType get() = CgTypePrimitive.CALLABLE
        override fun toIr(context: CgContext): String {
            return "  $result.2 = bitcast %typeof.$nameOfFunction* @$nameOfFunction to %size_t*" +
                   "  $result.1 = insertvalue %lambda undef, %size_t* $result.2, 0\n" +
                   "  $result = insertvalue %lambda $result.1, %object* $objectReg, 1\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), objectReg = registerMap(objectReg))
        }
    }

    data class LoadVirtualCallable(override val result: String, val objectReg: String, val nameOfSlot: String) : CgOp() {
        override val resultType: CgType get() = CgTypePrimitive.CALLABLE
        override fun toIr(context: CgContext): String {
            val slotId = context.slotNameToId(nameOfSlot)
            return "  $result = call %lambda @lookupVirtualMethod(%object* $objectReg, %size_t $slotId)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), objectReg = registerMap(objectReg))
        }
    }

    data class Call(override val result: String, override val resultType: CgType, val methodReg: String, val params: List<Pair<CgType, String>>) : CgOp() {
        init {
            if (result.isEmpty())
                throw IllegalArgumentException("Result must not be empty")
        }

        override fun toIr(context: CgContext): String {
            val paramDecl = params.joinToString("") { (type, _) -> ", $type" }
            val paramStr = params.joinToString("") { (type, value) -> ", $type $value" }
            val prefix = if (resultType == CgTypePrimitive.VOID) "" else "$result = "
            return "  $result.1 = extractvalue %lambda $methodReg, 0\n" +
                   "  $result.2 = extractvalue %lambda $methodReg, 1\n" +
                   "  $result.3 = bitcast %size_t* $result.1 to $resultType(%object*$paramDecl)*\n" +
                   "  ${prefix}tail call tailcc $resultType $result.3(%object* $result.2$paramStr)\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(result = registerMap(result), methodReg = registerMap(methodReg), params = params.map { (type, value) -> Pair(type, registerMap(value)) })
        }
    }

    data class New(override val result: String, val className: String) : CgOp() {
        override val resultType: CgType get() = CgTypePrimitive.OBJECT
        override fun toIr(context: CgContext): String {
            return "  $result = tail call tailcc %object* @newObject(%size_t " +
                   "ptrtoint( %typeof.object\$$className* getelementptr ( %typeof.object\$$className, %typeof.object\$$className* null, i32 1 ) to %size_t)" +
                   ", %vtable* bitcast( %typeof.vtable\$$className* @$className to %vtable*))\n"
        }
    }

    data class Acquire(val objectReg: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID
        override fun toIr(context: CgContext): String {
            return "  tail call tailcc void @acquire(%object* $objectReg)\n"
        }
    }

    data class Release(val variableName: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID
        override fun toIr(context: CgContext): String {
            return "  tail call tailcc void @release(%object** $variableName)\n"
        }
    }

    data class Return(val returnType: CgType, val returnReg: String) : CgOp() {
        override val result: String get() = ""
        override val resultType: CgType get() = CgTypePrimitive.VOID
        override fun toIr(context: CgContext): String {
            return "  ret $returnType $returnReg\n"
        }

        override fun updateRegisters(registerMap: (String) -> String): CgOp {
            return copy(returnReg = registerMap(returnReg))
        }
    }
}
