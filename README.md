# TerminalFaker

Two standalone Python 3.6+ scripts for faking terminal/monitoring output — demos, tutorials, screenshots, background footage. No dependencies beyond stdlib (`curses` for the dashboard).

- **`mock_terminal.py`** — plays a scripted fake shell session (prompt, typed input, output) with color and typing animation. Full docs: [`mock_terminal.md`](mock_terminal.md).
- **`dashboard.py`** — bashtop-like grid of independently animated regions (gauges, timelines, logs, status lights, matrix rain, scrolling text, and a terminal pane that reuses `mock_terminal.py`). Full docs: [`dashboard.md`](dashboard.md).

`dashboard.py` imports `mock_terminal.py` as a library; `mock_terminal.py` stays fully standalone.

## Quick start

```bash
python mock_terminal.py demo.txt
python dashboard.py examples/dashboard/layout.txt
```

## Common input-file format

Both tools read plain-text files with the same two-part shape:

```
KEY: value
KEY: value
---
block content
---
block content
```

- **Header** — `KEY: value` lines before the first `---`, for global/region config.
- **Blocks** — everything after, separated by `---`; meaning depends on the file (cycles for a terminal script, one block per dashboard region, etc.).
- **`INCLUDE: path/to/file`** — replaced with that file's contents (resolved relative to the including file's dir) before parsing. Works in any of these files, nests, and errors out on circular includes.
- **Colors** — `black red green yellow blue magenta cyan white`, plus `bold dim italic underline`, combinable (e.g. `bold green`). Same names everywhere.
- **Comments** — `#` lines are ignored in `mock_terminal.py` input files.

### `mock_terminal.py` file format

```
PROMPT: user@host:~ $ 
PROMPT_COLOR: green
INPUT_COLOR: cyan
OUTPUT_COLOR: white
INPUT_SPEED: 0.05
INITIAL_WAIT: 5
---
INPUT: echo "Hello World"
OUTPUT:
Hello World
WAIT: 2
```

- Header sets `PROMPT`, `PROMPT_COLOR`, `INPUT_COLOR`, `OUTPUT_COLOR`, `INPUT_SPEED`, `INPUT_SPEED_RANDOMNESS`/`INPUT_SPEED_MIN`/`INPUT_SPEED_MAX`, `INITIAL_WAIT`.
- Each `---`-separated cycle: `INPUT:` (required), `OUTPUT:` (optional, multi-line), `WAIT:` (default 2s), per-cycle `PROMPT:`/`PROMPT_COLOR:` overrides.
- Inline color markup: `{colorname}text{reset}` inside `INPUT:`/`OUTPUT:`; escape literal braces with `\{`/`\}`.
- CLI: `python mock_terminal.py <input_file> [--wait N] [--no-clear] [--speed S] [--randomness] [--speed-min N] [--speed-max N]`.

See [`mock_terminal.md`](mock_terminal.md) for full details and more examples.

### `dashboard.py` file format

```
TITLE: System Monitor
REFRESH_RATE: 0.1
---
REGION: cpu_gauge
TYPE: gauge
ROW: 0
COL: 0
DATA: cpu.gauge.txt
```

- Layout file header: `TITLE`, `REFRESH_RATE` (seconds/frame, overridden by `--fps`).
- Each region block: `REGION`, `TYPE` (`gauge`, `timeline`, `log`, `status`, `matrix`, `text`, `terminal`), `ROW`/`COL`, `ROWSPAN`/`COLSPAN`, `DATA` (path to that region's own `KEY: value`/`---` data file).
- Module data-file formats (one per `TYPE`):
  - **`gauge`** — `LABEL`, `MIN`/`MAX`, `UNIT`, `WARN`/`CRIT` or `COLORS: value:color,...`, `INTERVAL`, body `VALUES: n,n,n` replayed in a loop.
  - **`timeline`** — same shape as `gauge` plus `WINDOW` (points kept) and `STYLE` (`filled`/`dotted`/`ascii`); scrolling sparkline.
  - **`log`** — `INTERVAL_MIN`/`INTERVAL_MAX`, `LOOP`; body is literal log lines appended at random intervals, auto-colored on `error`/`crit`/`fail`/`warn`.
  - **`status`** — `INTERVAL` header, then one `NAME:`/`STATES: color,color,...` block per indicator, cycling states.
  - **`matrix`** — `CHARSET` (`ascii`/`binary`/`katakana`), `SPEED`, `COLOR`; optional body of tokens (e.g. via `INCLUDE:`) to rain instead of random glyphs.
  - **`text`** — `TEXT:` template line (`{var}` placeholders), `COLOR`, `INTERVAL`; then `VAR:`/`VALUES:` blocks cycling each placeholder's value on each tick.
  - **`terminal`** — `DATA:` pointing at a `mock_terminal.py`-format file; reuses that engine's typing/color rendering, looping.
- CLI: `python dashboard.py <layout_file> [--fps N]`, `q` to quit.

See [`dashboard.md`](dashboard.md) for the complete reference and [`examples/dashboard/`](examples/dashboard/) for a working layout.

## Examples

- [`examples/dashboard/`](examples/dashboard/) — sample dashboard layout and data files.
- [`ep01/`](ep01/) — a larger worked example (multi-region dashboard + terminal session).

## License

`mock_terminal.py` / `mock_terminal.md`: Creative Commons Attribution 4.0 International — see [`mock_terminal.md`](mock_terminal.md).
