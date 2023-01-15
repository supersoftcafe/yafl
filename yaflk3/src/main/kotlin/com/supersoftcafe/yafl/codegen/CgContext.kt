package com.supersoftcafe.yafl.codegen

class CgContext(val slotNames: Map<String,Int>, val strings: Map<String, CgValue>) {

    fun slotNameToId(slotName: String): Int? = slotNames.get(slotName)
    fun literalStringToGlobalRef(string: String): CgValue? = strings.get(string)

}