package graph


class Graph<TNode> private constructor(private val nodes: List<TNode?>, private val edges: List<Edge>) {
    private data class Edge(val node1: Int, val node2: Int)
    constructor() : this(emptyList(), emptyList())


    private fun nodeToIndex(node: TNode): Int {
        val index = nodes.indexOfFirst { it === node }
        if (index < 0) throw IllegalArgumentException("Node not found");
        return index;
    }


    fun addEdge(node1: TNode, node2: TNode): Graph<TNode> {
        val node1Index = nodeToIndex(node1)
        val node2Index = nodeToIndex(node2)
        val edge = Edge(node1Index, node2Index)
        if (edge in edges) throw IllegalArgumentException("Edge already exists")
        return Graph(nodes, edges + edge)
    }

    fun removeEdge(node1: TNode, node2: TNode): Graph<TNode> {
        val node1Index = nodeToIndex(node1)
        val node2Index = nodeToIndex(node2)
        val edge = Edge(node1Index, node2Index)
        return Graph(nodes, edges - edge)
    }

    fun addNode(node: TNode): Graph<TNode> {
        if (node in nodes) throw IllegalArgumentException("Node already exists")
        val emptyIndex = nodes.indexOfFirst { it === null }
        val newNodes = if (emptyIndex < 0) nodes + node else nodes.mapIndexed { i, it -> if (i == emptyIndex) node else it }
        return Graph(newNodes, edges)
    }

    fun removeNode(node: TNode): Graph<TNode> {
        val nodeIndex = nodeToIndex(node)
        val newNodes = nodes.mapIndexed { i, it -> if (i == nodeIndex) null else it }
        val newEdges = edges.filter { it.node1 != nodeIndex && it.node2 != nodeIndex }
        return Graph(newNodes, newEdges)
    }

    fun findOuterEdges(node: TNode): List<TNode> {
        val nodeIndex = nodeToIndex(node)
        return edges.mapNotNull { if (it.node1 == nodeIndex) nodes[it.node2] else null }
    }

    fun findInnerEdges(node: TNode): List<TNode> {
        val nodeIndex = nodeToIndex(node)
        return edges.mapNotNull { if (it.node2 == nodeIndex) nodes[it.node1] else null }
    }

    fun dependencySort(node: TNode): List<TNode> {

    }
}


