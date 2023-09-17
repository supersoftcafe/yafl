package com.supersoftcafe.yafl.passes.p5_generate

import com.supersoftcafe.yafl.models.llir.*
import com.supersoftcafe.yafl.utils.*
import java.io.File

fun generateLlvmIr(things: Iterable<CgThing>): String {
    // Assign identities to virtual method names
    val slotIds = things.asSequence()
        .filterIsInstance<CgThingFunction>().flatten()      // For all operations in all functions
        .filterIsInstance<CgOp.LoadVirtualCallable>()       // Find virtual method resolutions
        .map { it.nameOfSlot }.distinct().sorted()          // Get a unique list of virtual method names
        .mapIndexed { index, name -> Pair(name, index) }    // Assign a unique id to each name
        .toMap()

    val context = CgContext(slotIds, mapOf())

    val code = things.flatMap(::phaseArc).flatMap(::phaseParallel).fold(CgLlvmIr()) { acc, thing -> acc + thing.toIr(context) }
    // val stdlib = CgLlvmIr(stdlib = CgOp::class.java.getResource("/stdlib.ll")!!.readText())
    val stdlib = CgLlvmIr(stdlib = File("/Users/mbrown/Projects/yafl/yaflk3/src/main/resources/stdlib.ll").readText())
    val combined = stdlib + code

    return combined.toString()
}

fun optimizeLlvmIr(text: String): Either<String> {
    return "opt --O1 -S".runCommand(text)
}

