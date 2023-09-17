package com.supersoftcafe.yafl.models.llir

enum class CgTypePrimitive(
    override val llvmType: String,
    val subType: CgSubType
) : CgType {
    // Ordered by size-ish

    FLOAT64("double", CgSubType.FLOAT),     // Usually 8 byte alignment
    INT64("i64", CgSubType.INT),            // Might have 4 byte alignment on 32 bit targets

    OBJECT("%object*", CgSubType.POINTER),  // Pointer to base of heap managed object
    FUNPTR("%funptr", CgSubType.POINTER),   // Pointer to first machine code instruction of a function
    POINTER("i8*", CgSubType.POINTER),
    SIZE("%size_t", CgSubType.INT),

    FLOAT32("float", CgSubType.FLOAT),
    INT("%int", CgSubType.INT),
    INT32("i32", CgSubType.INT),
    INT16("i16", CgSubType.INT),
    INT8("i8", CgSubType.INT),
    BOOL("i1", CgSubType.BOOL),
    VOID("void", CgSubType.VOID),
    ;

    override fun toString() = llvmType
}
