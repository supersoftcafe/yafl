package com.supersoftcafe.yafl.codegen

import com.supersoftcafe.yafl.utils.*


private inline fun <reified TElement : CgThing> Iterable<CgThing>.toIr(
    context: CgContext,
    toIr: (TElement, CgContext) -> CgLlvmIr,
    vararg translations: (TElement) -> TElement
) = asSequence().filterIsInstance<TElement>()
    .map { el -> translations.fold(el) { acc, op -> op(acc) } }
    .fold(CgLlvmIr()) { acc, value -> acc + toIr(value, context) }

fun generateLlvmIr(things: Iterable<CgThing>): Either<String,List<String>> {
    // Assign identities to virtual method names
    val slotIds = things.asSequence()
        .filterIsInstance<CgThingFunction>().flatten()      // For all operations in all functions
        .filterIsInstance<CgOp.LoadVirtualCallable>()       // Find virtual method resolutions
        .map { it.nameOfSlot }.distinct().sorted()          // Get a unique list of virtual method names
        .mapIndexed { index, name -> Pair(name, index) }    // Assign a unique id to each name
        .toMap()

    val context   = CgContext(slotIds)

    val classes = things.toIr(context, CgThingClass::toIr)
    val variables = things.toIr(context, CgThingVariable::toIr)
    val functions = things.toIr(context, CgThingFunction::toIr, ::arcPhase)
    val externFunctions = things.toIr(context, CgThingExternalFunction::toIr)
    val stdlib = CgLlvmIr(stdlib = CgOp::class.java.getResource("/stdlib.ll")!!.readText())

    val combined = stdlib + externFunctions + classes + variables + functions

    return Either.Some(combined.toString())
}

fun optimizeLlvmIr(text: String): Either<String,List<String>> {
    return "opt --O1 -S".runCommand(text)
}

