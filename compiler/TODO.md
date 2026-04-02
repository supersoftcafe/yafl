# Change async model to task based

Bit 0 of any pointer is reserved to indicate that it's a task pointer. Compressed 
string and integer pointers must work around that. Any return value that is a pointer
or a struct containting a pointer somewhere will use this encoding.

One of the never used NaN values is used as a sentinal for float32 and 64 but the 
function must return two, so that the second can be coerced into a pointer, but without
causing the hot path to degrade to integer or ram ops for function calls that are
known to be synchronous.

Tagged unions with a spare tag value can be simply hijacked to have a new tag for the
task pointer.

Finally if all else fails a simple bool flag is tagged onto the end as a sentinal and
wrapped into a union with the task pointer.

The task object itself always has the same mutex and callback machinery at the start
followed by space for the returned value.

The synchronous hot path should fall through quickly.

Integer and string type encoding is impacted by this. To support this and other 
disambiguations the following encoding is used:
- bit zero set means it is a task pointer
- bit one set means it is a compressed integer of 30 or 62 bits
- bit two set means it is a string of 3 or 7 bytes, bits 3-5 encode length
- 0 is None
- all others are YAFL object pointers

Example launchpad, or fast path synchronous function, example:
```
struct thingyresult
{
  object_t* a;
  int32_t b;
};
void get_thing$async(frame_t* frametask, object* resulttask)
{
  switch (frametask->callid)
  {
    case 1:
      // do something with result
      break;

      // buld state machine here
  }
}
struct thingyresult get_thing(object_t* this, int32_t value)
{
  int32_t call_id;
  object_t* task;

  object_t* result = something(null, value);
  if (unlikely(is_task(result)))
  {
    task = extract_task(result);
    call_id = 1;
    goto asynccommon;
  }
  // carry on with hot sync path
  return {result->field, value};

asynccommon;
  frame_t* frametask = allocateheapframe();
  frametask->callid = call_id;

  // save variables to heap frame

  // Either saves the callback handler or directly calls it due
  // to task already complete, which can happen.
  save_callback_handler(task, (fun_t){.f=get_thing$async, .o=frametask});
  return {.a = wrap_task(frametask) };
}
```



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


# Early returns

I take it all back about having a special syntax for breaks. Early
returns break that anyway, so we might as well have normal breaks.
Code analysis will have to check for early return and for break if
it causes any issues.


# String inspection

Strings are currently write-only: concatenation and printing are supported, but
there is no way to inspect a string's contents. Add to stdlib/string.yafl:

- length(s: String): Int            — number of Unicode code points
- char_at(s: String, i: Int): Int   — code point at index i
- =(left: String, right: String): Bool — structural equality

These require corresponding additions to libyafl (string_length, string_char_at,
string_eq operations), to be implemented in parallel.

char_at returns Int, keeping Char as a one-way int-to-string conversion and
avoiding the need for a separate Char type.


# Stdin reading

System::Console currently supports output only. Add:

fun read_line(): String|None

Returns the next line from stdin without the trailing newline, or None at EOF.
Requires a corresponding libyafl addition.


# List<T>

A generic linked-list type, to be added to the stdlib once the for-loop
feature is in place (list traversal needs runtime-bound loops).

class List<T>(head: T, tail: List<T>|None)

Stdlib functions (in System namespace, all generic over T):
```
- cons(head: T, tail: List<T>|None): List<T>
- map<T, U>(list: List<T>|None, f: (:T):U): List<U>|None
- filter<T>(list: List<T>|None, pred: (:T):Bool): List<T>|None
- fold<T, A>(list: List<T>|None, acc: A, f: (:A,:T):A): A
- length<T>(list: List<T>|None): Int
- append<T>(left: List<T>|None, right: List<T>|None): List<T>|None
- reverse<T>(list: List<T>|None): List<T>|None
```

# JSON parser and pretty-printer

A non-trivial end-to-end program to validate the language is expressive enough
for serious work. Read a JSON document from stdin, parse it into a typed YAFL
value tree, and emit it back to stdout as indented, formatted JSON.

The value tree uses a recursive union type:

```
class JsonArray(head: JsonValue, tail: JsonArray|None)
class JsonEntry(key: String, value: JsonValue, tail: JsonEntry|None)

typealias JsonValue: JsonNull | JsonBool | JsonNumber | JsonString | JsonArray | JsonEntry
```

