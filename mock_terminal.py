#!/usr/bin/env python3
"""
Mock Terminal Generator

Generates realistic terminal input/output sequences from a simple text format.
Supports color styling, typing animations, and configurable delays.

Usage:
    python mock_terminal.py <input_file> [--wait SECONDS]
    python mock_terminal.py demo.txt --wait 3
"""

import sys
import time
import argparse
import os
import random
import re
from typing import Dict, List, Tuple
from dataclasses import dataclass

# Matches inline color markup like {red}...{reset} or {bold green}...{/}
COLOR_TAG_RE = re.compile(r'\{([\w ]+)\}')

# Placeholders used to protect \{ and \} from being parsed as markup
_ESCAPED_LBRACE = '\x00ESC_LBRACE\x00'
_ESCAPED_RBRACE = '\x00ESC_RBRACE\x00'

# ANSI color codes
COLORS = {
    'black': '\033[30m',
    'red': '\033[31m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'magenta': '\033[35m',
    'cyan': '\033[36m',
    'white': '\033[37m',
    'bold': '\033[1m',
    'dim': '\033[2m',
    'italic': '\033[3m',
    'underline': '\033[4m',
    'reset': '\033[0m',
}


@dataclass
class Config:
    """Terminal configuration from input file"""
    prompt: str = "$ "
    prompt_color: str = "green"
    input_color: str = "cyan"
    output_color: str = "white"
    type_delay: float = 0.05
    input_speed: float = 0.05
    initial_wait: float = 5.0
    input_speed_randomness: bool = False
    input_speed_min: float = 0.01
    input_speed_max: float = 0.1


@dataclass
class Cycle:
    """A single input/output cycle.

    `actions` is an ordered list of ('input', text) / ('output', text) /
    ('wait', seconds) tuples, preserving file order so WAIT can land
    anywhere in the sequence (before INPUT, mid-OUTPUT, at the end, etc).
    """
    actions: list = None
    prompt: str = None
    prompt_color: str = None
    type_delay: float = 0.05


class MockTerminal:
    """Generates mock terminal output"""

    def __init__(self, config: Config, output=None):
        self.config = config
        self.output = output if output is not None else sys.stdout

    def clear_screen(self):
        """Clear the terminal screen"""
        if self.output is sys.stdout:
            os.system('clear' if os.name != 'nt' else 'cls')

    def get_color(self, color_name: str) -> str:
        """Get ANSI code(s) for a color name, supporting combos like 'bold green';
        fallback to white if nothing recognized"""
        codes = ''.join(COLORS.get(word, '') for word in color_name.split())
        return codes or COLORS['white']

    def parse_colored_text(self, text: str, default_color: str) -> List[Tuple[str, str]]:
        """Split text into (segment, color) pairs based on inline {colorname} markup.
        {reset} or {default} reverts to default_color. Unrecognized tags are left
        as literal text (e.g. a stray '{foo}'). Use \\{ and \\} to emit literal braces
        without triggering markup (e.g. for JSON output)."""
        protected = text.replace('\\{', _ESCAPED_LBRACE).replace('\\}', _ESCAPED_RBRACE)
        parts = COLOR_TAG_RE.split(protected)
        segments = []
        current_color = default_color
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                tag = part.strip().lower()
                words = tag.split()
                if tag in ('reset', 'default'):
                    current_color = default_color
                elif words and all(w in COLORS for w in words):
                    current_color = tag
                else:
                    segments.append((f'{{{part}}}', current_color))
            elif part:
                segments.append((part, current_color))

        return [
            (seg_text.replace(_ESCAPED_LBRACE, '{').replace(_ESCAPED_RBRACE, '}'), seg_color)
            for seg_text, seg_color in segments
        ]

    def type_text(self, text: str, color: str, speed: float = None):
        """Type text character by character, honoring optional inline {colorname} markup"""
        if speed is None:
            speed = self.config.input_speed

        segments = self.parse_colored_text(text, color)
        active_color = None

        for seg_text, seg_color in segments:
            if seg_color != active_color:
                self.output.write(self.get_color(seg_color))
                self.output.flush()
                active_color = seg_color

            for char in seg_text:
                self.output.write(char)
                self.output.flush()

                # Calculate delay for this character
                if self.config.input_speed_randomness:
                    delay = random.uniform(self.config.input_speed_min, self.config.input_speed_max)
                else:
                    delay = speed

                time.sleep(delay)

        self.output.write(COLORS['reset'])
        self.output.flush()

    def print_output(self, text: str, color: str):
        """Print output, honoring optional inline {colorname} markup"""
        segments = self.parse_colored_text(text, color)
        rendered = ''.join(f"{self.get_color(seg_color)}{seg_text}" for seg_text, seg_color in segments)
        print(f"{rendered}{COLORS['reset']}", file=self.output)

    def print_prompt(self, prompt: str = None, prompt_color: str = None):
        """Print the prompt, optionally overriding text/color for this cycle"""
        prompt = prompt if prompt is not None else self.config.prompt
        prompt_color = prompt_color if prompt_color is not None else self.config.prompt_color
        segments = self.parse_colored_text(prompt, prompt_color)
        active_color = None

        for seg_text, seg_color in segments:
            if seg_color != active_color:
                self.output.write(self.get_color(seg_color))
                self.output.flush()
                active_color = seg_color
            self.output.write(seg_text)
        self.output.write(COLORS['reset'])
        self.output.flush()

    def run_cycle(self, cycle: Cycle, print_prompt: bool = True):
        """Run a single input/output cycle, executing its actions in file order"""

        if print_prompt:
            self.print_prompt(cycle.prompt, cycle.prompt_color)

        if cycle.type_delay > 0:
            time.sleep(cycle.type_delay)

        for action, value in cycle.actions:
            if action == 'input':
                self.type_text(value, self.config.input_color)
                print(file=self.output)  # Newline after input
            elif action == 'output':
                output_lines = value.split('\n')
                for line in output_lines:
                    if line:  # Skip empty lines in iteration, but preserve them in output
                        self.print_output(line, self.config.output_color)
                    else:
                        print(file=self.output)
            elif action == 'wait':
                if value > 0:
                    time.sleep(value)


    def run(self, cycles: List[Cycle], initial_wait: float = None, print_prompt: bool = True):
        """Run the full terminal sequence"""
        if initial_wait is None:
            initial_wait = self.config.initial_wait

        self.clear_screen()

        # Initial wait before starting
        if initial_wait > 0:
            # print(f"Starting in {initial_wait} seconds...", flush=True)
            time.sleep(initial_wait)

        # Run all cycles
        for i, cycle in enumerate(cycles):
            self.run_cycle(cycle, print_prompt=(print_prompt or i > 0))


def parse_input_file(filepath: str, content: str = None) -> Tuple[Config, List[Cycle]]:
    """Parse the input file and return config and cycles.

    If `content` is given, it is parsed directly and `filepath` is only used
    for error messages (used by callers that need to pre-process the file,
    e.g. to resolve INCLUDE directives, before handing it to this parser).
    """
    config = Config()
    cycles = []

    if content is None:
        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            print(f"Error: File '{filepath}' not found.")
            sys.exit(1)

    # Split by cycle separator
    sections = content.split('---')

    # First section is config
    config_section = sections[0].strip()
    for line in config_section.split('\n'):
        # line = line.strip()
        if not line or line.startswith('#'):
            continue

        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            raw_value = value
            value = value.strip()

            if key == 'prompt':
                config.prompt = raw_value
            elif key == 'prompt_color':
                config.prompt_color = value
            elif key == 'input_color':
                config.input_color = value
            elif key == 'output_color':
                config.output_color = value
            elif key == 'input_speed':
                try:
                    config.input_speed = float(value)
                except ValueError:
                    print(f"Warning: Invalid input_speed value '{value}', using default")
            elif key == 'initial_wait':
                try:
                    config.initial_wait = float(value)
                except ValueError:
                    print(f"Warning: Invalid initial_wait value '{value}', using default")
            elif key == 'input_speed_randomness':
                config.input_speed_randomness = value.lower() in ('true', 'yes', '1', 'on')
            elif key == 'input_speed_min':
                try:
                    config.input_speed_min = float(value)
                except ValueError:
                    print(f"Warning: Invalid input_speed_min value '{value}', using default")
            elif key == 'input_speed_max':
                try:
                    config.input_speed_max = float(value)
                except ValueError:
                    print(f"Warning: Invalid input_speed_max value '{value}', using default")

    # Parse cycles
    for section in sections[1:]:
        section = section.strip()
        if not section:
            continue

        cycle_config = {
            'actions': [],
            'type_delay': 0.2,
            'prompt': None,
            'prompt_color': None,
            'has_input': False,
        }

        lines = section.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]

            if line.strip().startswith('#') or not line.strip():
                i += 1
                continue

            if line.startswith('INPUT:'):
                cycle_config['actions'].append(('input', line.replace('INPUT:', '', 1).strip()))
                cycle_config['has_input'] = True
            elif line.startswith('OUTPUT:'):
                # Collect multi-line output
                output_lines = []
                i += 1
                while i < len(lines):
                    if lines[i].startswith(('WAIT:', 'INPUT:', 'PROMPT:', 'PROMPT_COLOR:')):
                        break
                    output_lines.append(lines[i])
                    i += 1
                cycle_config['actions'].append(('output', '\n'.join(output_lines)))
                continue
            elif line.startswith('WAIT:'):
                try:
                    cycle_config['actions'].append(('wait', float(line.replace('WAIT:', '', 1).strip())))
                except ValueError:
                    pass
            elif line.startswith('TYPE_DELAY:'):
                try:
                    cycle_config['type_delay'] = float(line.replace('TYPE_DELAY:', '', 1).strip())
                except ValueError:
                    pass
            elif line.startswith('PROMPT_COLOR:'):
                cycle_config['prompt_color'] = line.replace('PROMPT_COLOR:', '', 1).strip()
            elif line.startswith('PROMPT:'):
                cycle_config['prompt'] = line.replace('PROMPT:', '', 1)

            i += 1

        if cycle_config['has_input']:
            if not any(action == 'wait' for action, _ in cycle_config['actions']):
                cycle_config['actions'].append(('wait', 2.0))
            cycles.append(Cycle(
                actions=cycle_config['actions'],
                prompt=cycle_config['prompt'],
                prompt_color=cycle_config['prompt_color'],
                type_delay=cycle_config['type_delay']
            ))

    return config, cycles


