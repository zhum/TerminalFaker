# Dashboard — bashtop-like fake data grid

`dashboard.py` renders a grid of independently animated regions, each fed by
its own fake-data file, in a single curses screen. It's built on top of
`mock_terminal.py` (see `mock_terminal.md`) but that script stays fully
standalone — `dashboard.py` imports it as a library, never the reverse.

```
python dashboard.py <layout_file> [--fps N]
```

Press `q` to quit.

## Layout file

Same two-part style as `mock_terminal.py`'s input files: a `KEY: value`
header, then `---`-separated blocks — one block per region.

```
TITLE: System Monitor
REFRESH_RATE: 0.1
---
REGION: cpu_gauge
TYPE: gauge
ROW: 0
COL: 0
DATA: cpu.gauge.txt
---
REGION: net_chart
TYPE: timeline
ROW: 0
COL: 1
DATA: net.timeline.txt
---
REGION: main_log
TYPE: log
ROW: 1
COL: 0
COLSPAN: 2
DATA: system.log.txt
---
REGION: term
TYPE: terminal
ROW: 2
COL: 0
DATA: session.terminal.txt
---
REGION: status
TYPE: status
ROW: 2
COL: 1
DATA: services.status.txt
```

Header keys:

| Key | Meaning |
|---|---|
| `TITLE` | Optional title bar text |
| `REFRESH_RATE` | Seconds between frames (default `0.1`); overridden by `--fps` |

Region block keys:

| Key | Meaning |
|---|---|
| `REGION` | Unique region name |
| `TYPE` | One of `gauge`, `timeline`, `log`, `status`, `text`, `matrix`, `terminal`, `region` |
| `ROW` / `COL` | Grid cell position (0-based) |
| `ROWSPAN` / `COLSPAN` | Cells spanned (default `1`) |
| `DATA` | Path to the region's data file, relative to the layout file |

The grid size is derived from the highest `ROW`/`COL` + span used; cells are
equal-sized.

## `INCLUDE:` directive

Any line of the form:

```
INCLUDE: path/to/file.txt
```

