package com.supersoftcafe.yafl.codegen

enum class CgTypePrimitive(override val llvmType: String, val subType: CgSubType) : CgType {
    VOID("void", CgSubType.VOID),
    BOOL("i1", CgSubType.BOOL),
    INT8("i8", CgSubType.INT),
    INT16("i16", CgSubType.INT),
    INT32("i32", CgSubType.INT),
    INT64("i64", CgSubType.INT),
    FLOAT32("float", CgSubType.FLOAT),
    FLOAT64("double", CgSubType.FLOAT),
    OBJECT("%object*", CgSubType.POINTER), // Pointer to base of heap managed object
    CALLABLE("i32*", CgSubType.POINTER);   // Pointer to first machine code instruction of a function

    override fun toString() = llvmType
}
