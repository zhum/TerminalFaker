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
| `TYPE` | One of `gauge`, `timeline`, `log`, `status`, `matrix`, `terminal` |
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

### `terminal`

```
DATA: session.terminal.txt
```

Uses the **exact same input-file format as standalone `mock_terminal.py`**
(`PROMPT:`, `INPUT:`, `OUTPUT:`, `WAIT:`, inline `{color}` markup, etc. —
see `mock_terminal.md`). The region reuses `mock_terminal.py`'s own typing/
color engine, looping the cycles once they finish.

## Colors

All modules accept the same color names as `mock_terminal.py`:
`black red green yellow blue magenta cyan white bold dim italic underline`,
combinable (e.g. `bold green`).
