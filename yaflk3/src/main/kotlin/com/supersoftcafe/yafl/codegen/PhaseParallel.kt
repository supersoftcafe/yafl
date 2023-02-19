package com.supersoftcafe.yafl.codegen



private fun List<CgOp>.allOutputRegisters(): List<CgValue.Register> {
    return map { it.result }.filter { it.type != CgTypePrimitive.VOID }
}

private fun List<CgOp>.allInputRegisters(): List<CgValue.Register> {
    return flatMap { it.inputs }.filterIsInstance<CgValue.Register>()
}


fun phaseParallel(thing: CgThing): List<CgThing> {
    if (thing !is CgThingFunction)
        return listOf(thing)
    val function: CgThingFunction = thing

    val ops = function.body
    val startIndex = ops.indexOfFirst { it is CgOp.Fork }

    val result: List<CgThing> = if (startIndex < 0) {
        listOf(function)
    } else {

        // Found first occurrence of Fork. Grab the Id and split out the operations
        val id = (ops[startIndex] as CgOp.Fork).id
        val endIndex = ops.indexOfLast { it is CgOp.Join && it.id == id }
        if (endIndex < startIndex) throw IllegalArgumentException("Missing CgOp.Join")
        val leftOuterOps = ops.subList(0, startIndex)
        val rightOuterOps = ops.subList(endIndex+1, ops.size)

        // Figure out which registers are transferred in(put) and out(put) of the parallel sections
        val outerOps = leftOuterOps + rightOuterOps
        val innerOps = ops.subList(startIndex+1, endIndex)
        val inputRegisters = outerOps.allOutputRegisters().intersect(innerOps.allInputRegisters().toSet())
        val outputRegisters = innerOps.allOutputRegisters().intersect(outerOps.allInputRegisters().toSet())
        val allRegisters = inputRegisters + outputRegisters

        // Declare structure that will hold transfer values between outer and inner blocks
        val locals = CgTypeStruct(allRegisters.map { it.type })
        val localsLookup = allRegisters.withIndex().associate { (index, value) -> value to index }

        // This is the same register that will be used in all cases (inner and outer) to refer to transfer structure
        val localsReg = CgValue.Register("par.$id", CgTypePointer(locals))

        // Process each block into its own function with a single parameter of the transfer structure
        val functionalBlocks = innerOps.withIndex()
            .filter { (_, value) -> value is CgOp.ParallelBlock }
            .map { (index, _) ->
                val childBodyOps = innerOps.drop(index+1).takeWhile { it !is CgOp.ParallelBlock }

                val childLoadOps = childBodyOps.allInputRegisters().intersect(inputRegisters)
                    .flatMap {
                        val ptr = CgValue.Register("${it.name}.ptr", CgTypePointer(it.type))
                        listOf(
                            CgOp.GetElementPtr(ptr, localsReg, intArrayOf(localsLookup[it]!!)),
                            CgOp.Load(it, ptr)
                        )
                    }

                val childStoreOps = childBodyOps.allOutputRegisters().intersect(outputRegisters)
                    .flatMap {
                        val ptr = CgValue.Register("${it.name}.ptr", CgTypePointer(it.type))
                        listOf(
                            CgOp.GetElementPtr(ptr, localsReg, intArrayOf(localsLookup[it]!!)),
                            CgOp.Store(it.type, ptr, it)
                        )
                    }

                CgThingFunction(
                    "${function.globalName}.par.$id.$index",
                    "",
                    CgTypePrimitive.VOID,
                    listOf(localsReg),
                    childLoadOps + childBodyOps + childStoreOps + CgOp.Return(CgValue.VOID))
            }

        // Generation the function call to fiber_parallel to execute the parallel blocks
        val functionArrayType = CgTypePointer(CgTypeStruct(List(functionalBlocks.size) { CgTypePrimitive.FUNPTR }))
        val functionArrayReg = CgValue.Register("par.$id.blocks", functionArrayType)
        val parentBodyOps = listOf(CgOp.Alloca(functionArrayReg)) + functionalBlocks.flatMapIndexed { index, block ->
            val tmpReg = CgValue.Register("par.$id.f$index", CgTypePointer(CgTypePrimitive.FUNPTR))
            val sourceFunction = CgValue.Global(block.globalName, CgTypePrimitive.FUNPTR)
            listOf(
                CgOp.GetElementPtr(tmpReg, functionArrayReg, intArrayOf(index)),
                CgOp.Store(CgTypePrimitive.FUNPTR, tmpReg, sourceFunction)
            )
        } + CgOp.CallStatic(CgValue.VOID, localsReg, "fiber_parallel",
            listOf(functionArrayReg, CgValue.Immediate(functionalBlocks.size.toString(), CgTypePrimitive.SIZE)))

        // Store in(put) values to the transfer structure
        val parentStoreOps = listOf(CgOp.Alloca(localsReg)) + inputRegisters.flatMap {
            val tmpReg = CgValue.Register("par.$id.${it.name}", CgTypePointer(it.type))
            listOf(
                CgOp.GetElementPtr(tmpReg, localsReg, intArrayOf(localsLookup[it]!!)),
                CgOp.Store(tmpReg.type, tmpReg, it))
        }

        // Load out(put) values from the transfer structure into the original named registers
        val parentLoadOps = outputRegisters.flatMap {
            val tmpReg = CgValue.Register("par.$id.${it.name}", CgTypePointer(it.type))
            listOf(
                CgOp.GetElementPtr(tmpReg, localsReg, intArrayOf(localsLookup[it]!!)),
                CgOp.Load(it, tmpReg))
        }

        // Re-construct the function from the new re-written operations and add the new functions for the blocks
        (listOf<CgThingFunction>(function.copy(body = leftOuterOps + parentStoreOps + parentBodyOps + parentLoadOps + rightOuterOps)) + functionalBlocks)
            // Recursive application until all fork/join blocks are processed
            .flatMap(::phaseParallel)
    }

    return result
}

