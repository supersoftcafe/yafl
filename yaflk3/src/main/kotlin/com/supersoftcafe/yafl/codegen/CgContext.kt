package com.supersoftcafe.yafl.codegen

class CgContext(val slotNames: Map<String,Int>) {

    fun slotNameToId(slotName: String): Int? = slotNames.get(slotName)

}