def main():
    parser = argparse.ArgumentParser(
        description='Generate mock terminal input/output sequences',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Example input file format:

    # Configuration section
    PROMPT: $ 
    PROMPT_COLOR: green
    INPUT_COLOR: cyan
    OUTPUT_COLOR: white
    INPUT_SPEED: 0.05
    INPUT_SPEED_RANDOMNESS: false
    INPUT_SPEED_MIN: 0.01
    INPUT_SPEED_MAX: 0.1
    INITIAL_WAIT: 5

    ---
    INPUT: ls -la
    OUTPUT:
    total 48
    drwxr-xr-x  5 user  staff   160 Jul  8 12:34 .
    drwxr-xr-x 10 root  wheel   320 Jul  7 10:20 ..
    WAIT: 2

    ---
    INPUT: python script.py
    OUTPUT:
    Hello, World!
    Processing complete...
    WAIT: 3

Example with randomness:
    python mock_terminal.py demo.txt --randomness --speed-min 0.02 --speed-max 0.08
        '''
    )
    parser.add_argument('input_file', help='Input file with terminal sequences')
    parser.add_argument('--wait', type=float, default=None,
                        help='Initial wait time in seconds (overrides file setting)')
    parser.add_argument('--no-clear', action='store_true',
                        help='Do not clear screen at start')
    parser.add_argument('--speed', type=float, default=None,
                        help='Typing speed in seconds per character (overrides file setting)')
    parser.add_argument('--randomness', action='store_true',
                        help='Enable random typing speed (overrides file setting)')
    parser.add_argument('--speed-min', type=float, default=None,
                        help='Minimum typing speed when randomness is enabled')
    parser.add_argument('--speed-max', type=float, default=None,
                        help='Maximum typing speed when randomness is enabled')

    args = parser.parse_args()

    # Parse input file
    config, cycles = parse_input_file(args.input_file)

    # Override config with CLI arguments
    if args.wait is not None:
        config.initial_wait = args.wait
    if args.speed is not None:
        config.input_speed = args.speed
    if args.randomness:
        config.input_speed_randomness = True
    if args.speed_min is not None:
        config.input_speed_min = args.speed_min
    if args.speed_max is not None:
        config.input_speed_max = args.speed_max

    # Create and run terminal
    terminal = MockTerminal(config)

    try:
        wt = config.initial_wait if not args.no_clear else 0
        terminal.run(cycles, initial_wait=wt)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(0)


if __name__ == '__main__':
    main()
