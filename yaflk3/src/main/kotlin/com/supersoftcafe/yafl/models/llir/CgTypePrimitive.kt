package com.supersoftcafe.yafl.models.llir

enum class CgTypePrimitive(override val llvmType: String, val subType: CgSubType, val approxSize: Int) : CgType {
    // Ordered by size-ish

    FLOAT64("double", CgSubType.FLOAT, 8),
    INT64("i64", CgSubType.INT, 8),
    OBJECT("%object*", CgSubType.POINTER, 6), // Pointer to base of heap managed object
    FUNPTR("%funptr", CgSubType.POINTER, 6),   // Pointer to first machine code instruction of a function
    POINTER("i8*", CgSubType.POINTER, 6),
    SIZE("%size_t", CgSubType.INT, 6),
    INT("%int", CgSubType.INT, 4),
    FLOAT32("float", CgSubType.FLOAT, 4),
    INT32("i32", CgSubType.INT, 4),
    INT16("i16", CgSubType.INT, 2),
    INT8("i8", CgSubType.INT, 1),
    BOOL("i1", CgSubType.BOOL, 1),
    VOID("void", CgSubType.VOID, 0),
    ;

    override fun toString() = llvmType
}
