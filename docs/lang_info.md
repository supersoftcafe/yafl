# YAFL language thoughts

# Tuple of a type is the type

If I declare a function that takes a parameter (int), which is tuple of int, and I try to call the function with a plain old int, it works. Tuple of int is int.

# You can unpack tuples

```
let a = (2, 3, 4)
let b = (1, *a, 5, 6) # Now b is (1, 2, 3, 4, 5, 6)
doSomething("Fred", *b) # And this takes it as an expanded parameter
```

# Maths is limited to int and float

The integer type is named Int. The floating type is named Float. The two are not compatible, but can be converted explicitly. The Int type has no min/max, as in, it is a big integer under the covers.

There are fixed width integer types, and there are different sized floating point types, but they are only for storage. All maths on these types is done on Int and Float, in other words, they are automatically converted up before performing maths on them.

```
# We can store Int32 etc, but maths produces an Int
let a: Int32 = 27
let b: Int16 = 100
let c: Int = a * b
let d: Int16 = toInt16(c)

# We can store Float32 and Float64, but maths produces a Float
let a: Float32 = 1.2
let b: Float64 = 12.3
let c: Float = a * b
let d: Float32 = toFloat32(c)
```

# All operators are functions that can be overloaded

Operators are just functions.

```
# Custom operator
fun `+`(a: MyCustomTYpe, b: MyCustomType): MyCustomType
    ret doSomething(a, b)

fun applyToIntAndTwo(a: Int, f: (Int,Int):Int):Int
    ret f(a, 2)

fun test(a: Int): Int
    # Refer to the operator + for Int
    ret applyToIntAndTwo(a, `+`)
```

# Functions are data

It's a functional language. Any variable that holds a lambda is equivalent to a function with the same signature. Either can be loaded, stored, passed and manipulated. You can see this in the note above on operators.

When resolving and referenced data by name, resolution searches the local scope first, object instance scope and then global scope. Since functions are data, we don't distinguish between locating a function and locating data. This means that we are looking for something that is assignment compatible with the target, which in the case of a function call is a function with some known signature.

# Traits

Traits describe the functionality of a generic type, e.g. one might describe:

```
trait Stringable<T>
    fun toString(t:T):String
```

Then for some specific type we can have:

```
impl trait Stringable<CustomType>
    fun toString(t:CustomType):String
        ret convertToString(t)
```

For people in the C# and Kotlin world, there is this idea of extensions on classes, functions that look like a class member through syntactic sugar. YAFL doesn't do that. Classes aren't such a big thing in YAFL.

Also, this looks a lot like Rust traits. Yes, it does. Inspired by, I think is the phrase.

# Templates

Whilst traits are limited to functions, templates can bring generics magic to anything. Don't forget to indent, and it's not limited to just one thing.

```
template <X> where Stringable<X>
    class Thingy(x: X)
        fun putStuffHere():X
            ret x
        fun asString():String
            ret toString(x)
```

# Error handling

Any function that returns a value might be defined to have some return value to indicate an error. We could generalise that concept and wrap it up with something, or use a tagged union with None. These are cases where the function has done it's job correctly, and correctly reported the failure to the caller.

There are situations where the failure is not correct, where the caller is not able to deal with it. These are defined as any case where the function is not able to provide a valid return value. Take for instance the integer divide operator. We could define it to return either the integer result or None, but that would complicate a lot of code. Ideally, at least due to convention, it just returns Int. However, divide by zero cannot be represented as an Int, and so we need some other failure mechanism that does not require the caller to make a decision.

Most languages call this an exception. Let's go with that, even though the underlying mechanism will be very different.



