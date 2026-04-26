
# IO TTY input

Currently the IO module tries to fill the buffer, which means that TTY input beyond what is needed
must be entered, or CTRL-D pressed before the program will respond. Ideally we need to have a read
mode that does not fill the buffer, but rather only reads exactly what is needed to fullfil the
request.

# Linear types

A linear type is a type that once initiated must be used exactly once. Each use then creates a new instance
for the next function in the chain, finally terminating on a function that does not return a new instance.

This compiler level checking ensures that some handle that represents a resource can only be used by one
thread at a time and that it will be destroyed. The IO library is waiting for this to get language safety
for closing file handles.

# One line functions

fun addTwoNumbers(a:Int, b:Int) => a + b

# Early return from BlockExpression

To support more coding styles that are not anti-functional, an early return is not just acceptable, it
is very useful.

# Replace worker nodes with tasks

Currently the task job system uses worker nodes that the caller pre-allocates. The async model of yafl
uses task objects, again that are pre-allocated. Instead of having two separate things both are tasks.

A task object then has fields to support queueing as a job, and a thread_id of the creator. A normal
dispatch will post it to the caller thread. Most code will invoke a task directly, if possible.

When adding parallel job support (future work) we'll have a dispatch that round robins the threads, but
for now the default mode of dispatch will be to put the job back on to the caller thread's queue. This
is good for cache coherency.

This means adding extra fields to task_t, and investigating any uses of the task API, to ensure that
they use the library task_init (to be done) method. Some of the new task code initialises explicitly
but that means that they assume that they know how to initialise. The first field of all task sub-classes
must be task_t, and task_init must be used on it.

# Tuple let grouping

A lowering pass groups all sequences of independent `let` bindings — those with
no data dependency between them — into a single tuple construct/destruct
statement. This is unconditional: every eligible sequence is grouped regardless
of cost. A later, separate pass will decide which grouped tuples to evaluate in
parallel based on a weighing function. The consequence is that independent `let`
bindings must not be assumed to have a defined evaluation order.

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
which suggests that loops are compatible wiaddth the functional paradigm if
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




