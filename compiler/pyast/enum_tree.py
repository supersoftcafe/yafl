"""The enum declaration tree.

An enum is a tree of declarations: the root `EnumStatement`, its `.variants`
below it, each with its own `.parameters` — the fields declared at exactly
that level. A level is named by its PATH, the variant names from the root
down to it (`()` is the root); `EnumSpec.path` is the path of a value's type.
Path names are the declarations' own names. Monomorphisation suffixes a
specialised enum's declarations and the types redirected to it alike, so a
path walks the tree of the enum its type names.

Plain functions over the tree, shared by the statement layer and the type
layer, which reads declarations through `Resolver.find_enum`.
"""
from __future__ import annotations


def node_at(root, path: tuple[str, ...]):
    """The declaration at `path` below `root`, or None if there is none."""
    node = root
    for name in path:
        node = next((v for v in node.variants if v.name == name), None)
        if node is None:
            return None
    return node


def find_variant(root, name: str):
    """(path, declaration) of the variant named `name` at any depth below
    `root` — `((), root)` when `name` is the root — or None."""
    if root.name == name:
        return (), root
    for v in root.variants:
        found = find_variant(v, name)
        if found is not None:
            path, node = found
            return (v.name,) + path, node
    return None


def leaf_names(node) -> list[str]:
    """The leaves at or below `node`. A declaration without variants is a
    leaf, unless it has no parameter list at all (an uninhabited enum)."""
    if not node.variants:
        return [node.name] if node.has_param_list else []
    return [leaf for v in node.variants for leaf in leaf_names(v)]


def visible_fields(root, path: tuple[str, ...]) -> list:
    """The (unique name, type) fields of a value typed at `path`: those
    declared at that level or a parent level. A field declared lower down
    belongs to a sub-type; a same-named field on another variant is a
    different field."""
    levels = [node_at(root, path[:depth]) for depth in range(len(path) + 1)]
    if levels[-1] is None:
        return []
    return [(let.name, let.declared_type)
            for level in levels for let in level.parameters.flatten()
            if let.declared_type is not None]
