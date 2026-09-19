# Mock Terminal Generator

Copyright (c) 2026 Sergey Zhumatiy <sergzhum@gmail.com>

This work is licensed under the Creative Commons Attribution 4.0 International License. 
To view a copy of this license, visit http://creativecommons.org 
or send a letter to Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.

## Purpose

Generate realistic terminal input/output sequences for demos, tutorials, and documentation.

Describe your fake shell prompt, timing options and input/output text sequences in a file,
then use it as a script argument. By default script cleans the terminal, waits for specified delay,
then plays your scenario.

## Features

- **Color Support**: Style prompts, input, and output with ANSI colors
- **Typing Animation**: User input appears with character-by-character animation
- **Configurable Timing**: Control initial wait, typing speed, and delays between commands
- **Simple Format**: Easy-to-read text format for defining sequences
- **CLI Options**: Override file settings with command-line arguments

## Installation

The script requires only Python 3.6+. No external dependencies needed.

```bash
chmod +x mock_terminal.py
```

## Quick Start

```bash
./mock_terminal.py demo.txt

# or

python mock_terminal.py demo.txt
```

With custom wait time:

```bash
python mock_terminal.py demo.txt --wait 3
```

## Input File Format

A file has two parts: a configuration section, then a single `---` separator,
then a stream of instructions. Instructions are interpreted **one at a time,
in file order** — there's no cycle/block grouping and no repeated `---`
needed between commands. (A stray `---` line in the instruction stream
matches no instruction keyword, so it's silently ignored — handy as a visual
divider between commands if you like the look.)

### Configuration Section

The section before the first `---` defines global settings:

```
PROMPT: user@host:~ $ 
PROMPT_COLOR: green
INPUT_COLOR: cyan
OUTPUT_COLOR: white
INPUT_SPEED: 0.05
INITIAL_WAIT: 5
```

**Available Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `PROMPT` | `$ ` | The shell prompt text |
| `PROMPT_COLOR` | `green` | Color of the prompt |
| `INPUT_COLOR` | `cyan` | Color of user input |
| `OUTPUT_COLOR` | `white` | Color of command output |
| `INPUT_SPEED` | `0.05` | Delay in seconds between typed characters |
| `INPUT_SPEED_RANDOMNESS` | `false` | Enable random delays between characters |
| `INPUT_SPEED_MIN` | `0.01` | Minimum delay when randomness is enabled |
| `INPUT_SPEED_MAX` | `0.1` | Maximum delay when randomness is enabled |
| `INITIAL_WAIT` | `5` | Seconds to wait before starting |

### Instructions

The instruction stream is a flat sequence of directives, executed in order:

```
INPUT: command to run
OUTPUT:
This is the command output
Can span multiple lines
WAIT: 2
```

**Directives:**

- `INPUT:` - Types a command at the prompt (prompt is printed first)
- `OUTPUT:` (optional, multi-line) - Prints command output until the next directive line
- `WAIT:` - Pauses for the given number of seconds. If an `INPUT:` isn't followed by an
  explicit `WAIT:` before the next `INPUT:` (or end of file), a default 2s wait is inserted.