The lexer walks the input string character by character using char_at and
length. The parser is a recursive-descent over the token stream, with
parse_value, parse_array, and parse_object calling each other mutually.
The pretty-printer traverses the value tree with pattern matching and
builds the output string using indentation-aware recursion.

Prerequisites: Conditions, Loops, String inspection, Stdin reading, List<T>.


# Tuple let grouping

A lowering pass groups all sequences of independent `let` bindings — those with
no data dependency between them — into a single tuple construct/destruct
statement. This is unconditional: every eligible sequence is grouped regardless
of cost. A later, separate pass will decide which grouped tuples to evaluate in
parallel based on a weighing function. The consequence is that independent `let`
bindings must not be assumed to have a defined evaluation order.


# IO<T> and sequencing via ?>

IO operations return an IO<T> value that must be captured and threaded to the
next IO call. Because each step in the chain depends on the previous step's
output, the tuple-let dependency analysis will naturally keep them ordered — no
special compiler knowledge of IO<T> is required. Any user-defined sequential
type follows the same pattern. The CPS backend will later rewrite IO<T> chains
into non-blocking async operations with no change to source.


# Linear types (far future)

Any class intended as a sequential wrapper (like IO<T>) needs a way to declare
that its values are single-use, preventing a sequential chain from being forked
into two branches that each believe they hold the current state token.

Expressed as a class attribute:

```
class [linear] IO<T>(value: T)
```

The semantics are strictly linear: a value must be consumed exactly once on
every code path. This forces explicit handling of every linear value — for
resource types like file handles, the discard function IS the close call, and
the compiler requiring it on all paths is precisely the guarantee that prevents
resource leaks. Silently dropping a linear value is a compile error.

Enforcement is a compile-time use-count analysis pass. The main cases to handle:

- Conditionals: both branches of an if/else must each consume the linear value
  exactly once. This is naturally satisfied when IO is threaded via ?>.
- Closures: a lambda that captures a linear value may only be invoked once.
  This interacts with the lambda-lowering pass and needs careful tracking.
- Generics: passing a linear value into a generic function requires that
  function to declare it consumes rather than copies the argument. A new
  where-clause constraint will likely be needed.

The tuple-let grouping pass requires no special handling: any two bindings that
both reference a linear value are already dependent by definition, so the
existing dependency analysis will never group them. Linearity and grouping are
naturally consistent.

In practice, ?> already enforces the right discipline — as long as IO is
threaded through ?>, the chain is sound. Linear types close the gap by making
that a compiler guarantee rather than a convention.


# [final] classes

A class marked [final] cannot be subclassed, and nothing may inherit from it.
The compiler enforces this as a static error. Because no polymorphic dispatch
can ever occur through a [final] type, the vtable mechanism is bypassed entirely
and all method calls are emitted as direct C calls.

[final] is useful as a design constraint independent of any C interop — it
communicates intent and enables a straightforward optimisation. It is also a
prerequisite for the [foreign] interop mechanism below.


# [foreign] C interop

A class marked [foreign] declares an opaque type whose implementation lives in
an external C library. The compiler suppresses struct typedef and vtable
emission for the type entirely. A [foreign] class has no constructor parameters
— instances cannot be constructed directly in YAFL. Instead, standalone
[foreign] functions return instances of the type:

```
class [foreign, final] FileIO
    fun [foreign("libyafl_file_read_line")] read_line(): String|None
    fun [foreign("libyafl_file_write")]     write(s: String): None
    fun [foreign("libyafl_file_close")]     close(): None

fun [foreign("libyafl_file_open")]   open(path: String): FileIO
fun [foreign("libyafl_file_create")] create(path: String): FileIO
```

[foreign("symbol")] on a function suppresses the body and maps the declaration
to that exact C symbol. Call sites are otherwise unchanged.

This applies equally to non-member functions with no associated foreign class —
any standalone function can be declared as a foreign symbol:

```
fun [foreign("libyafl_get_env")] get_env(name: String): String|None
```

[foreign] classes must also be [final]: without that guarantee the compiler
would need vtable entries for them, which cannot be generated for a type whose
implementation is opaque.
