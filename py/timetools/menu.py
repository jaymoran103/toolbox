"""The menu `tt` shows with no arguments: presets first, then the tools."""

from timetools import runner, spec, term

TOOL_LINES = {
    "stopwatch": "stopwatch",
    "timer": "timer 5m",
    "metronome": "metronome 120",
    "counter": "counter",
    "fireworks": "fireworks 30s -r 2/s --view big",
}


def entries():
    items = []
    for name, (block, path) in runner.presets().items():
        first = block["steps"][0] if block["steps"] else {"tool": "wait"}
        items.append((name, "%d steps · %s" % (len(spec.expand(block)), spec.describe(first)), block))
    for tool, line in TOOL_LINES.items():
        items.append((tool, spec.TOOLS[tool]["help"], spec.parse_text(line)[0]))
    return items


def run():
    items = entries()
    pick = 0
    width = max(len(name) for name, _, _ in items)
    with term.Keys() as keys:
        while True:
            lines = ["timetools · ↑↓ or j/k move · enter run · q quit", ""]
            for i, (name, note, _) in enumerate(items):
                mark = "›" if i == pick else " "
                lines.append("%s %-*s  %s" % (mark, width, name, note))
            print("\x1b[H\x1b[2J" + "\r\n".join(lines), end="", flush=True)
            key = keys.read()
            if key in ("up", "k"):
                pick = (pick - 1) % len(items)
            elif key in ("down", "j"):
                pick = (pick + 1) % len(items)
            elif key in ("q", "esc"):
                print("\x1b[H\x1b[2J", end="")
                return 0
            elif key == "enter":
                break
    print("\x1b[H\x1b[2J", end="", flush=True)
    block = items[pick][2]
    results, quit = runner.run_block(block)
    if block["score"]:
        print(runner.scorecard_text(runner.score(results, block["score"])))
    return 0
