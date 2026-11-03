#!/bin/sh
# Link tt and one command per tool into ~/.local/bin, and the example
# presets into ~/.config/timetools. Safe to re-run. Needs only python3 3.9+.
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN="${BIN:-$HOME/.local/bin}"
PRESETS="${XDG_CONFIG_HOME:-$HOME/.config}/timetools"
mkdir -p "$BIN" "$PRESETS"

link() {
  if [ -e "$2" ] && [ ! -L "$2" ]; then
    echo "skip $2: a real file is there"
  else
    ln -sfn "$1" "$2" && echo "linked $2"
  fi
}

for name in tt stopwatch timer metronome counter fireworks; do
  link "$ROOT/bin/tt" "$BIN/$name"
done
link "$ROOT/presets/examples.tt" "$PRESETS/examples.tt"

case ":$PATH:" in *":$BIN:"*) ;; *) echo "add $BIN to PATH to use these commands" ;; esac
