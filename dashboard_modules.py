"""
Region modules for dashboard.py — a bashtop-like grid of fake-data panes.

Each module class implements the same three-method interface:
    parse(text)   -- turn a data-file's (already INCLUDE-expanded) text into state
    update(now)   -- advance animation/replay state given a monotonic timestamp
    render(win)   -- draw into a curses window

Shared utilities here (`load_with_includes`, `parse_kv_body`) are also used by
dashboard.py for the layout file itself, so INCLUDE and the KEY: value header
style stay consistent across the layout file and every module's data file.
"""

import curses
import os
import random
import re
import threading
import time
import unicodedata

# mock_terminal.py must stay importable and runnable completely on its own;
# this is the only direction the dependency goes (dashboard -> mock_terminal).
import mock_terminal

INCLUDE_RE = re.compile(r'^INCLUDE:\s*(.+?)\s*$')


def load_with_includes(path, _stack=None):
    """Read a file, recursively inlining any `INCLUDE: <path>` lines.

    Included paths are resolved relative to the including file's directory.
    Raises ValueError on a circular include chain.
    """
    path = os.path.abspath(path)
    stack = _stack or []
    if path in stack:
        chain = ' -> '.join(stack + [path])
        raise ValueError(f"Circular INCLUDE detected: {chain}")

    try:
        with open(path, 'r') as f:
            raw = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"INCLUDE target not found: {path}")

    base_dir = os.path.dirname(path)
    out_lines = []
    for line in raw.split('\n'):
        m = INCLUDE_RE.match(line)
        if m:
            inc_path = m.group(1).strip()
            if not os.path.isabs(inc_path):
                inc_path = os.path.join(base_dir, inc_path)
            out_lines.append(load_with_includes(inc_path, stack + [path]))
        else:
            out_lines.append(line)
    return '\n'.join(out_lines)


def parse_kv_body(text):
    """Split `KEY: value` header (before the first `---`) from the remaining
    `---`-separated blocks, mirroring mock_terminal.py's input-file style."""
    sections = text.split('---')
    header = {}
    for line in sections[0].split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or ':' not in stripped:
            continue
        key, value = stripped.split(':', 1)
        header[key.strip().lower()] = value.strip()
    blocks = [s.strip() for s in sections[1:]]
    return header, blocks


# ---------------------------------------------------------------------------
# curses color helpers
# ---------------------------------------------------------------------------

_CURSES_BASE_COLORS = {
    'black': curses.COLOR_BLACK,
    'red': curses.COLOR_RED,
    'green': curses.COLOR_GREEN,
    'yellow': curses.COLOR_YELLOW,
    'blue': curses.COLOR_BLUE,
    'magenta': curses.COLOR_MAGENTA,
    'cyan': curses.COLOR_CYAN,
    'white': curses.COLOR_WHITE,
}


def init_colors():
    """Set up curses color pairs once; returns a name -> attr map that
    modules combine (e.g. 'bold green') the same way mock_terminal.py does."""
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK

    attrs = {}
    pair_id = 1
    for name, value in _CURSES_BASE_COLORS.items():
        curses.init_pair(pair_id, value, bg)
        attrs[name] = curses.color_pair(pair_id)
        pair_id += 1
    attrs['bold'] = curses.A_BOLD
    attrs['dim'] = curses.A_DIM
    attrs['underline'] = curses.A_UNDERLINE
    attrs['reset'] = curses.A_NORMAL
    return attrs


def color_attr(colors, name):
    """Combine space-separated color/style words (e.g. 'bold green') into a
    single curses attribute, unknown words contribute nothing."""
    attr = curses.A_NORMAL
    for word in (name or '').lower().split():
        attr |= colors.get(word, 0)
    return attr


def safe_addstr(win, y, x, text, n=None, attr=curses.A_NORMAL):
    """addstr/addnstr wrapped against curses.error at the bottom-right cell,
    a well-known curses quirk rather than a real failure."""
    try:
        if n is None:
            win.addstr(y, x, text, attr)
        else:
            win.addnstr(y, x, text, max(0, n), attr)
    except curses.error:
        pass


