# The preset kit

`lib/preset_kit.py` is the shared frame for a tool that keeps named presets for one thing and lets you pick one. A preset says which elements show, in what order, and the value of each setting. Every tool on the kit has the same command line, files and keys. Four tools are built on it. `claude-statusline` and `starship-preset` pick which stats and prompt modules show. `ghostty-config` and `terminal-config` set Ghostty's and macOS Terminal's look and feel.

## What a tool supplies

A tool is one script that subclasses `Tool`. It sets four fields and writes `render()`:

```python
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from preset_kit import Element, Tool, main

class Prompt(Tool):
    name = "my-prompt"                       # the command, and the config and state dir names
    title = "what my prompt shows"           # a few words for the header
    elements = (
        Element("dir", "directory"),         # kind "show": in or out, and ordered
        Element("git", "git branch"),
        Element("sep", "separator", kind="choice", choices=(" | ", " · ")),
    )
    builtins = {"default": {"show": ["dir", "git"]}}

    def render(self, preset, width):         # lines for the preview pane, ANSI is fine
        return [" ".join(preset["show"])]

    def value(self, key):                    # optional: a live reading beside each element
        return ""

if __name__ == "__main__":
    main(Prompt(), sys.argv[1:])
```

The tool's runtime reads `tool.active_preset()`. It gets `{"show": [keys], "set": {key: value}}`, cleaned of keys the tool no longer has.

## Elements

| kind | holds | editor keys |
| --- | --- | --- |
| `show` | in or out, and a place in the order | `space` show or hide, `⇧↑↓` reorder |
| `choice` | one of `choices`, a tuple or a callable | `←→` cycle; `enter` opens a filtered list past 7 options |
| `number` | `lo` to `hi` in steps of `step` | `←→` step, `⇧←→` 10 steps, `enter` type |
| `color` | a `#rrggbb` hex | `enter` opens `color-pick`, `#` types a hex |
| `text` | free text | `enter` type |

| option | effect |
| --- | --- |
| `group` | files the element under a folding heading |
| `optional` | the setting can be unset with `x`, and the tool leaves it out |
| `default` | the value when not optional, and where a number starts stepping |
| `actions` | `{key: (label, fn)}`. `fn(tool, value)` runs with the terminal handed over, and returns a new value or `None` |

## Hooks

All optional. The kit calls them, and a tool overrides the ones it needs.

| hook | called | used by `ghostty-config` to |
| --- | --- | --- |
| `value(key)` | beside each element | show what an unset setting falls back to |
| `live(preset)` | on hover and on each change | repaint the window in the preset's colours |
| `restore()` | when the picker closes | put the window's colours back |
| `applied(name, preset)` | when a preset goes into use, or the one in use is edited | write the config fragment |

## Colour

`BG(hex)` and `FG(hex)` give a tool's `render()` its colours. They draw in full colour when `COLORTERM` says the terminal has it, and as the nearest xterm-256 colour otherwise, matched as `color-pick` matches. `PRESET_KIT_COLOURS=full` or `256` overrides the guess. Older macOS Terminal has no full colour, so a tool that draws with these still reads right there.

`pickup` is what the footer says when a preset goes into use. `list_shows = False` drops the list of shown elements under the preview.

## What every tool gets

| | |
| --- | --- |
| `tool` | the picker and editor, in a terminal |
| `tool <preset>` | use a preset |
| `tool -l` | list presets, `•` on the one in use |
| `tool -s` | the preset in use, and where it comes from |
| `tool -r` | back to the default |
| `tool --print [p]` | draw a preset, or the one in use |
| `tool --save NAME` | keep the preset in use as NAME |
| exit code | 0 done, 1 unknown preset or bad name, 2 usage error |

## Files

| | |
| --- | --- |
| built-ins | in the script, as `builtins` |
| yours | `presets/<tool>/<preset>.json`, linked to `~/.config/<tool>/presets` by `install.sh` |
| the pick | `~/.local/state/<tool>/active`, one name; no file means the default |

A preset of yours with a built-in's name hides it, and the list calls it `changed`. Deleting it brings the built-in back. `<TOOL>_PRESETS_DIR` and `XDG_STATE_HOME` move the files, for tests.

## Keys

Three screens. The preset list draws the hovered preset on the right. The editor lists every element, shown ones first in order, under folding group headings when the tool has groups. A long choice opens a list you filter by typing, and the preview follows the hovered option. Edits save as you make them, so `esc` only goes back. Undo all and delete are armed: `⌫` once says what goes, and `⌫` again does it.

| list | | editor | |
| --- | --- | --- | --- |
| `enter` | use it | `space` | show or hide |
| `e` `→` | edit | `←→` | change a setting |
| `n` | new from this | `⇧↑↓` `K` `J` | reorder |
| `⌫ ⌫` | delete yours | `z` `y` | undo, redo |
| `q` `esc` | quit | `⌫ ⌫` | undo all |
| `?` | keys | `esc` `←` | back |
| | | `x` | unset |
| | | `-` `+` | fold all, open all |

## The worked example: claude-statusline

Claude Code pipes session JSON into `bin/claude-statusline`, and it prints one line from the preset in use. Run by hand in a terminal, the same script opens the picker. Each run keeps its input in `~/.local/state/claude-statusline/sample.json`, so the preview uses your last session's numbers. A pick reaches running sessions on their next refresh.

Its elements are segment functions in a dict, `SEGMENTS`. A new stat is one function and one `Element` line. `ATTACH` joins a segment to the one before with a space, and `APART` sets one off with a wide gap.

## The worked example: ghostty-config

`bin/ghostty-config` is one tool for all of Ghostty. A preset is a config fragment. About 30 settings sit in six groups: Theme, Font, Window, Cursor, Mouse and clipboard, and Keys. Each element's key is the Ghostty option's own name, so the fragment is one `key = value` line per set element. Every setting is optional, and an unset one keeps your config's value.

`applied()` writes the fragment to `~/.local/state/ghostty-config/active.conf`. On first use it adds one line to your Ghostty config, `config-file = ?<that path>`. New windows take a pick, and `⌘⇧,` reloads open ones.

The theme is a `choice` whose options come from a callable: your themes, then Ghostty's. Its `c` action opens `ghostty-theme-edit` on the theme, so the colour tree is reused, not rebuilt. `live()` repaints the window with OSC colour codes as you move through themes and colours.

`GHOSTTY_CONFIG`, `GHOSTTY_THEMES_DIR`, `GHOSTTY_CONFIG_PRESETS_DIR` and `XDG_STATE_HOME` point it at copies, for tests.

## A third example: terminal-config

`bin/terminal-config` does for macOS Terminal what `ghostty-config` does for Ghostty, with the settings Terminal's AppleScript can reach. A preset names a base profile plus changes. With no changes, `applied()` switches to the base profile. With changes, it builds a profile called `toolbox` from the base and the changes. Either way Terminal's default profile, its startup profile and every open tab move to it. AppleScript can't copy a profile's ANSI colours, so `toolbox` keeps Terminal's stock palette. `default` goes back to the profile Terminal used before the tool first ran.

## A fourth example: starship-preset

`bin/starship-preset` picks which Starship modules show, as `show` elements, over a base config: your own, none, or one of Starship's built-in presets. Each built-in becomes a kit preset of its own. `applied()` writes the base with a new top-level `format` to `~/.local/state/starship-preset/active.toml`, and a zsh hook points `STARSHIP_CONFIG` at it before every prompt. With `-H`, the tool overrides `active()` and `set_active()` to keep the pick for one project instead.
