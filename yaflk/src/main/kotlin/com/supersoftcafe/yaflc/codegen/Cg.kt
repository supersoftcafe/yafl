package com.supersoftcafe.yaflc.codegen

import com.supersoftcafe.yaflc.utils.*


private inline fun <reified TElement : CgThing> Iterable<CgThing>.toIr(context: CgContext, toIr: (TElement, CgContext) -> CgLlvmIr) =
    asSequence().filterIsInstance<TElement>().fold(CgLlvmIr()) { acc, value -> acc + toIr(value, context) }

fun generateLlvmIr(things: Iterable<CgThing>): Either<String> {
    // Assign identities to virtual method names
    val slotIds = things.asSequence()
        .filterIsInstance<CgThingFunction>().flatten()      // For all operations in all functions
        .filterIsInstance<CgOp.LoadVirtualCallable>()       // Find virtual method resolutions
        .map { it.nameOfSlot }.distinct().sorted()          // Get a unique list of virtual method names
        .mapIndexed { index, name -> Pair(name, index) }    // Assign a unique id to each name
        .toMap()

    val   context = CgContext(slotIds)
    val   classes = things.toIr(context, CgThingClass::toIr)
    val functions = things.toIr(context, CgThingFunction::toIr)
    val    stdlib = CgLlvmIr(stdlib = CgOp::class.java.getResource("/stdlib.ll")!!.readText())

    val combined = stdlib + classes + functions

    return Some(combined.toString())
}

fun optimizeLlvmIr(text: String): Either<String> {
    return "opt --O3 -S".runCommand(text)
}

