"""Run steps and blocks: one tool, a preset, or a whole file.

The runner owns everything between steps: repeats, gaps, waiting for a key,
moving next and back, and the scorecard. Each tool only runs itself.
"""

import glob
import json
import os
import subprocess
import sys
import time

from timetools import counter, fireworks, metronome, spec, stopwatch, term, timer, views
from timetools.durations import fmt

TOOLS = {"stopwatch": stopwatch, "timer": timer, "wait": timer, "metronome": metronome,
         "counter": counter, "fireworks": fireworks}
STYLE_KEYS = ("palette", "colors", "children", "trail", "length", "size", "gravity", "crackle", "rocket")
PRESET_DIRS = ("~/.config/timetools",)


def config(step):
    """A parsed step plus its tool's defaults."""
    cfg = dict(spec.DEFAULTS[step["tool"]], label="", view=None)
    cfg.update(step)
    return cfg


def check(cfg):
    """Errors a parser can't see, such as a zero-length timer."""
    for key in ("duration", "for", "cap", "within"):
        value = cfg.get(key)
        if isinstance(value, float) and value <= 0:
            return "--%s must be more than zero" % key
    if cfg["tool"] == "metronome" and not metronome.MIN_BPM <= cfg["bpm"] <= metronome.MAX_BPM:
        return "bpm must be between %d and %d" % (metronome.MIN_BPM, metronome.MAX_BPM)
    if cfg["tool"] == "fireworks":
        if cfg["span"] != "forever" and cfg["span"][0] <= 0:
            return "span must be more than zero"
        if (cfg["count"] or [1])[0] < 1 or (cfg["rate"] or [1])[0] <= 0:
            return "count and rate must be more than zero"
    return None


def run_step(step, view_name=None, hooks=None, where=None):
    cfg = config(step)
    problem = check(cfg)
    if problem:
        raise spec.ParseError("%s: %s" % (cfg["tool"], problem))
    style = {k: cfg[k] for k in STYLE_KEYS if k in step}
    if hooks and hooks.out is sys.stdout:
        view_name = "none"  # stdout carries the JSON lines, so draw nothing
    view = views.load(cfg["view"] or view_name, style)
    if hooks:
        view = hooks.wrap(view, cfg, where)
    return TOOLS[cfg["tool"]].run(cfg, view)


def run_block(block, view_name=None, hooks=None, start=1):
    """Run a block's steps in order. Returns (results, quit)."""
    steps = spec.expand(block)
    results = {}
    i = max(0, start - 1)
    first = True
    while 0 <= i < len(steps):
        step = steps[i]
        if not first:
            moved = between(block, step, view_name, hooks)
            if moved == "quit":
                return ordered(results), True
            if moved == "back":
                i = max(0, i - 1)
                continue
        where = {"block": block["name"], "step": i + 1, "of": len(steps)}
        if hooks:
            hooks.send("step", dict(where, label=step.get("label") or spec.describe(step), tool=step["tool"]))
        result = run_step(step, view_name, hooks, where)
        first = False
        results[i] = result
        if result["nav"] == "quit":
            return ordered(results), True
        i = max(0, i - 1) if result["nav"] == "back" else i + 1
    return ordered(results), False


def ordered(results):
    return [results[k] for k in sorted(results)]


def between(block, step, view_name, hooks=None):
    """The pause before a step: a gap, or a wait for a key."""
    label = step.get("label") or spec.describe(step)
    if block["advance"] == "key":
        if hooks:
            hooks.send("ready", {"block": block["name"], "next": label})
        with term.Keys() as keys:
            if not keys.interactive:
                return None
            term.status("next: %s  · space or enter to start · b back · q quit" % label)
            while True:
                key = keys.read()
                if key in ("space", "enter", "n"):
                    term.status("")
                    return None
                if key in ("b", "q", "esc"):
                    term.status("")
                    return term.NAV[key]
    if block["gap"]:
        result = run_step({"tool": "wait", "duration": block["gap"], "label": "next: %s" % label}, view_name)
        return result["nav"]
    return None


