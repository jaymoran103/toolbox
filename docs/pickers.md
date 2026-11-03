# The colour pickers

Two terminal pickers, each one script you can run raw or as a TUI. Any program can call them.

| Tool | Picks | Reach for it when |
| --- | --- | --- |
| `color-pick` | one colour | a single colour, from a grid, sliders or swatches |
| `hue-pick` | a family of shades per hue, from a fixed list of hues | categories that must stay apart, in a 256-colour TUI or in full colour |

`hue-pick` replaced `palette-pick`, which is removed.

## Two ways to run them

**Raw.** `--print` builds the result from the options and prints it. There is no screen and no keys, so a script, Makefile or test can use it.

```sh
hue-pick --print --hues red,teal,violet -x -f hex
#870000 #af0000 #d70000 #ff5f5f #ff8787
#005f5f #008787 #00afaf #00d7d7 #00ffff
#5f00af #8700d7 #875fff #af87ff #d7afff
```

**TUI.** Without `--print`, the picker draws on `/dev/tty` and the answer goes to stdout, so `x=$(hue-pick)` works from a shell or another program.

## What every picker shares

| | |
| --- | --- |
| stdout | the result: JSON by default, or `-f hex` (a family a line) or `-f css` |
| exit code | 0 picked, 1 cancelled (Esc or q), 2 usage error, with the message on stderr |
| `-o FILE` | also writes the full JSON to FILE on every change, so a caller can preview live. A cancel writes the starting state back. |
| `--split`, `--tab` | runs the picker in a Ghostty split or tab, and the calling process waits for the answer |
| `--nested` | the caller already holds the alternate screen, as inside a curses app |
| `-t TEXT` | says what is being picked, on the top line |
| state | the last pick, in `~/.local/state/<tool>/last.json`. Options on the command line override it. |

## hue-pick

The hues live in `config/hue-pick/hues.json`, or in `~/.config/hue-pick/hues.json` if that file exists. Each hue is a family:

```json
{"name": "teal", "hue": 195, "light": [44, 90],
 "xterm": ["#005f5f", "#008787", "#00afaf", "#00d7d7", "#00ffff"]}
```

- **`-x` xterm-256 mode.** The five `xterm` colours were chosen by hand, darkest first, and they are the truth in this mode. With `-s N` under 5, the family takes an even spread of the five.
- **`--full` mode.** Each hue steps through its own `light` range at one `--strength`, in OKLCH, so step k of every hue is equally light.
- **Adding a hue.** Add an entry, then run `hue-pick check`. It exits 1 on a bad entry, lists the closest pairs, and `--html FILE` draws a sheet of every hue in both modes.
- **Output (`--print`, or Enter in the TUI).** `{"families": [[hex…]…], "palette": [hex…], "hues": [name…], "mode", "steps", "strength", "xterm", "verdict"}`.

### `--assign`: a hue for each of a caller's groups

This is for a caller with named groups, such as projects and their tabs. Each group gets one hue, and groups may share a hue. The input is the JSON itself, or `-` for stdin, or `@file`:

```json
{"groups": [{"key": "eng", "label": "engineering", "hue": "red", "step": null, "n": 6,
             "items": [null, 4, null, null, null, null]},
            {"key": "ops", "hue": "orange", "n": 1}],
 "steps": 3}
```

| field | meaning |
| --- | --- |
| `key` | the caller's id for the group |
| `label` | what the picker shows |
| `hue` | the starting hue, by name |
| `step` | the group's own step, 0-4, or `null` for auto |
| `n` | how many items the group has |
| `items` | a step per item by rank, `null` for auto |
| `steps` | how many shades items take |

The output gives the caller everything it draws, so it does no colour maths of its own:

```json
{"assign": {"eng": "red", "ops": "orange"}, "step": {"eng": 2, "ops": 2}, "fixed": {},
 "steps": 3, "mode": "xterm", "hues": ["red", "orange"], "families": [["#870000", "…"], ["#af5f00", "…"]],
 "item_steps": {"eng": [2, 4, 1, 2, 3, 1], "ops": [2]},
 "colours": {"eng": ["#d70000", "#d70000", "#ff8787", "#af0000", "#d70000", "#ff5f5f", "#af0000"],
             "ops": ["#ff8700", "#ff8700"]},
 "neighbours": [["eng", "ops", "red", "orange"]]}
```

`colours[key]` is the group's colour, then each item's by rank. `neighbours` lists neighbouring hues on adjacent groups. It's a warning, never a block. The rules live in `lib/hue_rules.py`: the first group on a hue takes the middle step, groups sharing a hue take steps middle out, and items step outward from their group. Python callers can load that file from beside `hue-pick`, as `bin/../lib/hue_rules.py`, so they draw exactly what the picker shows. Its API is `load_hues`, `ITEM_ORDER`, `group_steps`, `item_steps`, `item_colours`, `by_step`, `neighbours` and `nearest`.

In the TUI, a long list of groups scrolls, and PgUp and PgDn jump by ten.

## Calling a picker from a TUI

This is the pattern any program can follow to use `hue-pick --assign`:

```python
import json, os, shutil, subprocess, sys, tempfile, time

def pick(groups, live):
    """Open hue-pick in a split. live(colours) is called on every change."""
    out = os.path.join(tempfile.mkdtemp(), "live")
    proc = subprocess.Popen([sys.executable, shutil.which("hue-pick"), "--assign", json.dumps({"groups": groups}),
                             "-t", "my app: colours", "--split", "-o", out],
                            stdout=subprocess.PIPE, text=True)
    seen = None
    while proc.poll() is None:                    # in a real TUI: on each tick of your loop
        try: now = open(out).read()
        except OSError: now = None
        if now and now != seen:
            seen = now; live(json.loads(now)["colours"])
        time.sleep(0.15)
    answer = proc.stdout.read()
    return json.loads(answer) if proc.returncode == 0 else None   # None: cancelled, revert
```

Outside Ghostty, end curses, run the picker in the same terminal without `--split`, and redraw when it returns. To reopen a picker on the last answer, save the answer and pass it back: `--hues`, `-s`, or the groups' `hue` and `step`.

## Where things are

```
bin/color-pick  bin/hue-pick
lib/hue_rules.py                 the --assign rules, shared with callers
config/hue-pick/hues.json        the hues
docs/pickers.md                  this file
```

`hue-pick` needs `lib/` beside `bin/`.