- `PROMPT:` - Sets the prompt text used for subsequent `INPUT:`s. **Sticks until changed
  again** (it's not reset per-command) — set it back to reproduce the global `PROMPT` if needed.
- `PROMPT_COLOR:` - Same, for prompt color.
- `TYPE_DELAY:` - Seconds to pause after printing the prompt, before typing starts, for
  subsequent `INPUT:`s. Sticks until changed.

Since `OUTPUT:` collects lines until it sees one of the directive keywords, a literal
output line that happens to start with `WAIT:`, `INPUT:`, `PROMPT:`, `PROMPT_COLOR:`,
or `TYPE_DELAY:` needs a backslash escape or it will be misread as a directive and end
the output early:

```
INPUT: cat status.txt
OUTPUT:
\WAIT: 30s remaining
Job still running
```

The leading `\` is stripped and the rest of the line is emitted as-is.

### Color Options

Available colors:

- `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`
- `bold`, `dim`, `italic`, `underline` (can be combined with colors)

Example with bold green:
```
PROMPT_COLOR: bold green
```

### Inline Colors in INPUT/OUTPUT

Wrap any part of `INPUT:` or `OUTPUT:` text in `{colorname}...{reset}` to change color mid-text.
Combos work too (`{bold red}`). `{reset}` or `{default}` reverts to that field's base color
(`INPUT_COLOR`/`OUTPUT_COLOR`). Unrecognized tags (e.g. `{foo}`) are left as literal text.
Tags don't carry across lines — close them before the line ends.

```
INPUT: rm -rf {red}important_folder{reset}
OUTPUT:
{green}Success:{reset} 12 files removed
{red}Error:{reset} permission denied on 2 files
WAIT: 2
```

To show a literal `{...}` (e.g. JSON, or a color-name word you don't want treated as markup),
escape the braces with `\{` and `\}`:

```
INPUT: curl -s api.example.com/status
OUTPUT:
\{"status": "red", "code": 200\}
WAIT: 2
```

## Usage Examples

### Basic Example

```
PROMPT: $
PROMPT_COLOR: green
INPUT_COLOR: cyan
INPUT_SPEED: 0.05
---
INPUT: echo "Hello World"
OUTPUT:
Hello World
WAIT: 2

INPUT: date
OUTPUT:
Wed Jul 08 12:34:56 PDT 2026
WAIT: 1
```

### Example with Randomness

```
PROMPT: $
PROMPT_COLOR: green
INPUT_COLOR: cyan
INPUT_SPEED_RANDOMNESS: true
INPUT_SPEED_MIN: 0.02
INPUT_SPEED_MAX: 0.08
---
INPUT: npm install
OUTPUT:
added 247 packages, and audited 248 packages in 3.5s
WAIT: 2
```

### Fast Typing

For quick demos, reduce input speed:

```bash
python mock_terminal.py demo.txt --speed 0.01
```

Or set in file:
```
INPUT_SPEED: 0.01
```

### Realistic Typing with Randomness

To make typing look more human-like with variable speeds:

```bash
python mock_terminal.py demo.txt --randomness --speed-min 0.01 --speed-max 0.1
```

Or set in file:
```
INPUT_SPEED_RANDOMNESS: true
INPUT_SPEED_MIN: 0.01
INPUT_SPEED_MAX: 0.1
```

This will randomly vary the delay between each character within the specified range, making the typing appear more natural and less mechanical.

### Custom Prompt

```
PROMPT: root@server:/var/www#
PROMPT_COLOR: red
```

### Changing the Prompt Mid-Session

`PROMPT:`/`PROMPT_COLOR:` change the running prompt for every `INPUT:` that follows,
until changed again — useful for simulating `su`, `ssh`, `docker exec`, venv activation,
etc. They do **not** auto-revert; switch back explicitly when the simulated session ends.

```
PROMPT: user@laptop:~ $
PROMPT_COLOR: cyan

INPUT: ssh admin@server
OUTPUT:
Welcome to server
WAIT: 1

PROMPT: admin@server:~#
PROMPT_COLOR: red
INPUT: whoami
OUTPUT:
admin
WAIT: 2

PROMPT: user@laptop:~ $
PROMPT_COLOR: cyan
INPUT: exit
OUTPUT:
logout
WAIT: 1
```

Without that last `PROMPT:`/`PROMPT_COLOR:` reset, `exit` would still show at the
`admin@server:~#` prompt.

### Multi-line Output

Output automatically handles multiple lines:

```
---
INPUT: ls -la
OUTPUT:
total 48
drwxr-xr-x  5 user staff 160 Jul  8 12:34 .
-rw-r--r--  1 user staff 1234 Jul  8 12:30 file.txt
WAIT: 2
```

## Command Line Options

```
usage: mock_terminal.py [-h] [--wait SECONDS] [--no-clear] [--speed SPEED] 
                        [--randomness] [--speed-min MIN] [--speed-max MAX] input_file

Options:
  -h, --help            Show this help message
  --wait SECONDS        Override initial wait time
  --no-clear            Don't clear screen at start
  --speed SPEED         Override typing speed (seconds per character)
  --randomness          Enable random typing speed
  --speed-min MIN       Minimum delay between characters when randomness enabled
  --speed-max MAX       Maximum delay between characters when randomness enabled
```

### Examples

```bash
# Use default settings from file
python mock_terminal.py demo.txt

# Start immediately (no countdown)
python mock_terminal.py demo.txt --wait 0

# Fast typing (0.01 sec per character)
python mock_terminal.py demo.txt --speed 0.01

# Random typing speed for natural appearance
python mock_terminal.py demo.txt --randomness --speed-min 0.01 --speed-max 0.1

# Don't clear screen, append to current view
python mock_terminal.py demo.txt --no-clear

# Combination: random typing, custom wait, no clear
python mock_terminal.py demo.txt --wait 2 --randomness --speed-min 0.02 --speed-max 0.08 --no-clear
```

## Tips and Tricks

### Recording Terminal Sessions

To record the output for video tutorials:

```bash
# Using asciinema
asciinema rec demo.cast
python mock_terminal.py demo.txt

# Using script command
script demo.log
python mock_terminal.py demo.txt
exit
```

### Creating a Presentation Script

Build sequences for different steps:

```
# step1.txt - Setup phase
PROMPT: $
INPUT_SPEED: 0.02
---
INPUT: git clone repo
OUTPUT:
Cloning...
Done!
WAIT: 2

# step2.txt - Execution phase
PROMPT: $
INPUT_SPEED: 0.02
---
INPUT: npm install
OUTPUT:
...lots of output...
WAIT: 2
```

### Long Running Commands

For commands that appear to take time, use `WAIT`:

```
---
INPUT: npm build
OUTPUT:
Building...
Compiling TypeScript...
Running tests...
Done! Output in dist/
WAIT: 5
```

### Comments in Input Files

Use `#` for comments:

```
# This is a comment
PROMPT: $  # Inline comment

---
# Start with a simple command
INPUT: pwd
OUTPUT:
/home/user
```

## Troubleshooting

### Colors not showing

Make sure your terminal supports ANSI colors. On Windows, use Windows Terminal or enable ANSI escape codes.

### Typing too fast/slow

Adjust `INPUT_SPEED`:
- Increase for slower (e.g., `0.1`)
- Decrease for faster (e.g., `0.01`)

### Output not displaying correctly

Check for missing colons in the input file. Each field must have `FIELD:` format.

### Output cuts off early on a line like `WAIT: ...` or `INPUT: ...`

`OUTPUT:` collection ends at any line starting with a directive keyword. If the output
text itself needs to start with one of those keywords, escape it: `\WAIT: ...`.

### Prompt appears twice

Make sure `INPUT:` values don't already contain the prompt text.

## Examples Included

- `examples/dashboard/session.terminal.txt` - Basic demonstration with various commands

## License

Free to use and modify for any purpose.

