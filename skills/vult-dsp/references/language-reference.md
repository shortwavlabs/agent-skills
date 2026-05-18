# Vult Language Reference

Complete syntax reference for the Vult language. Derived from the official Vult wiki.

## Table of Contents

- [Comments](#comments)
- [Types](#types)
- [Operators](#operators)
- [Expressions](#expressions)
- [Statements](#statements)
- [Functions](#functions)
- [Memory Variables](#memory-variables)
- [Function Context and Naming](#function-context-and-naming)
- [Shared Context with `and`](#shared-context-with-and)
- [External Functions](#external-functions)
- [Tags](#tags)
- [Builtin Functions](#builtin-functions)
- [Arrays](#arrays)

## Comments

```
// Line comment

/* Block comment */

/* /* Nested block comments are supported */ */
```

## Types

Vult is statically typed with type inference. The primitive types are:

| Type | Description | Example |
|------|-------------|---------|
| `int` | Integer | `0`, `1`, `3942` |
| `real` | Floating or fixed-point (determined at compile time) | `1.0`, `3.1416` |
| `bool` | Boolean | `true`, `false` |
| `unit` | Empty/void value | `()` |

Numbers without a decimal point are `int`. Numbers with a decimal point are `real`. These cannot be mixed without explicit casting:

```
val x : int = int(1.7);    // real -> int (truncates)
val y : real = real(1);     // int -> real
```

Type annotations use `:` after variable or parameter names:

```
val x : real = 1.0;
val y : int = 0;
fun add(a : int, b : int) : int { return a + b; }
```

### Fixed-point specifics

When compiling with `-real fixed`, all `real` values use q16.16 fixed-point format:
- Range: approximately -32768.0 to 32767.0
- Precision: smallest representable value is ~0.0000153
- The `fix16` type can be used explicitly for mixed float/fixed code
- Literals with `x` suffix are fixed-point: `12.5x`

### Default values

All variables initialize to zero if no value is provided:

```
val a : int;            // a = 0
val b : real;           // b = 0.0
val c : array(int,3);   // c = [0, 0, 0]
val d : array(real,3);  // d = [0.0, 0.0, 0.0]
```

## Operators

All operators require both operands to be the same type.

### Arithmetic (`int` and `real`)

```
+    Addition
-    Subtraction
*    Multiplication
/    Division
%    Modulo
-    Unary minus (e.g., -1.0)
```

### Logic (`bool`)

```
&&    And
||    Or
not(x)   Not (function, not operator)
```

### Relational (`int` and `real`)

```
==    Equal
<>    Not equal
<     Less than
>     Greater than
<=    Less than or equal
>=    Greater than or equal
```

## Expressions

### If-expressions

If-expressions always require an `else` branch:

```
val x = if y > 0.0 then 3.0 else 4.0;
```

### Tuples

Multiple values can be grouped and destructured:

```
val x, y, z = 1, 2, 3;
val (a, b, c) : (int, int, int) = 1, 2, 3;
val point : (real, real, real) = 0.0, 1.0, 2.0;
```

### Function calls with context

See [Function Context and Naming](#function-context-and-naming).

## Statements

### Variable declarations

```
val x = 0;           // type inferred as int
val y : real = 1.0;  // type specified
```

### Assignments

```
x = 1;
a, b, c = 0, 1, 2;

// Discard return values with _
val x, _ = foo();    // ignore second return value
_ = bar();           // ignore return of unit-returning function
```

### If-statements

If-statements may omit the `else` branch. Single-statement bodies don't need braces:

```
if (x > 0)
    return 0;

if (y > 0) {
    y = 0;
    x = 1;
} else {
    y = 1;
    x = 2;
}
```

### While loops

Vult has only `while` loops. Use a counter variable for `for`-loop behavior:

```
fun sum() {
    val i = 0;
    val acc = 0;
    while (i < 10) {
        acc = acc + i;
        i = i + 1;
    }
    return acc;
}
```

## Functions

```
fun add(a, b) { return a + b; }
fun typed(a : int, b : int) : int { return a + b; }
fun nothing() : unit { }
```

Functions can return multiple values:

```
fun swap(a, b) { return b, a; }
val x, y = swap(1, 2);
```

## Memory Variables

`mem` variables persist their values across function calls. They are always initialized to zero. This is the foundation of stateful DSP in Vult:

```
fun counter() {
    mem count = count + 1;   // self-referencing: reads previous value, stores new
    return count;
}
```

`mem` variables can also be declared with just a type (initialized to default):

```
mem x : int;
mem y : real;
mem z : array(real, 3);
```

The key difference from `val`:
- `val` — local variable, reset every call
- `mem` — persistent state, survives across calls, lives in the function's context

## Function Context and Naming

Every call to an active function (one with `mem` variables) creates an independent context:

```
fun counter() {
    mem count = count + 1;
    return count;
}

fun test() {
    val a = counter();   // context 1: a = 1, 2, 3, ...
    val b = counter();   // context 2: b = 1, 2, 3, ...
}
```

**Named contexts** allow you to control context reuse:

```
fun test() {
    val a = first:counter();   // named context "first"
    val b = second:counter();  // different named context "second"
    val c = first:counter();   // reuses context "first" — c = 2
}
```

Named contexts are essential for:
- **Stereo processing**: `left:filter(in_l)` and `right:filter(in_r)`
- **Oversampling**: call the same context multiple times per sample
- **Polyphony**: named instances per voice

## Shared Context with `and`

Functions linked with `and` share the same memory context. This enables patterns where multiple functions access the same state:

```
fun counter() {
    mem x = x + 1;
    return x;
}
and reset() {
    x = 0;   // accesses same 'x' from counter()
}

fun test() {
    val a = c:counter();   // a = 1
    val b = c:counter();   // b = 2
    _ = c:reset();         // resets x to 0
    val d = c:counter();   // d = 1
}
```

`mem` variables can be declared in any function in the `and` chain — they are all shared:

```
fun foo() {
    mem x : int;    // declared in foo
    mem y : real;   // declared in foo
}
and bar() {
    mem z : array(real, 3);  // declared in bar
    // x, y, z all accessible from both foo() and bar()
}
```

## External Functions

External functions are replaced by a specified C/C++ function during code generation:

```
external foo(x : int) : int "actual_foo";
```

A Vult call `foo(0)` becomes `actual_foo(0)` in the generated C/C++.

This is useful for platform-specific I/O (Arduino `digitalRead`, `analogWrite`, etc.).

## Tags

Tags modify function behavior.

### `@[init]` — Custom initialization

By default `mem` variables start at zero. Use `@[init]` to set different initial values:

```
fun counter() {
    mem count = count + 1;
    return count;
}
and start() @[init] {
    count = 10;   // counter starts at 10 instead of 0
}
```

### `@[table(size, min, max)]` — Lookup tables

Replaces a function with an interpolated lookup table. The function must take one `real` and return one `real`:

```
fun sine_wave(x) @[table(size=128, min=0.0, max=1.0)] {
    return sin(2.0 * 3.1415 * x);
}
```

Tables are especially valuable for expensive functions when targeting fixed-point hardware, replacing calls like `exp()` with simple additions and multiplications.

### `@[wave(channels, file)]` — WAV file embedding

Embeds a WAV file as an array accessible from Vult code:

```
external mywave(channel : int, index : int) : real @[wave(channels=1, file="wave.wav")];
```

Usage:
- `mywave(channel, sample_index)` — circular access (wraps around)
- `mywave_samples()` — returns the number of samples in the embedded file

Supported formats: PCM 16-bit or 24-bit WAV.

## Builtin Functions

### Array operations

```
get(array, index)      // array[index]
set(array, index, val) // array[index] = val
size(array)            // array length
```

### Math (for `real` types)

```
abs(x)      // absolute value
exp(x)      // exponential
sin(x)      // sine
cos(x)      // cosine
tan(x)      // tangent
tanh(x)     // hyperbolic tangent
sqrt(x)     // square root
floor(x)    // floor
```

### Random

```
random()    // real in [0.0, 1.0)
irandom()   // int in [0, 2^32), use irandom() % N for range
```

### Debug

```
log(value)  // prints value with newline (int, real, bool, or string)
```

### Constants

```
eps()       // smallest representable fixed-point value
pi()        // π ≈ 3.14159265
```

## Arrays

Array types are `array(type, size)`:

```
val x = [1, 2, 4];                          // type inferred: array(int, 3)
val y : array(real, 3) = [1.0, 2.0, 4.0];  // explicit type

// Undeclared-size arrays
val z[3];       // size is 3, type not yet known
z[0] = 1;       // now type is known: array(int, 3)
```

Access and modification:

```
val element = get(arr, 0);     // read
_ = set(arr, 0, new_value);   // write
val len = size(arr);           // length
```

Arrays as `mem` variables persist across function calls:

```
fun delay_line(input) {
    mem buffer : array(real, 44100);
    mem write_pos;
    val output = get(buffer, write_pos);
    _ = set(buffer, write_pos, input);
    write_pos = (write_pos + 1) % size(buffer);
    return output;
}
```