def parse_color_thresholds(raw, context=''):
    """Parse a COLORS value: 'v1:color1,v2:color2,...' into (value, color)
    pairs sorted ascending by value. Warns and auto-sorts if given out of
    order rather than silently misrendering."""
    pairs = []
    for chunk in (raw or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ':' not in chunk:
            print(f"Warning: invalid COLORS entry '{chunk}'{context}, expected value:color")
            continue
        val_str, color = chunk.split(':', 1)
        try:
            val = float(val_str.strip())
        except ValueError:
            print(f"Warning: invalid COLORS value '{val_str}'{context}")
            continue
        pairs.append((val, color.strip()))

    if any(pairs[i][0] > pairs[i + 1][0] for i in range(len(pairs) - 1)):
        print(f"Warning: COLORS entries{context} are not sorted ascending, sorting automatically")
        pairs.sort(key=lambda p: p[0])

    return pairs


def color_for_value(pairs, value, default_color):
    """Color of the highest threshold <= value; below the first threshold
    (or if no pairs given) falls back to default_color."""
    chosen = default_color
    for threshold, color in pairs:
        if value >= threshold:
            chosen = color
        else:
            break
    return chosen


# ---------------------------------------------------------------------------
# base module
# ---------------------------------------------------------------------------

class Module:
    def __init__(self, name, data_path, colors):
        self.name = name
        self.data_path = data_path
        self.colors = colors
        text = load_with_includes(data_path) if data_path else ''
        self.parse(text)

    def parse(self, text):
        raise NotImplementedError

    def update(self, now):
        pass

    def render(self, win):
        raise NotImplementedError

    def _draw_frame(self, win, title):
        win.erase()
        win.box()
        h, w = win.getmaxyx()
        if title and w > 4:
            safe_addstr(win, 0, 2, f" {title} ", w - 4)


# ---------------------------------------------------------------------------
# gauge
# ---------------------------------------------------------------------------

class GaugeModule(Module):
    def parse(self, text):
        header, blocks = parse_kv_body(text)
        self.label = header.get('label', self.name)
        self.min = float(header.get('min', 0))
        self.max = float(header.get('max', 100))
        self.unit = header.get('unit', '')
        self.interval = float(header.get('interval', 1.0))
        colors_raw = header.get('colors')
        if colors_raw:
            self.color_thresholds = parse_color_thresholds(colors_raw, f" in gauge '{self.name}'")
        else:
            self.color_thresholds = None
        self.warn = float(header.get('warn', self.min + (self.max - self.min) * 0.7))
        self.crit = float(header.get('crit', self.min + (self.max - self.min) * 0.9))

        values = []
        for block in blocks:
            for line in block.split('\n'):
                line = line.strip()
                if line.startswith('VALUES:'):
                    raw = line.split(':', 1)[1]
                    values.extend(float(v) for v in raw.split(',') if v.strip())
        self.values = values or [self.min]
        self.idx = 0
        self.value = self.values[0]
        self.last_tick = 0.0

    def update(self, now):
        if now - self.last_tick >= self.interval:
            self.last_tick = now
            self.idx = (self.idx + 1) % len(self.values)
            self.value = self.values[self.idx]

    def render(self, win):
        self._draw_frame(win, self.label)
        h, w = win.getmaxyx()
        bar_w = max(0, w - 4)
        span = self.max - self.min
        pct = 0.0 if span == 0 else (self.value - self.min) / span
        pct = max(0.0, min(1.0, pct))
        filled = int(bar_w * pct)

        if self.color_thresholds is not None:
            color_name = color_for_value(self.color_thresholds, self.value, 'green')
        else:
            color_name = 'green'
            if self.value >= self.crit:
                color_name = 'red'
            elif self.value >= self.warn:
                color_name = 'yellow'
        attr = color_attr(self.colors, color_name)

        bar_row = h // 2
        if 0 < bar_row < h - 1 and bar_w > 0:
            safe_addstr(win, bar_row, 2, '█' * filled, attr=attr)
            safe_addstr(win, bar_row, 2 + filled, '░' * (bar_w - filled))

        label_row = min(h - 2, bar_row + 1)
        if label_row > bar_row:
            safe_addstr(win, label_row, 2, f"{self.value:.1f}{self.unit}", bar_w, attr)
        win.noutrefresh()


# ---------------------------------------------------------------------------
# timeline / sparkline
# ---------------------------------------------------------------------------

_SPARK_CHARS = '▁▂▃▄▅▆▇█'
# 3-level partial-row resolution for STYLE: ascii ('#' is the full-row char,
# used the same way _SPARK_CHARS[-1] ('█') is unused below since a fully
# filled row is drawn with fill_char directly).
_ASCII_LEVELS = ('_', '=', '#')


class TimelineModule(Module):
    def parse(self, text):
        header, blocks = parse_kv_body(text)
        self.label = header.get('label', self.name)
        self.color = header.get('color', 'cyan')
        self.min = float(header['min']) if 'min' in header else None
        self.max = float(header['max']) if 'max' in header else None
        self.interval = float(header.get('interval', 1.0))
        self.window = int(header.get('window', 120))
        colors_raw = header.get('colors')
        if colors_raw:
            self.color_thresholds = parse_color_thresholds(colors_raw, f" in timeline '{self.name}'")
        else:
            self.color_thresholds = None

        style = header.get('style', 'filled').lower()
        if style not in ('filled', 'dotted', 'ascii'):
            print(f"Warning: unknown STYLE '{style}' in timeline '{self.name}', using 'filled'")
            style = 'filled'
        self.style = style

        values = []
        for block in blocks:
            for line in block.split('\n'):
                line = line.strip()
                if line.startswith('VALUES:'):
                    raw = line.split(':', 1)[1]
                    values.extend(float(v) for v in raw.split(',') if v.strip())
        self.values = values or [0.0]
        self.idx = 0
        self.history = [self.values[0]]
        self.last_tick = 0.0

    def update(self, now):
        if now - self.last_tick >= self.interval:
            self.last_tick = now
            self.idx = (self.idx + 1) % len(self.values)
            self.history.append(self.values[self.idx])
            if len(self.history) > self.window:
                self.history = self.history[-self.window:]

    def _attr_for(self, default_attr, v):
        if self.color_thresholds is not None:
            return color_attr(self.colors, color_for_value(self.color_thresholds, v, self.color))
        return default_attr

    def render(self, win):
        h, w = win.getmaxyx()
        default_attr = color_attr(self.colors, self.color)
        plot_w = max(0, w - 4)
        # A braille column packs 2 samples, so pull twice as much history to
        # fill the same on-screen width as the 1-sample-per-column styles.
        needed = plot_w * 2 if self.style == 'dotted' else plot_w
        series = self.history[-needed:] if needed else []

        title = f"{self.label} {series[-1]:.1f}" if series else self.label
        self._draw_frame(win, title)

        lo = self.min if self.min is not None else (min(series) if series else 0.0)
        hi = self.max if self.max is not None else (max(series) if series else 1.0)
        if hi == lo:
            hi = lo + 1.0

        # Interior plot rows span 1..h-2 (row 0 and h-1 are the box border),
        # so the full region height is used regardless of window size.
        plot_h = max(0, h - 2)
        bottom_row = h - 2

        if self.style == 'dotted':
            self._render_dotted(win, series, lo, hi, plot_h, bottom_row, default_attr)
        else:
            fill_char = '#' if self.style == 'ascii' else '█'
            levels = _ASCII_LEVELS if self.style == 'ascii' else _SPARK_CHARS
            for i, v in enumerate(series):
                pct = max(0.0, min(1.0, (v - lo) / (hi - lo)))
                attr = self._attr_for(default_attr, v)
                steps = round(pct * plot_h * len(levels))
                full_rows, rem = divmod(steps, len(levels))
                col = 2 + i
                for r in range(plot_h):
                    row = bottom_row - r
                    if row < 1:
                        break
                    if r < full_rows:
                        safe_addstr(win, row, col, fill_char, attr=attr)
                    elif r == full_rows and rem > 0:
                        safe_addstr(win, row, col, levels[rem - 1], attr=attr)
                    else:
                        break
        win.noutrefresh()

    # Visual dot slots top-to-bottom within a braille cell map to these dot
    # bits (see Unicode Braille Patterns block, U+2800 + bitmask).
    _BRAILLE_LEFT_BITS = (0, 1, 2, 6)
    _BRAILLE_RIGHT_BITS = (3, 4, 5, 7)

    def _render_dotted(self, win, series, lo, hi, plot_h, bottom_row, default_attr):
        def filled_dots(v):
            pct = max(0.0, min(1.0, (v - lo) / (hi - lo)))
            return round(pct * plot_h * 4)

        for pair_idx in range(0, len(series), 2):
            left = series[pair_idx]
            right = series[pair_idx + 1] if pair_idx + 1 < len(series) else None
            filled_left = filled_dots(left)
            filled_right = filled_dots(right) if right is not None else 0
            attr = self._attr_for(default_attr, right if right is not None else left)
            col = 2 + pair_idx // 2

            for r in range(plot_h):
                row = bottom_row - r
                if row < 1:
                    break
                code = 0
                for v in range(4):
                    dot_index = r * 4 + (3 - v)
                    if dot_index < filled_left:
                        code |= 1 << self._BRAILLE_LEFT_BITS[v]
                    if right is not None and dot_index < filled_right:
                        code |= 1 << self._BRAILLE_RIGHT_BITS[v]
                if code:
                    safe_addstr(win, row, col, chr(0x2800 + code), attr=attr)
                elif filled_left == 0 and filled_right == 0:
                    break


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------

class LogModule(Module):
    def parse(self, text):
        header, blocks = parse_kv_body(text)
        self.interval_min = float(header.get('interval_min', 0.3))
        self.interval_max = float(header.get('interval_max', 2.0))
        self.loop = header.get('loop', 'true').lower() in ('true', 'yes', '1', 'on')

        body = '\n'.join(blocks)
        self.lines = [l for l in body.split('\n') if l.strip()] or ['(no log lines)']
        self.shown = []
        self.idx = 0
        self.next_at = 0.0

    def update(self, now):
        if now >= self.next_at:
            self.shown.append(self.lines[self.idx])
            self.idx += 1
            if self.idx >= len(self.lines):
                self.idx = 0 if self.loop else len(self.lines) - 1
            self.next_at = now + random.uniform(self.interval_min, self.interval_max)

    def render(self, win):
        self._draw_frame(win, self.name)
        h, w = win.getmaxyx()
        visible = max(0, h - 2)
        for i, line in enumerate(self.shown[-visible:]):
            lower = line.lower()
            if 'error' in lower or 'crit' in lower or 'fail' in lower:
                attr = color_attr(self.colors, 'red')
            elif 'warn' in lower:
                attr = color_attr(self.colors, 'yellow')
            else:
                attr = curses.A_NORMAL
            safe_addstr(win, 1 + i, 2, line, max(0, w - 4), attr)
        win.noutrefresh()


# ---------------------------------------------------------------------------
# status lights
# ---------------------------------------------------------------------------

class StatusModule(Module):
    def parse(self, text):
        header, blocks = parse_kv_body(text)
        self.interval = float(header.get('interval', 3.0))
        self.items = []
        for block in blocks:
            name = None
            states = ['green']
            for line in block.split('\n'):
                line = line.strip()
                if not line or line.startswith('#') or ':' not in line:
                    continue
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                if key == 'name':
                    name = value
                elif key == 'states':
                    states = [s.strip() for s in value.split(',') if s.strip()] or ['green']
            if name:
                self.items.append({'name': name, 'states': states, 'idx': 0})
        if not self.items:
            self.items = [{'name': self.name, 'states': ['green'], 'idx': 0}]
        self.last_tick = 0.0

    def update(self, now):
        if now - self.last_tick >= self.interval:
            self.last_tick = now
            for item in self.items:
                item['idx'] = (item['idx'] + 1) % len(item['states'])

    def render(self, win):
        self._draw_frame(win, self.name)
        h, w = win.getmaxyx()
        for i, item in enumerate(self.items):
            row = 1 + i
            if row >= h - 1:
                break
            state = item['states'][item['idx']]
            attr = color_attr(self.colors, state)
            safe_addstr(win, row, 2, '●', attr=attr)
            safe_addstr(win, row, 4, item['name'], max(0, w - 6))
        win.noutrefresh()


# ---------------------------------------------------------------------------
# matrix rain
# ---------------------------------------------------------------------------

_CHARSETS = {
    'ascii': '!<>-_\\/[]{}=+*^?#$%&01',
    'binary': '01',
    'katakana': 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン',
}


def _display_width(ch):
    """Terminal cell width of one character. East-Asian wide/fullwidth
    glyphs (e.g. katakana) occupy 2 columns even though curses' cell model
    only advances the cursor by 1, so callers must account for this
    themselves to avoid the terminal auto-wrapping past a window's edge."""
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1


class MatrixModule(Module):
    def parse(self, text):
        header, blocks = parse_kv_body(text)
        charset_name = header.get('charset', 'ascii').lower()
        self.charset = _CHARSETS.get(charset_name, _CHARSETS['ascii'])
        self.speed = float(header.get('speed', 0.05))
        self.color = header.get('color', 'green')

        words = []
        for block in blocks:
            for line in block.split('\n'):
                line = line.strip()
                if line:
                    words.append(line)
        self.words = words
        self.columns = None
        self.last_tick = 0.0
        self.pending = True

    def update(self, now):
        self.pending = now - self.last_tick >= self.speed
        if self.pending:
            self.last_tick = now

    def _ensure_columns(self, plot_h, plot_w):
        if self.columns is None or len(self.columns) != plot_w:
            self.columns = [random.randint(-plot_h, 0) for _ in range(max(plot_w, 1))]

    def render(self, win):
        self._draw_frame(win, self.name)
        h, w = win.getmaxyx()
        # Interior only (row 0/h-1 and col 0/w-1 are the box border), same
        # inset every other module uses, so the rain stays inside its frame.
        plot_h = max(0, h - 2)
        plot_w = max(0, w - 4)
        self._ensure_columns(plot_h, plot_w)
        if self.pending:
            for i in range(plot_w):
                self.columns[i] += 1
                if self.columns[i] > plot_h + random.randint(0, max(plot_h, 1)):
                    self.columns[i] = random.randint(-plot_h, 0)

        attr = color_attr(self.colors, self.color)
        for i in range(plot_w):
            y = self.columns[i]
            if 0 <= y < plot_h:
                glyph = random.choice(self.words) if self.words else random.choice(self.charset)
                # A wide glyph landing on the last plot column would make
                # the terminal auto-wrap and overwrite column 0 of whatever
                # sits next in the real layout (e.g. the region below) -
                # skip it there instead.
                if i + _display_width(glyph[0]) > plot_w:
                    continue
                safe_addstr(win, 1 + y, 2 + i, glyph, max(1, plot_w - i), attr)
        win.noutrefresh()


# ---------------------------------------------------------------------------
# terminal I/O (reuses mock_terminal.py as a library)
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r'(\x1b\[[0-9;]*m)')
_ANSI_TO_NAME = {code: name for name, code in mock_terminal.COLORS.items()}


