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

Non-functional annotations displayed on the canvas.

Example:
```
#X text 50 10 This is a comment;
```

## Connections

```
#X connect SRC_INDEX SRC_OUTLET DST_INDEX DST_INLET;
```

- All values are 0-based integers
- `SRC_INDEX` / `DST_INDEX` — object indices (sequential from 0, only `#X obj` and `#X msg` count)
- `SRC_OUTLET` / `DST_INLET` — outlet/inlet numbers (0-based)

Only these line types increment the index counter:
- `#X obj`
- `#X msg`
- `#X floatatom`
- `#X symbolatom`
- `#X text` (in some Pd versions)

These do NOT increment the counter:
- `#X connect`
- `#X array`
- `#X coords`

Example:
```
#X obj 50 30 osc~ 440;       // index 0
#X obj 50 80 *~ 0.5;         // index 1
#X obj 50 130 dac~;          // index 2
#X connect 0 0 1 0;          // osc~ outlet 0 -> *~ inlet 0
#X connect 1 0 2 0;          // *~ outlet 0 -> dac~ inlet 0
#X connect 1 0 2 1;          // *~ outlet 0 -> dac~ inlet 1 (stereo)
```

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
#X obj X Y declare -path /path/to/abstractions;
#X obj X Y declare -lib library_name;
```

## Line Continuation

Long lines can be split with `\` at the end (though this is rarely needed):

```
#X msg 50 30 very long message \
that continues on the next line;
```

## Complete Patch Template

```
#N canvas 0 0 WIDTH HEIGHT 12;

// Comments (use #X text for visible comments)
#X text 50 10 Patch description;

// Objects (track index for each)
#X obj X1 Y1 TYPE1 ARGS;
#X obj X2 Y2 TYPE2 ARGS;
#X obj X3 Y3 TYPE3 ARGS;

// Connections (use tracked indices)
#X connect SRC1 SRC_OUT1 DST1 DST_IN1;
#X connect SRC2 SRC_OUT2 DST2 DST_IN2;
```

## Common Pitfalls

1. **Missing semicolons** — every line must end with `;`
2. **Wrong indices** — verify object count matches connection references
3. **Signal/control mismatch** — `~` outlets cannot connect to non-`~` inlets
4. **Spaces in paths** — file paths in objects must not contain spaces
5. **$0 expansion** — `$0` in objects is replaced with a unique canvas ID at load time, useful for local send/receive names