def score(results, kind):
    """Scorecard for the stopwatch steps. A capped solve is DNF. The WCA
    average drops the best and worst; two DNFs make the average DNF."""
    solves = [r for r in results if r["tool"] == "stopwatch"]
    times = [None if r["outcome"] == "dnf" else r["elapsed"] for r in solves]
    done = sorted(t for t in times if t is not None)
    card = {"kind": kind, "solves": [{"label": r["label"], "time": t} for r, t in zip(solves, times)],
            "best": done[0] if done else None, "worst": None if None in times else (done[-1] if done else None),
            "mean": sum(done) / len(done) if done else None}
    if kind == "wca" and len(times) >= 3:
        dnfs = times.count(None)
        if dnfs > 1:
            card["average"] = None
        else:
            ranked = done + [float("inf")] * dnfs
            middle = ranked[1:-1]
            card["average"] = sum(middle) / len(middle)
    return card


def scorecard_text(card):
    show = lambda t: "DNF" if t is None else fmt(t, 2)
    lines = ["%-20s %s" % (s["label"] or "solve %d" % i, show(s["time"])) for i, s in enumerate(card["solves"], 1)]
    lines.append("%-20s %s" % ("best", show(card["best"])))
    lines.append("%-20s %s" % ("mean", show(card["mean"])))
    if "average" in card:
        lines.append("%-20s %s" % ("average (WCA)", show(card["average"])))
    return "\n".join(lines)


# presets

def preset_files(extra=()):
    files = []
    for d in tuple(extra) + (os.getcwd(),) + PRESET_DIRS:
        files += sorted(glob.glob(os.path.join(os.path.expanduser(d), "*.tt")))
    return files


def presets(extra=()):
    """name -> (block, file). A preset in the current folder wins."""
    found = {}
    for path in preset_files(extra):
        try:
            blocks = spec.parse_text(open(path).read())
        except (OSError, spec.ParseError) as e:
            sys.stderr.write("skipping %s: %s\n" % (path, e))
            continue
        for block in blocks:
            if block["name"] and block["name"] not in found:
                found[block["name"]] = (block, path)
    return found


def resolve(target):
    """A preset name, a file (optionally file.tt:name), '-' for stdin, or
    inline text -> list of blocks."""
    if target == "-":
        return spec.parse_text(sys.stdin.read())
    path, _, name = target.partition(":") if target.count(":") == 1 and ".tt:" in target else (target, "", "")
    if path.endswith(".tt") or os.path.isfile(path):
        blocks = spec.parse_text(open(os.path.expanduser(path)).read())
        if name:
            blocks = [b for b in blocks if b["name"] == name]
            if not blocks:
                raise spec.ParseError("no preset [%s] in %s" % (name, path))
        return blocks
    found = presets()
    if target in found:
        return [found[target][0]]
    if " " not in target.strip() and ";" not in target and target not in spec.TOOLS and target not in spec.ALIASES:
        raise spec.ParseError("no preset named %r (see 'tt presets')" % target)
    return spec.parse_text(target)


# hooks: --emit, --on, --out

class Hooks:
    """Writes events as JSON lines and runs commands on them."""

    def __init__(self, emit=None, on=()):
        self.out = None
        if emit == "-":
            self.out = sys.stdout
        elif emit:
            self.out = open(emit, "a")
        self.on = {}
        for item in on:
            event, _, command = item.partition("=")
            self.on.setdefault(event, []).append(command)

    def __bool__(self):
        return bool(self.out or self.on)

    def send(self, event, data):
        record = dict(data, event=event, time=time.time())
        line = json.dumps(record, default=str)
        if self.out:
            self.out.write(line + "\n")
            self.out.flush()
        for command in self.on.get(event, []) + self.on.get("*", []):
            env = dict(os.environ, TT_EVENT=event, TT_JSON=line)
            subprocess.Popen(command, shell=True, env=env, stdin=subprocess.DEVNULL)

    def wrap(self, view, cfg, where):
        return Hooked(view, self, cfg, where or {})


SAFE = (int, float, str, bool, type(None))


def public(state):
    return {k: v for k, v in vars(state).items() if isinstance(v, SAFE) and k != "now"}


class Hooked:
    """A view wrapper that reports open, events and close to Hooks."""

    def __init__(self, view, hooks, cfg, where):
        self._view, self._hooks = view, hooks
        self._base = dict(where, tool=cfg["tool"], label=cfg["label"])

    def open(self, tool, help):
        self._hooks.send("start", self._base)
        return self._view.open(tool, help)

    def frame(self, state):
        return self._view.frame(state)

    def next_frame(self, state):
        return self._view.next_frame(state)

    def event(self, name, state):
        self._hooks.send(name, dict(self._base, **public(state)))
        return self._view.event(name, state)

    def close(self, state):
        result = self._view.close(state)
        self._hooks.send("done", dict(self._base, **public(state)))
        return result

    def abort(self):
        return self._view.abort()