is replaced with the contents of that file (resolved relative to the
including file's directory) before the file is parsed. Works in the layout
file and in every module's data file — nest as needed. Circular includes
raise an error instead of hanging.

## Module data-file formats

Each module's data file uses the same `KEY: value` header + `---`-blocks
style as the layout file.

### `gauge`

```
LABEL: CPU
MIN: 0
MAX: 100
UNIT: %
WARN: 70
CRIT: 90
INTERVAL: 1.0
---
VALUES: 23,45,67,89,42,30
```

Replays `VALUES` in a loop, one value every `INTERVAL` seconds. Bar turns
yellow at `WARN`, red at `CRIT` (default 70%/90% of the range).

Instead of `WARN`/`CRIT`, give `COLORS` a `value:color` list to pick the bar
color from arbitrary thresholds:

```
COLORS: 0:green,70:yellow,90:red
```

Entries must be ascending by value (out-of-order entries get a warning and
are auto-sorted). The color used is that of the highest threshold `<=` the
current value; below the first threshold the bar defaults to green. When
`COLORS` is present it replaces `WARN`/`CRIT` entirely.

### `timeline`

```
LABEL: Network In (Mbps)
COLOR: cyan
MIN: 0
MAX: 100
INTERVAL: 1.0
WINDOW: 120
---
VALUES: 12,15,14,20,18,30,45,22
```

Replays `VALUES` into a scrolling sparkline. `MIN`/`MAX` are optional
(auto-scales to the visible window if omitted). `WINDOW` caps how many
points are kept.

`COLORS` works the same way as for `gauge` — a `value:color` list, ascending,
picking the highest threshold `<=` each plotted value (points below the
first threshold, and the whole line when `COLORS` is omitted, use `COLOR`):

```
COLORS: 0:green,60:yellow,85:red
```

`STYLE` picks how the plot is drawn (default `filled`):

| Style | Look |
|---|---|
| `filled` | Solid unicode blocks (`█▁▂▃▄▅▆▇`), one column per value, eighth-cell vertical resolution. |
| `dotted` | Braille dot grid (2 values per character cell), higher resolution, half the on-screen width per value. |
| `ascii` | Plain-ASCII fill (`_ = #`), one column per value, three-level vertical resolution — for terminals without unicode/braille support. |

```
STYLE: dotted
```

### `log`

```
INTERVAL_MIN: 0.3
INTERVAL_MAX: 2.0
LOOP: true
---
[INFO] service started
[WARN] high memory usage
INCLUDE: shared_errors.log
```

Everything after the first `---` is treated as literal log lines (not
`KEY:` directives), appended one at a time at a random interval between
`INTERVAL_MIN` and `INTERVAL_MAX`. Lines containing `error`/`crit`/`fail` or
`warn` (case-insensitive) are colored red/yellow automatically.

### `status`

```
INTERVAL: 3.0
---
NAME: API
STATES: green,green,yellow,green
---
NAME: DB
STATES: green,red,green
```

Each block after the header is one named indicator; its light cycles
through `STATES` (any color name) every `INTERVAL` seconds.

### `matrix`

```
CHARSET: katakana
SPEED: 0.05
COLOR: green
```

`CHARSET` is `ascii`, `binary`, or `katakana`. A data file is optional — with
none, the region just rains random glyphs. Add a body to rain specific
tokens instead:

```
CHARSET: ascii
SPEED: 0.04
---
INCLUDE: wordlist.txt
```

### `text`

```
TEXT: CPU {cpu}% / MEM {mem}%\nUptime: 14d
COLOR: bold cyan
INTERVAL: 1.0
---
VAR: cpu
VALUES: 12,18,45,80
---
VAR: mem
VALUES: 30,32,31
```

`TEXT` is a single line; `\n` inside it starts a new output line. `{var}`
placeholders are filled from the `VAR:`/`VALUES:` blocks (comma-separated,
no escaping), cycling one value every `INTERVAL` seconds. Unbound `{var}`s
default to `?`.

### `region`

Fills a `TEMPLATE` with `{var}` placeholders whose values come from `VARS`
blocks (one block per var):

```
TEMPLATE: CPU: {cpu}%\nStatus: {status}\n{load}
INTERVAL: 1.0
---
VAR: cpu
VALUES: 12;18;45;80
---
VAR: status
LINES:
all systems nominal
.
degraded — retrying
node down
.
---
VAR: load
TYPE: bar
STYLE: solid
DASH: 1
MIN: 0
MAX: 100
START: 10
END: 95
TIME: 8
RANDOM: 0.3
TEMPLATE: [{bar}] {cur}/{max} eta {estimated}s
```

`TEMPLATE` (header) is one line; `\n` inside it starts a new output line
(same convention as `text`'s `TEXT:`). `INTERVAL` is how often list-kind
vars advance, by default.

To sync every var to one full animation cycle, set `DURATION` (seconds) on
the header instead: each list-kind var then spaces its own steps as
`DURATION / (count - 1)`, so it lands on its last value exactly at
`DURATION`, and any `bar` var whose `TIME` isn't set defaults to `DURATION`
too — the whole region reaches its end state together, then loops. A var
can still opt out by giving its own `INTERVAL` (list vars) or `TIME` (bar
vars) in its block.

Each `VARS` block starts with `VAR: name` and is one of:

| Kind | Block | Value |
|---|---|---|
| List | `VALUES: a;b\;c` | `;`-separated strings (`\;` escapes a literal `;`); cycles one per `INTERVAL`. |
| Multi-line list | `LINES:` followed by lines, items separated by a line containing just `.` | Each item can span multiple lines; cycles one per `INTERVAL`. A lone `SAME` (or `SAME*N`) item repeats the previous item for 1 (or `N`) more steps instead of being literal text; escape as `\SAME`/`\SAME*N` for a literal line. |
| Range | `RANGE: start;end` | Counts (inclusive) from `start` to `end` (steps down if `end < start`), one step per `INTERVAL`. Integer if neither bound has a `.`; otherwise steps by the smallest decimal place seen and keeps that many digits (`RANGE: 5.0;6.5` → `5.0, 5.1, ... 6.5`). |
| Progress bar | `TYPE: bar` plus bar settings below | An animated bar, updated every frame (not gated by `INTERVAL`). |

Bar settings:

| Key | Meaning |
|---|---|
| `STYLE` | `solid` (`█`/`░`), `dots` (`•`/`·`), `hash` (`#`/`-`), `line` (`-`/` `); default `solid` |
| `DASH` | `true`/`1` shows a rotating spinner at the fill edge |
| `MIN` / `MAX` | Value range the bar's fill fraction is computed against (default `0`/`100`) |
| `START` / `END` | Animated value's start/end points (default `MIN`/`MAX`) |
| `TIME` | Seconds to animate from `START` to `END`, then loops |
| `RANDOM` | Max random seconds of jitter added per frame (default `0`) |
| `ESTIMATED` | Fixed value for `{estimated}`; if omitted, counts down `TIME` remaining |
| `TEMPLATE` | The bar's own line; `{bar}` expands to fill the rest of the region's width, so the line spans the full width. Also supports `{min}`, `{max}`, `{cur}`, `{elapsed}`, `{estimated}` |

### `terminal`

```
DATA: session.terminal.txt
```

Uses the **exact same input-file format as standalone `mock_terminal.py`**
(`PROMPT:`, `INPUT:`, `OUTPUT:`, `WAIT:`, inline `{color}` markup, etc. —
see `mock_terminal.md`). The region reuses `mock_terminal.py`'s own typing/
color engine, replaying the flat instruction stream in order and looping
back to the start once it finishes.

## Colors

All modules accept the same color names as `mock_terminal.py`:
`black red green yellow blue magenta cyan white bold dim italic underline`,
combinable (e.g. `bold green`).
