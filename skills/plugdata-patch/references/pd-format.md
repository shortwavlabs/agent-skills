# .pd File Format Specification

Complete reference for the Pure Data / plugdata patch file format.

## File Structure

A `.pd` file is plain text. Each statement is on its own line and ends with `;`. The file encoding is typically UTF-8 or ASCII.

### Statement Prefixes

| Prefix | Meaning |
|--------|---------|
| `#N` | New declaration (canvas, subpatch) |
| `#X` | Element on the current canvas (object, message, text, connection) |
| `#A` | Array data |

## Canvas Declaration

Every `.pd` file begins with a root canvas:

```
#N canvas X Y WIDTH HEIGHT FONTSIZE;
```

- `X`, `Y` — window position on screen (pixels, usually `0 0`)
- `WIDTH`, `HEIGHT` — canvas dimensions (pixels, e.g., `450 300`)
- `FONTSIZE` — default font size (commonly `12`)

Example:
```
#N canvas 0 0 600 400 12;
```

### Named Canvas (Subpatch)

```
#N canvas X Y WIDTH HEIGHT NAME VISIBLE;
```

- `NAME` — subpatch name (string)
- `VISIBLE` — `0` (closed) or `1` (open on load)

## Object Placement

```
#X obj X Y OBJECT_TYPE [ARG1] [ARG2] ...;
```

- `X`, `Y` — position on canvas (pixels from top-left)
- `OBJECT_TYPE` — the Pd object name (e.g., `osc~`, `*~`, `metro`)
- Arguments depend on the object type

Examples:
```
#X obj 100 50 osc~ 440;
#X obj 100 120 *~ 0.5;
#X obj 200 50 r gain;
#X obj 100 200 dac~ 1 2;
```

### Object Types

Objects fall into these categories:

- **Signal objects** (suffix `~`): process audio-rate data (44100 samples/sec)
- **Control objects**: process messages (bang, float, symbol, list)
- **GUI objects**: visual controls (sliders, buttons, knobs)
- **Abstractions**: sub-patches loaded from external `.pd` files
- **Externals**: compiled C objects or Lua scripts

## Message Box

```
#X msg X Y CONTENT;
```

Message boxes send their content when triggered (by a bang or click).

Examples:
```
#X msg 50 30 440;
#X msg 50 80 set 440;
#X msg 50 130 read audio.wav;
```

Messages can contain:
- Numbers: `440`, `-12`, `0.5`
- Symbols: `start`, `stop`
- Comma-separated messages: `440, 220`
- Variable references: `$1`, `$2` (creation arguments)
- Semicolon send: `; receiver value`

## Text / Comment

```
#X text X Y CONTENT;
```

Non-functional annotations displayed on the canvas. Comments still take an object index, so count them when numbering connections (see Connections).

Example:
```
#X text 50 10 This is a comment;
```

## Connections

```
#X connect SRC_INDEX SRC_OUTLET DST_INDEX DST_INLET;
```

- All values are 0-based integers
- `SRC_INDEX` / `DST_INDEX` — object indices: sequential from 0 on the current canvas, counting every item placed on it (comments included, see below)
- `SRC_OUTLET` / `DST_INLET` — outlet/inlet numbers (0-based)

Every item placed on the canvas takes the next index:
- `#X obj` (including GUI objects such as `tgl`, `hsl`, `bng`, `nbx`)
- `#X msg`
- `#X text` (comments: always counted, in every Pd version and in plugdata)
- `#X floatatom` / `#X symbolatom` / `#X listbox`
- `#X restore` (a subpatch or graph placed on the parent; its contents are numbered separately, starting from 0)

These do NOT increment the counter:
- `#X connect`
- `#X coords`
- `#X array` / `#A` (they belong to the enclosing graph, which is counted by its `#X restore`)
- `#X declare`
- `#N canvas` (opens a subpatch; the subpatch takes its parent index at `#X restore`)

Example:
```
#X text 50 10 stereo sine;   // index 0 (comment, still counted)
#X obj 50 30 osc~ 440;       // index 1
#X obj 50 80 *~ 0.5;         // index 2
#X obj 50 130 dac~;          // index 3
#X connect 1 0 2 0;          // osc~ outlet 0 -> *~ inlet 0
#X connect 2 0 3 0;          // *~ outlet 0 -> dac~ inlet 0
#X connect 2 0 3 1;          // *~ outlet 0 -> dac~ inlet 1 (stereo)
```

If you forget that comments count, every connection after the first comment shifts. Pd then reports `name.pd A B C D (text->...) connection failed`, or `audio signal outlet connected to nonsignal inlet (ignored)` when a signal wire lands on the wrong object.

## Arrays

### Declaration

```
#X array ARRAY_NAME SIZE float SAVE_FLAG;
```

