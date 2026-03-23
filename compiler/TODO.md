
# Simple classes
Any class that is below a particular complexity threshold (based on some heuristic
of its instance values) and does not inherit from any other class, or have
sub-classes, is equivalent to a C# struct with helper functions. We can add lowering
to make it so, converting its definition to a tuple and moving the instance functions
out into a namespace with call sites re-written to pass nominal 'this' as a first
parameter instead.


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


# Early returns

I take it all back about having a special syntax for breaks. Early
returns break that anyway, so we might as well have normal breaks.
Code analysis will have to check for early return and for break if
it causes any issues.

