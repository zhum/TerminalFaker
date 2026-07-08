#!/usr/bin/env python3
"""
Fake dashboard generator — a bashtop-like grid of independently animated,
fake-data-driven regions (gauges, timelines, logs, status lights, matrix
rain, and a terminal I/O pane reusing mock_terminal.py).

Usage:
    python dashboard.py <layout_file> [--fps N]

See dashboard.md for the layout file format, each module's data-file
directives, and the INCLUDE directive.
"""

import argparse
import curses
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

from dashboard_modules import (
    MODULE_REGISTRY,
    init_colors,
    load_with_includes,
    parse_kv_body,
    safe_addstr,
)


@dataclass
class RegionSpec:
    name: str
    type: str
    row: int = 0
    col: int = 0
    rowspan: int = 1
    colspan: int = 1
    data: Optional[str] = None


def parse_layout(text, base_dir):
    header, blocks = parse_kv_body(text)
    title = header.get('title', '')
    refresh_rate = float(header.get('refresh_rate', 0.1))

    regions = []
    for block in blocks:
        kv = {}
        for line in block.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or ':' not in line:
                continue
            key, value = line.split(':', 1)
            kv[key.strip().lower()] = value.strip()

        if 'region' not in kv or 'type' not in kv:
            continue

        data_path = kv.get('data')
        if data_path and not os.path.isabs(data_path):
            data_path = os.path.join(base_dir, data_path)

        regions.append(RegionSpec(
            name=kv['region'],
            type=kv['type'].lower(),
            row=int(kv.get('row', 0)),
            col=int(kv.get('col', 0)),
            rowspan=int(kv.get('rowspan', 1)),
            colspan=int(kv.get('colspan', 1)),
            data=data_path,
        ))
    return title, refresh_rate, regions


def build_windows(stdscr, regions, has_title):
    h, w = stdscr.getmaxyx()
    top = 1 if has_title else 0
    usable_h = max(1, h - top)

    n_rows = max((r.row + r.rowspan for r in regions), default=1)
    n_cols = max((r.col + r.colspan for r in regions), default=1)
    cell_h = max(1, usable_h // n_rows)
    cell_w = max(1, w // n_cols)

    windows = {}
    for r in regions:
        y = top + r.row * cell_h
        x = r.col * cell_w
        win_h = min(cell_h * r.rowspan, h - y)
        win_w = min(cell_w * r.colspan, w - x)
        if win_h <= 1 or win_w <= 1 or y >= h or x >= w:
            continue
        windows[r.name] = curses.newwin(win_h, win_w, y, x)
    return windows


def run_dashboard(stdscr, layout_file, fps):
    curses.curs_set(0)
    stdscr.nodelay(True)
    colors = init_colors()

    base_dir = os.path.dirname(os.path.abspath(layout_file))
    layout_text = load_with_includes(layout_file)
    title, refresh_rate, region_specs = parse_layout(layout_text, base_dir)

    windows = build_windows(stdscr, region_specs, bool(title))
    modules = {}
    for r in region_specs:
        cls = MODULE_REGISTRY.get(r.type)
        if cls is None:
            continue
        if r.name not in windows:
            continue
        modules[r.name] = cls(r.name, r.data, colors)

    frame_delay = (1.0 / fps) if fps else refresh_rate

    while True:
        now = time.monotonic()
        stdscr.erase()
        if title:
            safe_addstr(stdscr, 0, 2, title, attr=curses.A_BOLD)
        stdscr.noutrefresh()

        for r in region_specs:
            mod = modules.get(r.name)
            win = windows.get(r.name)
            if mod is None or win is None:
                continue
            mod.update(now)
            mod.render(win)
        curses.doupdate()

        ch = stdscr.getch()
        if ch in (ord('q'), ord('Q')):
            break
        time.sleep(frame_delay)


def main():
    parser = argparse.ArgumentParser(
        description='Run a bashtop-like fake dashboard driven by data files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Example layout file:

    TITLE: System Monitor
    REFRESH_RATE: 0.1
    ---
    REGION: cpu_gauge
    TYPE: gauge
    ROW: 0
    COL: 0
    DATA: cpu.gauge.txt
    ---
    REGION: term
    TYPE: terminal
    ROW: 1
    COL: 0
    DATA: session.terminal.txt

See dashboard.md for the full layout format, each module's data-file
directives, and the INCLUDE directive. Press q to quit.
        '''
    )
    parser.add_argument('layout_file', help='Dashboard layout file')
    parser.add_argument('--fps', type=float, default=None,
                        help='Override refresh rate (frames per second)')
    args = parser.parse_args()

    try:
        curses.wrapper(run_dashboard, args.layout_file, args.fps)
    except KeyboardInterrupt:
        pass
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
