package com.supersoftcafe.yafl.translate

import com.supersoftcafe.yafl.ast.Declaration
import com.supersoftcafe.yafl.ast.TypeRef
import com.supersoftcafe.yafl.utils.Namer


/**
 * Find all members up the hierarchy returning duplicate implementations where they are not
 * overridden by the inheritor. Rules are:
 *  1. If all inherited members are without implementation, just pick one to return.
 *  2. If any have implementation, do not return the ones without implementation.
 *  3. Any function at current level overrides inherited ones.
 */
fun Declaration.Klass.flattenClassMembersBySignature(
    findDeclaration: (String, Namer) -> Declaration
): Map<String, List<Declaration.Data>> {
    val inheritedMembersList = extends.map { typeRef ->
        (findDeclaration((typeRef as TypeRef.Named).name, typeRef.id) as Declaration.Klass).flattenClassMembersBySignature(findDeclaration)
    }
    val inheritedMembers = inheritedMembersList
        .flatMap { it.keys }.toSet()
        .associateWith { signature ->
            val identicalMemberList = inheritedMembersList
                .flatMap { it[signature] ?: listOf() }  // Get all funcs for a given signature
                .distinctBy { it.id }                   // Deduplicate diamond pattern issues
            identicalMemberList
                .filter { it.body != null }             // List of implementations
                .ifEmpty { identicalMemberList.take(1) }// Otherwise first prototype
        }

    val ourMembers = members
        .mapNotNull { it.signature }
        .associateWith { signature ->
            // List of implementations for given sig, or first prototype if there are no implementations
            val identicalMemberList = members
                .filter { it.signature == signature }   // Get all funcs for a given signature
            identicalMemberList
                .filter { it.body != null }             // List of implementations
                .ifEmpty { identicalMemberList.take(1) }// Otherwise first prototype
        }

    return inheritedMembers + ourMembers
}