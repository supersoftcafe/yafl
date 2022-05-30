package com.supersoftcafe.yaflc

import kotlinx.collections.immutable.PersistentList
import kotlinx.collections.immutable.persistentListOf

typealias Errors = PersistentList<Pair<SourceRef, String>>
typealias Finder = ((Declaration) -> Boolean) -> List<Declaration>
typealias NodePath = PersistentList<INode>

inline fun <T> Iterable<T>.foldErrors(lambda: (T) -> Errors): Errors {
    return fold(persistentListOf()) { list, value -> list.addAll(lambda(value)) }
}