- `ARRAY_NAME` — identifier (no spaces)
- `SIZE` — number of floating-point samples
- `float` — always `float` (the data type)
- `SAVE_FLAG` — `0` (don't save contents) or `1` (save with patch)

### Data

```
#A 0 V0 V1 V2 V3 ...;
```

- `0` — starting index
- Values are space-separated floats
- Multiple `#A` lines can continue the array

Example:
```
#X array waveform 256 float 0;
#A 0 0 0.098 0.195 0.290 0.383 0.471 0.556 0.634 0.707 0.773 0.831 0.882 0.924 0.957 0.981 0.995 1.000;
```

## Subpatches

Subpatches are inline abstractions — nested canvases within the parent patch.

### Structure

```
#N canvas 0 0 WIDTH HEIGHT NAME 0;
  ... (objects and connections inside the subpatch) ...
#X restore X Y pd NAME;
```

The `#X restore` line places the subpatch as an object on the parent canvas and receives an object index.

Example:
```
#N canvas 0 0 300 200 myProcessor 0;
#X obj 50 30 inlet~;
#X obj 50 100 lop~ 1000;
#X obj 50 170 outlet~;
#X connect 0 0 1 0;
#X connect 1 0 2 0;
#X restore 100 200 pd myProcessor;
```

### Inlets and Outlets in Subpatches

- `inlet` / `inlet~` — control/signal input from parent
- `outlet` / `outlet~` — control/signal output to parent
- Multiple inlets/outlets: first declared = index 0, second = index 1, etc.

## GUI Objects

GUI objects are declared as `#X obj` with special type names:

### Core Pd GUI

```
#X obj X Y bng SIZE HOLD INTERRUPT INIT SEND RECEIVE LABEL LABEL_POS LABEL_FONT COLOR_BG COLOR_FG LABEL_SIZE;
#X obj X Y tgl SIZE INIT INIT_VALUE SEND RECEIVE LABEL LABEL_POS LABEL_FONT COLOR_BG COLOR_FG LABEL_SIZE;
#X obj X Y nbx WIDTH HEIGHT MIN MAX LOG INIT SEND RECEIVE LABEL LABEL_POS LABEL_FONT COLOR_BG COLOR_FG LABEL_SIZE;
#X obj X Y hsl WIDTH HEIGHT MIN MAX LOG INIT SEND RECEIVE LABEL LABEL_POS LABEL_FONT COLOR_BG COLOR_FG LABEL_SIZE;
#X obj X Y vsl WIDTH HEIGHT MIN MAX LOG INIT SEND RECEIVE LABEL LABEL_POS LABEL_FONT COLOR_BG COLOR_FG LABEL_SIZE;
```

### ELSE GUI (plugdata)

These are simplified — just use as regular objects with creation arguments:

```
#X obj X Y knob MIN MAX LOG INIT SEND RECEIVE LABEL;
#X obj X Y scope~;
#X obj X Y keyboard;
#X obj X Y function;
#X obj X Y meter~;
```

## Floatatom / Symbolatom

```
#X floatatom X Y WIDTH LOWER UPPER LABEL_POS LABEL RECEIVE SEND;
#X symbolatom X Y WIDTH LOWER UPPER LABEL_POS LABEL RECEIVE SEND;
```

## Graph-On-Parent (GOP)

When a subpatch has GOP enabled, its visual content is shown on the parent canvas:

```
#X coords X_FROM Y_TO X_TO Y_FROM WIDTH HEIGHT GOP_FLAG;
```

## Send/Receive (Wireless)

Objects can communicate without cables using send/receive:

```
#X obj X Y send NAME;      // or: s NAME
#X obj X Y receive NAME;   // or: r NAME
#X obj X Y throw~ NAME;
#X obj X Y catch~ NAME;
```

Signal send/receive (`send~`/`receive~`, `throw~`/`catch~`) work the same way but for audio signals.

## Declaration (Search Paths)

```
#N canvas 0 0 600 400 12;
#X declare -path /path/to/abstractions -lib library_name;
#X obj X Y declare -path /path/to/abstractions -lib library_name;
```

Pd saves a declaration as two lines, and a generated patch needs both:
- `#X declare ...;` directly after the top `#N canvas` line. This line loads the libraries and adds the paths when the patch is opened, before any objects are created. It takes no object index.
- `#X obj X Y declare ...;` is the visible `[declare]` box. It takes an index like any other object, but **on its own it loads nothing**. Objects from the library will fail with "couldn't create".

plugdata and Gem: Gem is compiled into plugdata, but its classes are registered only as `Gem/<name>`. Prefer the prefixed names (`[Gem/gemwin]`, `[Gem/gemhead]`, `[Gem/pix_film]`, `[Gem/rectangle]`, ...), which need no declaration. `#X declare -lib Gem;` also works, but it makes the plain Gem names global for the rest of the session and replaces any ELSE object with the same name (for example ELSE's `[circle]` GUI).

## Line Continuation

Long lines can be split with `\` at the end (though this is rarely needed):

```
#X msg 50 30 very long message \
that continues on the next line;
```

## Complete Patch Template

```
#N canvas 0 0 WIDTH HEIGHT 12;

// Comments (use #X text for visible comments) take an index too: this one is 0
#X text 50 10 Patch description;

// Objects (track index for each; numbering continues after the comment: 1, 2, 3)
#X obj X1 Y1 TYPE1 ARGS;
#X obj X2 Y2 TYPE2 ARGS;
#X obj X3 Y3 TYPE3 ARGS;

// Connections (use tracked indices)
#X connect SRC1 SRC_OUT1 DST1 DST_IN1;
#X connect SRC2 SRC_OUT2 DST2 DST_IN2;
```

## Common Pitfalls

1. **Missing semicolons** — every line must end with `;`
2. **Wrong indices** — verify object count matches connection references. Comments (`#X text`) and subpatch `#X restore` lines count. The giveaway is `(text->...) connection failed` in the console.
3. **Signal/control mismatch** — `~` outlets cannot connect to non-`~` inlets
4. **Spaces in paths** — file paths in objects must not contain spaces
5. **$0 expansion** — `$0` in objects is replaced with a unique canvas ID at load time, useful for local send/receive names
