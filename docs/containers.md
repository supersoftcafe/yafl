# Container design — ordered vs unordered

## The rule

**No iteration on unordered containers.**

"Iteration" means any operation that lets a caller observe element ORDER: a
chain/cursor walk, or a conversion to an ordered container that does not name
an ordering. If a container has no defined order, exposing one is a lie — the
order is an artefact of the implementation (hash-tree shape, insertion
history), and callers come to depend on it.

Permitted on an unordered container:

* bulk transforms whose result is also unordered — `map`, `filter`
* order-independent questions — `isEmpty`, `size`, `contains`, `any`, `all`,
  `singleOrNone`, `isMoreThanOne`
* an EXPLICIT ordering — `sort`, which is the only way out to a `List`

## The four containers

| type | ordered? | built by | for |
|---|---|---|---|
| `Dict<K,V>` | no | `put` | keyed lookup |
| `Set<T>` | no | `add` | membership; a `Dict<T,()>` behind a wrapper |
| `Bag<T>` | no | `add` | accumulation when order does not matter |
| `List<T>` | YES | `ListBuilder` / `prepend` | sequences whose order is meaningful |

Pick the SIMPLEST container that does the job. A loop that reads its own
accumulator wants a `Set`. Plain accumulation wants a `Bag`, or a
`ListBuilder` when the result must be an ordered `List`. `ListBuilder` is an
optimisation, not the default to reach for.

### Bag

The original banker's pair (`front`, `rear`) with the reversal deleted. The
reversal only ever existed to restore ORDER when draining the rear; a `Bag`
has no order to restore, so both chains are walked as they lie. `add` is O(1),
and keeping two chains leaves room for a cheap `merge` later.

### List

Ordered, so a cursor walk (`chain`) is legitimate — that is what "ordered"
buys. Built ONLY front-normal, so there is no rear and nothing to reverse:

* `ListBuilder` — in-order construction, O(1) push
* `prepend` — the cons; O(1), yields reverse-of-insertion order

`append` is REMOVED. It is the sole reason the rear chain existed, and the
rear is the sole reason `_chainReverse` existed.

`reverse` is REMOVED. On a front-normal list it can only be implemented by
building a reversed copy — `_chainReverse` under a new name, which is exactly
what must not reappear. Order changes come from `sort`.

## Removed, and what replaces it

| removed | why | replacement |
|---|---|---|
| `_chainReverse` | the whole point | nothing; no rear to drain |
| `List.append` | requires the rear | `ListBuilder.push`, or `Bag.add` |
| `List.reverse` | a disguised chain reversal | `sort` with the ordering you mean |
| `Dict.keys(): List<K>` | leaks hash-tree order | `keys(): Set<K>` (keys are unique) |
| `Dict.values(): List<V>` | leaks hash-tree order | `values(): Bag<V>` (values may repeat) |

## Added

On `Bag` and `Set` (and `List` where meaningful):

* `isEmpty`, `size`
* `singleOrNone` — the element of a one-element container, else `None`
* `isMoreThanOne` — more than one element
* `map`, `filter`, `any`, `all`
* `sort` — `Bag`/`Set`/`List` -> `List`, natural order via `BasicCompare`
* `sortBy` — the same taking a comparison function, for types with no natural
  order

`merge`/`concat` of two containers is done the slow way for now: there is no
good answer yet and it is deliberately future work.

## Why this kills `_chainReverse`

Every one of its 13 call sites drains a rear chain. The rear exists only to
make `append` O(1) on an ordered list. Remove `append`, and:

* `List` is front-normal by construction — `chain()` is free
* `sort` no longer reverses the rear before seeding runs
* `Bag` keeps two chains but never needs order, so never reverses

No hidden replacement: there is no function anywhere whose job is "produce the
elements of X in the opposite order".