class _AnsiWriter:
    """File-like object MockTerminal writes into; keeps a capped ring of raw
    text (including ANSI codes) that the render step re-parses each frame."""

    _MAX_LEN = 20000

    def __init__(self):
        self._lock = threading.Lock()
        self._raw = ''

    def write(self, s):
        with self._lock:
            self._raw += s
            if len(self._raw) > self._MAX_LEN:
                self._raw = self._raw[-self._MAX_LEN:]

    def flush(self):
        pass

    def snapshot(self):
        with self._lock:
            return self._raw


def _parse_ansi_lines(raw, colors):
    """Turn raw text containing mock_terminal.py's ANSI codes into a list of
    lines, each a list of (text, curses_attr) segments."""
    lines = [[]]
    current_attr = curses.A_NORMAL
    for token in _ANSI_RE.split(raw):
        if not token:
            continue
        if token.startswith('\x1b['):
            name = _ANSI_TO_NAME.get(token)
            if name == 'reset':
                current_attr = curses.A_NORMAL
            elif name:
                current_attr |= color_attr(colors, name)
            continue
        parts = token.split('\n')
        for i, seg in enumerate(parts):
            if i > 0:
                lines.append([])
            if seg:
                lines[-1].append((seg, current_attr))
    return lines


class TerminalModule(Module):
    def parse(self, text):
        config, cycles = mock_terminal.parse_input_file(self.data_path, content=text)
        self._config = config
        self._cycles = cycles
        self._writer = _AnsiWriter()
        self._started = False

    def _run_loop(self):
        term = mock_terminal.MockTerminal(self._config, output=self._writer)
        while True:
            if self._cycles:
                term.run(self._cycles, initial_wait=0)
            time.sleep(1.0)

    def update(self, now):
        if not self._started:
            self._started = True
            threading.Thread(target=self._run_loop, daemon=True).start()

    def render(self, win):
        self._draw_frame(win, self.name)
        h, w = win.getmaxyx()
        lines = _parse_ansi_lines(self._writer.snapshot(), self.colors)
        visible = max(0, h - 2)
        for i, segs in enumerate(lines[-visible:] if visible else []):
            x = 2
            for seg_text, attr in segs:
                if x >= w - 1:
                    break
                safe_addstr(win, 1 + i, x, seg_text, w - 1 - x, attr)
                x += len(seg_text)
        win.noutrefresh()


MODULE_REGISTRY = {
    'gauge': GaugeModule,
    'timeline': TimelineModule,
    'log': LogModule,
    'status': StatusModule,
    'matrix': MatrixModule,
    'terminal': TerminalModule,
}
