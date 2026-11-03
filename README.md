# toolbox

Terminal tools built on shared templates. Clone it, run `./install.sh`, and each tool lands on your PATH.

```sh
git clone https://github.com/jaymoran103/toolbox.git ~/.toolbox
~/.toolbox/install.sh --list      # each tool and what it needs
~/.toolbox/install.sh             # link them all
```

## Templates plus implementations

A template lives in `lib/` and its contract in `docs/`. Each tool is one script in `bin/`, built on one template.

| template | for | contract |
| --- | --- | --- |
| preset kit, `lib/preset_kit.py` | config tools: presets you preview, edit, save and switch | `docs/preset-kit.md` |
| picker contract | pickers: one result, raw or from a TUI | `docs/pickers.md` |

`tt` lives whole in `tools/tt/`, as a git subtree of its own repo. Update it with `git subtree pull --prefix=tools/tt https://github.com/jaymoran103/timetools.git main --squash`.

`ghostty-config` is the model tool. Read it beside `docs/preset-kit.md` before writing a new one.

## Layout

```
bin/                  one script per tool, linked onto PATH
lib/                  the templates
docs/                 their contracts
tools/<tool>/         tool.json, the manifest install.sh reads, and any support files
presets/<tool>/       your presets, linked to ~/.config/<tool>/presets
config/               data a tool ships with
```

`main` is the starter kit, with built-in presets only. Keep your own presets and changes on a branch of your own, and merge `main` into it to update.

Everything runs on `python3` from the standard library, 3.9 or later. A tool that needs more says so in its manifest.
