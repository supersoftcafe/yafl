package com.supersoftcafe.yafl.codegen

import com.supersoftcafe.yafl.utils.*

fun generateLlvmIr(things: Iterable<CgThing>): Either<String,List<String>> {
    // Assign identities to virtual method names
    val slotIds = things.asSequence()
        .filterIsInstance<CgThingFunction>().flatten()      // For all operations in all functions
        .filterIsInstance<CgOp.LoadVirtualCallable>()       // Find virtual method resolutions
        .map { it.nameOfSlot }.distinct().sorted()          // Get a unique list of virtual method names
        .mapIndexed { index, name -> Pair(name, index) }    // Assign a unique id to each name
        .toMap()

    val context = CgContext(slotIds, mapOf())

    val code = things.flatMap(::phaseArc).flatMap(::phaseParallel).fold(CgLlvmIr()) { acc, thing -> acc + thing.toIr(context) }
    val stdlib = CgLlvmIr(stdlib = CgOp::class.java.getResource("/stdlib.ll")!!.readText())
    val combined = stdlib + code

    return Either.Some(combined.toString())
}

fun optimizeLlvmIr(text: String): Either<String,List<String>> {
    return "opt --O1 -S".runCommand(text)
}

