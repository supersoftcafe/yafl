NamedStatement._find_trait_data, searches for functions in trait interfaces
Only top level class/fun/let can have generics
Only search for data, not types, in trait interfaces


Invocation of class constructor, requires all 'where' classes to have implementations.
Call of function, requires all 'where' classes to have implementations.
Lowering, replaces all calls with implementations.



- After checking 'where' clause on class/fun/let definition, create
  Resolver that searches the 'where' specified interfaces, at least
  those where we have concrete types.
- ResolvedScope.TRAIT/Resolved.trait_scope should be handled correctly

- Add compile and check for trait_parameters (where clause)
- Any expression/type that uses a generic type needs to test that the 'let [trait] Type' exists for the trait_params where clauses
- Class constructors need to have generics added, same as owning class
- new_instance operation needs generics

- New Statement+TypeDecl for the generic placeholder
- Add generics parsing to fun/let/class/interface
- Add parse for 'where' clause
- Modify assignment compatibility check to take into account generics..  exact match only



# Loops
```
fun loops(x:int): int
  # Required default value if the loop is empty.
  let a = 1 
  for i in 0 to 3
    let a = a+x
  ret a
```
is functionally equivalent to
```
fun loops(x:int): int
  let a = 1
  let a0 = a+x
  let a1 = a0+x
  let a2 = a1+x
  ret a2
```
which suggests that loops are compatible with the functional paradigm if
the inner loop type of 'a' is identical to the outer loop type, where the
value is referenced downstream.
```
fun loops(x:int): int
  let a = 1
  for i in 0 to 3
    let a = a+x
    break if a > 20
  ret a
```
A break statement should be safe as well, and in terms of recursion is
the procedural equivalent of a return statement. It still obeys the
functional paradigm, but having it inside conditions might imply that
else blocks are not required. I think that making the break statement
itself a condition helps to avoid this anti-pattern.

# Conditions
```
fun condition(x:int): int
  if x > 10:
    let r = 20
  else: # Else is required, otherwise 'r' might not be set
    let r = 10
  ret r
```
is functionally equivalent to
```
fun condition(x:int): int
  let r = x > 10 ? 20 : 10
  ret r
```
which suggests that condition blocks are compatible with the functional
paradigm if each block defines the same named values with the exact same
types, where the value is referenced downstream.

These are not mutations, but they look like mutation, and allow
the programmer to think in classical non-functional terms.

