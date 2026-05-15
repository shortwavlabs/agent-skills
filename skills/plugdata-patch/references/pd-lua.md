# pd-lua Reference

pd-lua extends Pure Data / plugdata with the ability to write custom objects in Lua. It enables everything from simple utility objects to full synthesizers and sequencers.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Object Lifecycle](#object-lifecycle)
3. [Inlets and Outlets](#inlets-and-outlets)
4. [Message Handling](#message-handling)
5. [Output](#output)
6. [Signal Processing (DSP)](#signal-processing)
7. [Arrays/Tables](#arraystables)
8. [Clocks (Timers)](#clocks)
9. [Receivers (Wireless)](#receivers)
10. [Custom GUI](#custom-gui)
11. [Utilities](#utilities)
12. [Limitations](#limitations)

## Getting Started

### File Convention

Object name `foo` must be in a file named `foo.pd_lua`. Place the file in the patch directory or on Pd's search path.

### Minimal Object

```lua
local foo = pd.Class:new():register("foo")

function foo:initialize(sel, atoms)
    self.inlets = 1
    self.outlets = 1
    return true
end
```

### Modern Shorthand (v0.12.14+)

```lua
local foo = pd.class("foo")
```

## Object Lifecycle

### `initialize(sel, atoms)` — Required

Called when the object is created. Must return `true` or creation fails.

- `sel` — selector string (usually the object name)
- `atoms` — Lua table of creation arguments (can be numbers or strings)

```lua
function foo:initialize(sel, atoms)
    self.inlets = 1
    self.outlets = 1
    self.default = type(atoms[1]) == "number" and atoms[1] or 0
    return true
end
```

### `postinitialize()` — Optional

Runs after creation, before message processing. Good for deferred initialization.

### `finalize()` — Optional

Cleanup when object is destroyed. Release resources here.

## Inlets and Outlets

Set in `initialize()`. Cannot be changed after creation.

### Control-Only

```lua
self.inlets = 2       -- 2 control inlets
self.outlets = 1      -- 1 control outlet
```

### Mixed Signal and Control

```lua
self.inlets = {SIGNAL, SIGNAL, DATA}   -- 2 signal + 1 control inlet
self.outlets = {SIGNAL}                 -- 1 signal outlet
```

- `SIGNAL` — audio-rate inlet/outlet
- `DATA` — control-rate inlet/outlet (same as setting integer count)

Convention: leftmost inlet is "hot" (triggers computation), others are "cold" (set values).

## Message Handling

Methods are tried from most specific to most general:

### Specific Type + Inlet

```lua
function foo:in_1_bang()         -- bang on inlet 1
function foo:in_1_float(x)      -- float on inlet 1
function foo:in_1_symbol(x)     -- symbol on inlet 1
function foo:in_1_list(x)       -- list on inlet 1 (table arg)
function foo:in_1_anything(x)   -- any message on inlet 1
function foo:in_1_custom(x)     -- custom selector "custom" on inlet 1
```

### Any-Inlet Handlers

```lua
function foo:in_n_custom(n, x)  -- "custom" selector on any inlet
function foo:in_1(sel, atoms)   -- catch-all for inlet 1
function foo:in_n(n, sel, atoms) -- catch-all for any inlet
```

### Right-to-Left Convention

Output should go right-to-left (decreasing outlet numbers) to match Pd's execution model:

```lua
function foo:in_1_bang()
    self:outlet(2, "float", {right_value})   -- right outlet first
    self:outlet(1, "float", {left_value})    -- left outlet second
end
```

## Output

```lua
self:outlet(OUTLET_NUM, SELECTOR, ATOMS_TABLE)
```

The `ATOMS_TABLE` must always be a Lua table (curly braces), even for single values:

```lua
self:outlet(1, "bang", {})                    -- bang
self:outlet(1, "float", {42})                 -- single float
self:outlet(1, "symbol", {"hello"})           -- single symbol
self:outlet(1, "list", {1, 2, 3})            -- list
self:outlet(1, "custom", {"arg1", 2, 3})     -- custom selector with args
```

## Signal Processing

### Inlet/Outlet Declaration

```lua
function mydsp:initialize(sel, atoms)
    self.inlets = {SIGNAL, SIGNAL}  -- 2 audio inputs
    self.outlets = {SIGNAL}         -- 1 audio output
    return true
end
```

### DSP Callback (Optional)

```lua
function mydsp:dsp(samplerate, blocksize, nchannels)
    self.sr = samplerate
    self.blocksize = blocksize
    -- nchannels is a table of channel counts per inlet (v0.12.20+)
end
```

### Perform Method (Required)

```lua
function mydsp:perform(in1, in2)
    -- Each inN is a Lua table of samples (1-based, length = blocksize)
    -- Modify in-place (more efficient) or create new table
    local out = {}
    for i = 1, #in1 do
        out[i] = (in1[i] + in2[i]) * 0.5  -- mix to mono
    end
    return out  -- return one table per signal outlet
end
```

### Performance Note

Lua DSP is interpreted and significantly slower than C or Faust. Use pd-lua for:
- Control logic and routing
- Quick prototyping
- Moderate DSP (filters, simple effects)
- Algorithmic composition

Use C externals or Faust for performance-critical DSP.

## Arrays/Tables

```lua
-- Access an existing Pd array (re-sync each time — arrays may be recreated)
local t = pd.Table:new():sync("arrayname")  -- or: pd.table("arrayname")
if t == nil then
    pd.post("Array not found")
    return
end

t:length()        -- number of elements
t:get(i)          -- get value at index (0-based: 0 to length-1)
t:set(i, value)   -- set value at index (0-based)
t:redraw()        -- refresh graphical display
```

Note: Pd arrays use **0-based** indexing, unlike Lua's usual 1-based indexing.

## Clocks

Clocks fire a callback after a delay. Useful for scheduling, LFOs, and timed events.

```lua
-- In initialize:
self.clock = pd.Clock:new():register(self, "tick")  -- or: pd.clock(self, "tick")

-- Methods:
self.clock:delay(ms)       -- fire after ms milliseconds
self.clock:set(systime)    -- fire at absolute time
self.clock:unset()         -- cancel pending
self.clock:destruct()      -- destroy (optional since v0.12.12)

-- Time utilities:
pd.systime()               -- current time in Pd time units
pd.TIMEUNITPERMSEC         -- conversion constant
pd.timesince(systime)      -- elapsed ms since given systime

-- Callback:
function myobj:tick()
    -- do something
    self.clock:delay(1000)  -- reschedule
end
```

## Receivers

Wireless message send/receive from Lua.

### Sending

```lua
pd.send("receiver_name", "float", {42})
pd.send("receiver_name", "bang", {})
pd.send("receiver_name", "symbol", {"hello"})
```

### Receiving

```lua
-- In initialize:
self.recv = pd.Receive:new():register(self, "sym", "receive")
-- or: self.recv = pd.receive(self, "sym", "receive")

-- Callback:
function myobj:receive(sel, atoms)
    -- handle message
end

-- Cleanup:
self.recv:destruct()
```

## Custom GUI

Objects can draw custom graphics using a paint callback.

### Setup

```lua
function mygui:initialize(sel, atoms)
    self.inlets = 1
    self.outlets = 1
    self:set_size(80, 80)  -- width, height in pixels
    return true
end
```

### Drawing

```lua
function mygui:paint(g)
    local w, h = self:get_size()

    -- Colors
    g:set_color(0)                    -- predefined: 0=bg, 1=fg
    g:set_color(r, g, b)              -- RGB, each 0-255
    g:set_color(r, g, b, a)           -- with alpha (0.0-1.0)

    -- Shapes
    g:fill_all()
    g:fill_rect(x, y, w, h)
    g:stroke_rect(x, y, w, h, line_width)
    g:fill_ellipse(x, y, w, h)
    g:stroke_ellipse(x, y, w, h, line_width)
    g:draw_line(x1, y1, x2, y2, line_width)
end
```

### Mouse Interaction

```lua
function mygui:mouse_down(x, y)
    self.dragging = true
    self:repaint()
end

function mygui:mouse_up(x, y)
    self.dragging = false
    self:repaint()
end

function mygui:mouse_move(x, y) end
function mygui:mouse_drag(x, y)
    -- update state based on position
    self:repaint()
end
```

### Trigger Repaint

```lua
self:repaint()
```

Alpha transparency works in plugdata and Purr Data; ignored in vanilla Pd.

## Utilities

### Logging

```lua
pd.post("message")           -- log to Pd console
self:error("error message")  -- log error (red, traceable via Find Last Error)
```

### Dollar Expansion

```lua
self:canvas_realizedollar("$0-blah")  -- expand $0 to canvas ID
self:set_args(atoms)                   -- update creation arguments
self:get_args()                        -- get current creation arguments
```

## Complete Example: Simple Sequencer

```lua
local stepseq = pd.Class:new():register("stepseq")

function stepseq:initialize(sel, atoms)
    self.inlets = 1       -- bang triggers next step
    self.outlets = 1      -- outputs note value
    self.step = 1
    self.pattern = {60, 64, 67, 72, 67, 64, 60, 55}
    return true
end

function stepseq:in_1_bang()
    local note = self.pattern[self.step] or 60
    self:outlet(1, "float", {note})
    self.step = (self.step % #self.pattern) + 1
end

function stepseq:in_1_reset()
    self.step = 1
end
```

## Limitations

1. **No auto-reload** — `.pd_lua` files load once per session. Restart Pd/plugdata to pick up changes. Live-coding via `pdluax` or `reload` message is available.

2. **Performance** — Lua DSP is slower than C. Use for control logic and moderate DSP only.

3. **Atoms must be tables** — `outlet()` and `pd.send()` require table arguments, not bare values.

4. **0-based array indexing** — Pd arrays use 0-based indices, Lua uses 1-based. Be careful.

5. **Fixed inlets/outlets** — Cannot change after creation.

6. **Shared Lua state** — All objects share one Lua interpreter. Always use `local` for variables and functions.

7. **DSP reload clicks** — Reloading DSP code has no cross-fade, causing potential audio clicks.

8. **Float on SIGNAL inlet** — Float messages on SIGNAL inlets are treated as constant signals in `perform`, not control messages. Use `DATA` inlets for control alongside signal.
