"""preset_kit — the shared frame for a preset picker and editor.

A tool built on the kit keeps named presets for one thing, such as a
status line, a prompt or a terminal's config. A preset says which elements
show, in what order, and the value of each setting. The kit gives every
tool the same command line, the same files and the same keys. A tool
supplies its elements, its built-in presets and a render function, plus
any of four optional hooks.

docs/preset-kit.md has the contract and two worked examples.
"""

import json
import os
import re
import select
import shutil
import subprocess
import sys
import termios
import tty

HOME = os.path.expanduser("~")
BOLD, DIM, REV = "\x1b[1m", "\x1b[2m", "\x1b[7m"
RED, GREEN, YELLOW = "\x1b[31m", "\x1b[32m", "\x1b[33m"
MIN_W, MIN_H = 64, 16
MAX_W, MAX_H = 120, 40   # a bigger window centres the frame, not stretch it
HEX = re.compile(r"#[0-9a-fA-F]{6}")
LIST_AT = 7              # a choice with more options than this opens a list


def BG(h):
    return "\x1b[48;2;%d;%d;%dm" % tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def FG(h):
    return "\x1b[38;2;%d;%d;%dm" % tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


# --- what a tool supplies ---------------------------------------------------

class Element:
    """One thing a preset can show or set.

    kind "show"    in or out of the preset, and takes a place in its order.
    kind "choice"  one of `choices`. A callable gives them when asked.
    kind "number"  from `lo` to `hi` in steps of `step`.
    kind "color"   a #rrggbb hex, picked with color-pick.
    kind "text"    free text, typed.

    A setting is unset when `optional`, and the tool then leaves it out.
    Otherwise it falls back to `default`, or a choice's first option.
    `group` files the element under a folding heading in the editor.
    `actions` maps a key to (label, fn). fn(tool, value) runs with the
    terminal handed over, and returns a new value or None for no change.
    """

    def __init__(self, key, label, kind="show", choices=(), group="", optional=False,
                 default=None, lo=0, hi=100, step=1, note="", actions=None):
        self.key, self.label, self.kind, self.group = key, label, kind, group
        self.choices, self.optional, self.default = choices, optional, default
        self.lo, self.hi, self.step, self.note = lo, hi, step, note
        self.actions = actions or {}

    def options(self):
        return list(self.choices() if callable(self.choices) else self.choices)

    def fallback(self):
        if self.optional:
            return None
        if self.default is not None or self.kind != "choice":
            return self.default
        return self.options()[0]

    def valid(self, v):
        if v is None:
            return False
        if self.kind == "choice":
            # Long lists are asked for only when a list opens, not on load.
            return callable(self.choices) or v in self.choices
        if self.kind == "number":
            return isinstance(v, (int, float)) and self.lo <= v <= self.hi
        if self.kind == "color":
            return isinstance(v, str) and bool(HEX.fullmatch(v))
        return isinstance(v, str)

    def number(self, v):
        v = max(self.lo, min(self.hi, round(v / self.step) * self.step))
        return int(v) if float(self.step).is_integer() else round(v, 4)


class Tool:
    """Subclass this. Set the class fields and write render()."""

    name = ""            # the command; also names the config and state dirs
    title = ""           # a few words for the header
    elements = ()        # Elements, in the order the editor lists them
    builtins = {}        # preset name -> {"show": [keys], "set": {key: value}}
    default = "default"  # the built-in used when nothing is picked
    pickup = "new sessions pick it up"   # said when a preset goes into use
    list_shows = True    # list what a hovered preset shows under its preview

    def render(self, preset, width):
        """Lines that show what the preset looks like. ANSI SGR is fine."""
        raise NotImplementedError

    # --- optional hooks -------------------------------------------------------

    def value(self, key):
        """Text beside an element in the editor: a live reading, or what an
        unset setting falls back to. Empty by default."""
        return ""

    def live(self, preset):
        """Show the preset for real while it is on screen, if the tool can.
        Called on hover and on every change."""

    def restore(self):
        """Undo whatever live() did. Called when the picker closes."""

    def applied(self, name, preset):
        """The preset in use changed, or the one in use was edited. A tool
        whose target cannot read the pick at run time writes it out here."""

    # --- files ----------------------------------------------------------------
    # Presets of yours: ~/.config/<name>/presets/<preset>.json, which
    # install.sh links to the toolbox's presets/<name>/. The pick:
    # ~/.local/state/<name>/active.

    @property
    def presets_dir(self):
        env = self.name.upper().replace("-", "_") + "_PRESETS_DIR"
        return os.environ.get(env) or os.path.join(HOME, ".config", self.name, "presets")

    @property
    def state_dir(self):
        base = os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local", "state")
        return os.path.join(base, self.name)

    def path(self, name):
        return os.path.join(self.presets_dir, name + ".json")

    def yours(self):
        try:
            files = os.listdir(self.presets_dir)
        except OSError:
            return []
        return sorted(f[:-5] for f in files if f.endswith(".json") and not f.startswith("."))

    def listing(self):
        """(name, source) pairs. Built-ins first, in their own order. A preset
        of yours with a built-in's name hides it, and its source is
        "changed"."""
        mine = self.yours()
        out = [(n, "changed" if n in mine else "built-in") for n in self.builtins]
        return out + [(n, "yours") for n in mine if n not in self.builtins]

    def source(self, name):
        return dict(self.listing()).get(name)

    def element(self, key):
        return next(e for e in self.elements if e.key == key)

    def load(self, name):
        try:
            with open(self.path(name)) as f:
                return self.clean(json.load(f))
        except (OSError, ValueError):
            pass
        if name in self.builtins:
            return self.clean(self.builtins[name])
        return None

    def clean(self, preset):
        """Drop keys the tool no longer has and settle every setting, so an
        old file still loads after the tool changes."""
        kinds = {e.key: e for e in self.elements}
        show = [k for k in preset.get("show", []) if k in kinds and kinds[k].kind == "show"]
        sets = dict(preset.get("set", {}))
        out = {}
        for e in self.elements:
            if e.kind != "show":
                v = sets.get(e.key)
                out[e.key] = v if e.valid(v) else e.fallback()
        return {"show": list(dict.fromkeys(show)), "set": out}

    def save(self, name, preset):
        clean = self.clean(preset)
        clean["set"] = {k: v for k, v in clean["set"].items() if v is not None}
        os.makedirs(self.presets_dir, exist_ok=True)
        tmp = self.path(name) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(clean, f, indent=2)
            f.write("\n")
        os.replace(tmp, self.path(name))

    def delete(self, name):
        try:
            os.remove(self.path(name))
        except OSError:
            pass

    def active(self):
        try:
            with open(os.path.join(self.state_dir, "active")) as f:
                name = f.read().strip()
        except OSError:
            name = ""
        return name if self.source(name) else self.default

    def set_active(self, name):
        os.makedirs(self.state_dir, exist_ok=True)
        pick = os.path.join(self.state_dir, "active")
        if name == self.default:
            try:
                os.remove(pick)
            except OSError:
                pass
        else:
            with open(pick, "w") as f:
                f.write(name + "\n")
        self.applied(name, self.load(name))

    def active_preset(self):
        return self.load(self.active()) or self.clean(self.builtins[self.default])


def sibling(name):
    """Another tool's command: beside the running script, else on PATH."""
    here = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), name)
    return here if os.access(here, os.X_OK) else shutil.which(name)


# --- the command line ---------------------------------------------------------

USAGE = """\
  {n}               picker and editor
  {n} <preset>      use <preset>
  {n} -l            list presets
  {n} -s            say which preset is in use
  {n} -r            go back to {d}
  {n} --print [p]   draw a preset, or the one in use
  {n} --save NAME   keep the preset in use as NAME"""


def main(tool, argv):
    """Exit 0 done, 1 unknown preset or bad name, 2 usage error."""
    def die(msg, code=1):
        sys.stderr.write(f"{tool.name}: {msg}\n")
        sys.exit(code)

    a = argv[0] if argv else None
    if a in ("-h", "--help"):
        print(f"{tool.name} — {tool.title}\n\n" + USAGE.format(n=tool.name, d=tool.default))
    elif a in ("-l", "--list"):
        on = tool.active()
        for name, src in tool.listing():
            print(f"{'•' if name == on else ' '} {name:<20} {src}")
    elif a in ("-s", "--status"):
        print(f"{tool.active()} · {tool.source(tool.active())}")
    elif a in ("-r", "--reset"):
        tool.set_active(tool.default)
        print(tool.default)
    elif a == "--print":
        name = argv[1] if len(argv) > 1 else tool.active()
        preset = tool.load(name) or die(f"no preset '{name}' (try -l)")
        for line in tool.render(preset, term_width()):
            print(line if sys.stdout.isatty() else SGR.sub("", line))
    elif a == "--save":
        name = argv[1] if len(argv) > 1 else die("--save needs a name", 2)
        bad = name_problem(tool, name)
        if bad:
            die(bad)
        tool.save(name, tool.active_preset())
        print(f"saved {tool.path(name).replace(HOME, '~', 1)}")
    elif a and a.startswith("-"):
        die(f"unknown option {a} (try -h)", 2)
    elif a:
        if not tool.source(a):
            die(f"no preset '{a}' (try -l)")
        tool.set_active(a)
        print(a)
    else:
        if not os.isatty(sys.stdout.fileno()):
            die("the picker needs a terminal", 2)
        App(tool).run()


def term_width():
    try:
        return os.get_terminal_size(sys.stdout.fileno()).columns
    except OSError:
        return 1000   # a pipe gets the whole line


def name_problem(tool, name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name or ""):
        return "use letters, digits, dot, dash or underscore"
    if tool.source(name):
        return f"{name} already exists"
    return None


# --- drawing --------------------------------------------------------------------

SGR = re.compile(r"\x1b\[[0-9;]*m")


class Canvas:
    """A grid of (char, style) cells, flushed in one write so nothing tears."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cells = [[(" ", "")] * w for _ in range(h)]

    def put(self, y, x, text, style="", limit=None):
        if not 0 <= y < self.h:
            return
        if limit is not None:
            text = text[:max(0, limit)]
        row = self.cells[y]
        for i, ch in enumerate(text):
            if 0 <= x + i < self.w:
                row[x + i] = (ch, style)

    def put_ansi(self, y, x, line, limit):
        """Text with SGR escapes in it, as a tool's render() returns."""
        style, i = "", 0
        for part in re.split(r"(\x1b\[[0-9;]*m)", line):
            if SGR.fullmatch(part):
                style = "" if part in ("\x1b[0m", "\x1b[m") else style + part
                continue
            self.put(y, x + i, part, style, limit=limit - i)
            i += len(part)

    def centred(self, w, h):
        big = Canvas(w, h)
        oy, ox = (h - self.h) // 2, (w - self.w) // 2
        for y, row in enumerate(self.cells):
            big.cells[oy + y][ox:ox + self.w] = row
        return big

    def render(self):
        out = ["\x1b[H"]
        for y, row in enumerate(self.cells):
            style = None
            for ch, st in row:
                if st != style:
                    out.append("\x1b[0m" + st)
                    style = st
                out.append(ch)
            out.append("\x1b[0m")
            if y < self.h - 1:
                out.append("\r\n")
        return "".join(out)


def box(c, y, x, w, h, title, on, fill=False):
    st = "" if on else DIM
    c.put(y, x, "╭" + "─" * (w - 2) + "╮", st)
    for r in range(y + 1, y + h - 1):
        c.put(r, x, "│", st)
        if fill:
            c.put(r, x + 1, " " * (w - 2))
        c.put(r, x + w - 1, "│", st)
    c.put(y + h - 1, x, "╰" + "─" * (w - 2) + "╯", st)
    c.put(y, x + 2, f" {title} ", st + (BOLD if on else ""), limit=w - 4)


def shown(e, v):
    """A setting's value as the editor prints it."""
    if v is None:
        return "unset"
    if e.kind == "choice" and isinstance(v, str) and v.strip() != v:
        return repr(v)          # a separator such as " | " needs its edges
    return str(v)


# --- keys -----------------------------------------------------------------------

SEQ = {"[A": "up", "[B": "down", "[C": "right", "[D": "left",
       "OA": "up", "OB": "down", "OC": "right", "OD": "left",
       "[1;2A": "S-up", "[1;2B": "S-down", "[1;2C": "S-right", "[1;2D": "S-left"}
PLAIN = {"\r": "enter", "\n": "enter", "\x7f": "bs", "\x08": "bs", "\x03": "ctrl-c", " ": "space"}
CSI = re.compile(r"\x1b(\[[0-9;]*[A-Za-z~]|O[A-Za-z])")


def keys(data):
    s, i = data.decode("utf-8", "ignore"), 0
    while i < len(s):
        m = CSI.match(s, i)
        if m:
            yield SEQ.get(m.group(1), "")
            i = m.end()
            continue
        yield "esc" if s[i] == "\x1b" else PLAIN.get(s[i], s[i])
        i += 1


HELP = {
    "list": (("↑↓", "move"), ("enter", "use it"), ("e →", "edit"), ("n", "new from this"),
             ("⌫ ⌫", "delete yours"), ("q esc", "quit")),
    "edit": (("↑↓", "move"), ("space", "show or hide"), ("←→", "change a setting"),
             ("⇧←→", "change by 10 steps"), ("enter", "pick or type"), ("x", "unset"),
             ("⇧↑↓ K J", "reorder"), ("z  y", "undo  redo"), ("⌫ ⌫", "undo all"),
             ("esc ←", "back"), ("", "changes save as you go")),
    "choose": (("type", "filter"), ("↑↓", "move"), ("enter", "take it"), ("esc", "back")),
}


# --- the app ----------------------------------------------------------------------

class App:
    """Three levels. The list of presets, with the hovered one drawn on the
    right. The editor for one preset. And a list for a setting with many
    options. Edits save as they happen, so esc only goes back. Undo all and
    delete are armed: ⌫ once says what goes."""

    def __init__(self, tool):
        self.t = tool
        self.tty = os.open("/dev/tty", os.O_RDWR)
        self.mode, self.done = "list", False
        self.rows = tool.listing()
        names = [n for n, _ in self.rows]
        self.li = names.index(tool.active()) if tool.active() in names else 0
        self.loff = self.ei = self.eoff = 0
        self.name = self.preset = None
        self.undo, self.redo, self.first = [], [], None
        self.prompt = self.msg = self.armed = None
        self.help = False
        self.folded = set()
        self.grouped = any(e.group for e in tool.elements)
        self.choose = None            # [key, options, filter, index, offset]
        self.shown_live = None

    def out(self, s):
        os.write(self.tty, s.encode())

    def say(self, text, style=""):
        self.msg = (text, style)

    def hovered(self):
        return self.rows[self.li][0]

    def live(self, preset):
        """Hand the tool a preset to show for real, once per change."""
        mark = json.dumps(preset, sort_keys=True)
        if mark != self.shown_live:
            self.shown_live = mark
            self.t.live(preset)

    # --- editor rows ------------------------------------------------------------
    # Shown elements in their order, then hidden ones, then the settings.
    # With groups, each group gets a folding heading over its own rows.

    def ekeys(self):
        show = self.preset["show"]
        hidden = [e.key for e in self.t.elements if e.kind == "show" and e.key not in show]
        sets = [e.key for e in self.t.elements if e.kind != "show"]
        return show + hidden + sets

    def erows(self):
        if not self.grouped:
            return [("elem", k) for k in self.ekeys()]
        keys = self.ekeys()
        order = list(dict.fromkeys(self.t.element(k).group for k in keys))
        rows = []
        for g in order:
            rows.append(("group", g))
            if g not in self.folded:
                rows += [("elem", k) for k in keys if self.t.element(k).group == g]
        return rows

    def focus(self, key):
        rows = self.erows()
        if ("elem", key) not in rows:
            self.folded.discard(self.t.element(key).group)
            rows = self.erows()
        self.ei = rows.index(("elem", key))

    # --- actions ----------------------------------------------------------------

    def use(self):
        name = self.hovered()
        self.t.set_active(name)
        self.say(f"✓ in use · {name} · {self.t.pickup}", GREEN)

    def open(self, name):
        self.name, self.preset = name, self.t.load(name)
        self.first = json.dumps(self.preset)
        self.was_builtin = self.t.source(name) == "built-in"
        self.undo, self.redo = [], []
        self.mode, self.ei, self.eoff = "edit", 0, 0
        self.folded = set()

    def change(self, fn):
        before = json.dumps(self.preset)
        fn(self.preset)
        if json.dumps(self.preset) == before:
            return
        self.undo.append(before)
        self.redo = []
        self.store()

    def set_value(self, key, v):
        self.change(lambda p: p["set"].__setitem__(key, v))

    def store(self):
        if self.was_builtin and json.dumps(self.preset) == self.first:
            self.t.delete(self.name)          # back to the built-in exactly
            self.say("✓ saved · same as the built-in", GREEN)
        else:
            try:
                self.t.save(self.name, self.preset)
                self.say("✓ saved", GREEN)
            except OSError as e:
                self.say(f"save failed: {e.strerror}", RED)
                return
        if self.name == self.t.active():
            self.t.applied(self.name, self.preset)

    def step(self, src, dst):
        if not src:
            self.say("nothing to " + ("undo" if src is self.undo else "redo"), DIM)
            return
        dst.append(json.dumps(self.preset))
        self.preset = json.loads(src.pop())
        self.store()

    def new_from(self, base):
        def make(name):
            name = name.strip()
            bad = name_problem(self.t, name)
            if bad:
                self.say(bad, RED)
                return
            self.t.save(name, self.t.load(base))
            self.rows = self.t.listing()
            self.li = [n for n, _ in self.rows].index(name)
            self.open(name)
            self.say(f"✓ new preset {name}", GREEN)
        n = 2
        while self.t.source(f"{base}-{n}"):
            n += 1
        self.prompt = ["new preset", f"{base}-{n}", make]

    def handover(self, fn):
        """Run fn with the terminal in normal mode, then take it back. A
        child that leaves the alternate screen on exit is fine."""
        old = self.saved_mode
        termios.tcsetattr(self.tty, termios.TCSADRAIN, old)
        self.out("\x1b[?7h\x1b[?25h")
        try:
            return fn()
        finally:
            self.out("\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J")
            tty.setraw(self.tty)
            self.shown_live = None

    def pick_color(self, e):
        cp = sibling("color-pick")
        if not cp:
            self.say("color-pick not found · # types a hex", RED)
            return
        start = self.preset["set"].get(e.key) or ""
        args = [cp, "--nested", "-t", e.label] + ([start] if start else [])
        r = self.handover(lambda: subprocess.run(args, stdout=subprocess.PIPE, text=True))
        v = r.stdout.strip()
        if r.returncode == 0 and HEX.fullmatch(v):
            self.set_value(e.key, v.lower())

    def take_typed(self, e):
        def take(text):
            text = text.strip()
            if e.kind == "number":
                try:
                    self.set_value(e.key, e.number(float(text)))
                except ValueError:
                    self.say(f"not a number: {text}", RED)
            elif e.kind == "color":
                v = text if text.startswith("#") else "#" + text
                if HEX.fullmatch(v):
                    self.set_value(e.key, v.lower())
                else:
                    self.say(f"not a hex colour: {text}", RED)
            elif e.kind == "choice":
                if text in e.options():
                    self.set_value(e.key, text)
                else:
                    self.say(f"not an option: {text}", RED)
            else:
                self.set_value(e.key, (text or None) if e.optional else text)
        cur = self.preset["set"].get(e.key)
        self.prompt = [e.label, "" if cur is None else str(cur), take]

    def open_list(self, e):
        opts = e.options()
        cur = self.preset["set"].get(e.key)
        i = opts.index(cur) if cur in opts else 0
        self.choose = [e.key, opts, "", i, 0]
        self.mode = "choose"

    def filtered(self):
        key, opts, text, _, _ = self.choose
        t = text.lower()
        return [o for o in opts if t in str(o).lower()] if t else opts

    def candidate(self):
        """The preset as it would be with the hovered option."""
        opts = self.filtered()
        p = json.loads(json.dumps(self.preset))
        if opts:
            p["set"][self.choose[0]] = opts[min(self.choose[3], len(opts) - 1)]
        return p

    # --- keys -------------------------------------------------------------------

    def key(self, k):
        if k == "ctrl-c":
            self.done = True
            return
        if self.prompt:
            self.prompt_key(k)
            return
        if self.help:
            self.help = False
            if k in ("?", "esc"):
                return
        armed, self.armed, self.msg = self.armed, None, None
        if self.mode == "choose":
            self.key_choose(k)
            return
        if k == "?":
            self.help = True
            return
        k = {"k": "up", "j": "down", "K": "S-up", "J": "S-down"}.get(k, k)
        getattr(self, "key_" + self.mode)(k, armed)

    def prompt_key(self, k):
        label, text, then = self.prompt
        if k == "esc":
            self.prompt = None
        elif k == "enter":
            self.prompt = None
            then(text)
        elif k == "bs":
            self.prompt[1] = text[:-1]
        elif k == "space":
            self.prompt[1] = text + " "
        elif len(k) == 1 and k.isprintable():
            self.prompt[1] = text + k

    def key_list(self, k, armed):
        name, src = self.rows[self.li]
        if k in ("up", "down"):
            self.li = (self.li + (1 if k == "down" else -1)) % len(self.rows)
        elif k == "enter":
            self.use()
        elif k in ("e", "right"):
            self.open(name)
        elif k == "n":
            self.new_from(name)
        elif k == "bs":
            if src == "built-in":
                self.say("built in · nothing to delete", DIM)
            elif armed != "bs":
                self.armed = "bs"
                then = "brings back the built-in" if src == "changed" else "deletes it"
                self.say(f"⌫ again {then} · {name}", RED)
            else:
                # A deleted pick falls back to the default by itself.
                self.t.delete(name)
                self.rows = self.t.listing()
                self.li = min(self.li, len(self.rows) - 1)
                self.say(f"✓ {'built-in back' if src == 'changed' else 'deleted'} · {name}", GREEN)
        elif k in ("q", "esc"):
            self.done = True

    def key_edit(self, k, armed):
        rows = self.erows()
        kind, ref = rows[self.ei]
        if k in ("up", "down"):
            self.ei = (self.ei + (1 if k == "down" else -1)) % len(rows)
            return
        if kind == "group":
            if k in ("space", "enter", "right") and ref in self.folded:
                self.folded.discard(ref)
            elif k in ("space", "enter", "left"):
                if ref in self.folded and k == "left":
                    self.back()
                else:
                    self.folded.add(ref)
            elif k in ("-", "+"):
                groups = {g for g in (e.group for e in self.t.elements)}
                self.folded = groups if k == "-" else set()
                self.ei = min(self.ei, len(self.erows()) - 1)
            else:
                self.key_any(k, armed)
            return
        e = self.t.element(ref)
        v = self.preset["set"].get(ref)
        show = self.preset["show"]
        if e.kind == "show" and k in ("space", "enter"):
            self.change(lambda p: p["show"].remove(ref) if ref in p["show"] else p["show"].append(ref))
            self.focus(ref)
        elif e.kind == "show" and k in ("S-up", "S-down") and ref in show:
            j = show.index(ref) + (1 if k == "S-down" else -1)
            if 0 <= j < len(show):
                def swap(p):
                    s = p["show"]
                    i = s.index(ref)
                    s[i], s[j] = s[j], s[i]
                self.change(swap)
                self.focus(ref)
        elif e.kind == "choice" and k in ("left", "right", "space", "enter"):
            opts = e.options()
            if k in ("space", "enter") and len(opts) > LIST_AT:
                self.open_list(e)
                return
            d = -1 if k == "left" else 1
            i = (opts.index(v) + d) % len(opts) if v in opts else (0 if d > 0 else len(opts) - 1)
            self.set_value(ref, opts[i])
        elif e.kind == "number" and k in ("left", "right", "S-left", "S-right"):
            n = (10 if k.startswith("S-") else 1) * (1 if k.endswith("right") else -1)
            base = v if v is not None else (e.default if e.default is not None else e.lo)
            self.set_value(ref, e.number(base + n * e.step))
        elif e.kind == "color" and k in ("space", "enter"):
            self.pick_color(e)
        elif k == "#" and e.kind == "color" or k in ("space", "enter") and e.kind in ("number", "text"):
            self.take_typed(e)
        elif k == "x" and e.kind != "show":
            if e.optional:
                self.set_value(ref, None)
            else:
                self.say(f"{e.label} always has a value", DIM)
        elif k in e.actions:
            label, fn = e.actions[k]
            new = self.handover(lambda: fn(self.t, v))
            if new is not None:
                self.set_value(ref, new)
        elif k == "left":
            if self.grouped:
                self.ei = rows.index(("group", e.group))
            else:
                self.back()
        else:
            self.key_any(k, armed)

    def key_any(self, k, armed):
        """Editor keys that work on any row."""
        if k == "z":
            self.step(self.undo, self.redo)
        elif k == "y":
            self.step(self.redo, self.undo)
        elif k == "bs":
            if json.dumps(self.preset) == self.first:
                self.say("nothing to undo", DIM)
            elif armed != "bs":
                self.armed = "bs"
                self.say(f"⌫ again undoes every change since you opened {self.name}", RED)
            else:
                self.undo.append(json.dumps(self.preset))
                self.preset = json.loads(self.first)
                self.store()
                self.say(f"✓ back to how {self.name} was when you opened it", GREEN)
        elif k in ("esc", "q"):
            self.back()

    def back(self):
        self.mode = "list"
        self.rows = self.t.listing()
        self.li = [n for n, _ in self.rows].index(self.name)

    def key_choose(self, k):
        opts = self.filtered()
        c = self.choose
        if k in ("up", "down") and opts:
            c[3] = (min(c[3], len(opts) - 1) + (1 if k == "down" else -1)) % len(opts)
        elif k == "enter":
            if opts:
                self.set_value(c[0], opts[min(c[3], len(opts) - 1)])
            self.choose, self.mode = None, "edit"
        elif k == "esc":
            if c[2]:
                c[2], c[3] = "", 0
            else:
                self.choose, self.mode = None, "edit"
        elif k == "bs":
            c[2], c[3] = c[2][:-1], 0
        elif k == "space":
            c[2], c[3] = c[2] + " ", 0
        elif len(k) == 1 and k.isprintable():
            c[2], c[3] = c[2] + k, 0

    # --- layout -----------------------------------------------------------------

    def draw(self):
        tw, th = os.get_terminal_size(self.tty)
        w, h = min(tw, MAX_W), min(th, MAX_H)
        c = Canvas(w, h)
        if w < MIN_W or h < MIN_H:
            c.put(h // 2, 2, f"make the window at least {MIN_W}×{MIN_H} · now {w}×{h}", DIM)
            self.out(c.render())
            return
        lw = max(32, min(44, w * 2 // 5))
        bh = h - 2
        self.draw_header(c, w)
        title = {"list": "presets", "edit": self.name,
                 "choose": self.choose and self.t.element(self.choose[0]).label}[self.mode]
        box(c, 1, 0, lw, bh, title, True)
        box(c, 1, lw, w - lw, bh, "preview", False)
        inner = (2, 1, lw - 2, bh - 2)
        if self.mode == "list":
            self.draw_list(c, *inner)
            preset = self.t.load(self.hovered())
        elif self.mode == "edit":
            self.draw_edit(c, *inner)
            preset = self.preset
        else:
            self.draw_choose(c, *inner)
            preset = self.candidate()
        self.live(preset)
        pw = w - lw - 4
        lines = self.t.render(preset, pw)
        for i, line in enumerate(lines[:bh - 2]):
            c.put_ansi(2 + i, lw + 2, line, pw)
        if self.mode == "list" and self.t.list_shows:
            self.draw_shows(c, 2 + len(lines) + 1, lw + 2, pw, bh - len(lines) - 3, preset)
        self.draw_footer(c, w, h - 1)
        if self.help:
            self.draw_help(c, w, h)
        self.out(c.centred(tw, th).render())

    def draw_header(self, c, w):
        c.put(0, 1, self.t.name, BOLD)
        x = len(self.t.name) + 3
        c.put(0, x, self.t.title, DIM, limit=w - x - 30)
        right = f"in use · {self.t.active()} "
        c.put(0, w - len(right), right, DIM)

    def draw_list(self, c, y, x, w, h):
        on = self.t.active()
        self.loff = max(min(self.loff, self.li), self.li - h + 1)
        for r in range(min(h, len(self.rows) - self.loff)):
            i = self.loff + r
            name, src = self.rows[i]
            mark = "•" if name == on else " "
            text = f"{mark} {name}".ljust(w - 10)[:w - 10]
            c.put(y + r, x + 1, text, REV if i == self.li else "")
            c.put(y + r, x + w - 9, src.rjust(8), DIM)

    def draw_value(self, c, y, x, w, e, v):
        """A setting's value at the right of its row."""
        if v is None:
            note = self.t.value(e.key)
            text = f"unset · {note}" if note else "unset"
            if len(text) > w:
                text = text[:w - 1] + "…"
            c.put(y, x + w - len(text), text, DIM)
            return
        text = shown(e, v)
        if e.kind == "choice" and not callable(e.choices) and len(e.choices) <= LIST_AT:
            text = f"‹ {text} ›"
        if len(text) > w:
            text = text[:w - 1] + "…"
        c.put(y, x + w - len(text), text)
        if e.kind == "color":
            c.put(y, x + w - len(text) - 3, "  ", BG(v))

    def draw_edit(self, c, y, x, w, h):
        rows = self.erows()
        show = self.preset["show"]
        self.ei = min(self.ei, len(rows) - 1)
        self.eoff = max(min(self.eoff, self.ei), self.ei - h + 1)
        for r in range(min(h, len(rows) - self.eoff)):
            i = self.eoff + r
            kind, ref = rows[i]
            on = i == self.ei
            if kind == "group":
                arrow = "▸" if ref in self.folded else "▾"
                count = sum(1 for e in self.t.elements if e.group == ref and e.kind != "show"
                            and self.preset["set"].get(e.key) is not None)
                c.put(y + r, x + 1, f"{arrow} {ref}".ljust(w - 2), (REV if on else "") + BOLD)
                if count:
                    c.put(y + r, x + w - 8, f"{count} set".rjust(7), DIM)
                continue
            e = self.t.element(ref)
            lw = w - 5
            if e.kind == "show":
                lit = e.key in show
                mark = f"{show.index(e.key) + 1:>2}" if lit else "  "
                c.put(y + r, x + 1, mark, DIM)
                c.put(y + r, x + 4, e.label.ljust(lw)[:lw], (REV if on else "") + ("" if lit else DIM))
                note = e.note or self.t.value(e.key)
                if note and len(e.label) + len(note) + 3 < lw:
                    c.put(y + r, x + w - 1 - len(note), note, DIM)
                continue
            v = self.preset["set"].get(ref)
            # Line settings up under group headings, or under show rows' numbers.
            pad = "  " if self.grouped else "   " if any(x.kind == "show" for x in self.t.elements) else ""
            label = pad + e.label
            c.put(y + r, x + 1, label.ljust(w - 2)[:w - 2], REV if on else "")
            room = w - 3 - min(len(label), w // 2)
            if room > 4:
                self.draw_value(c, y + r, x + w - 1 - room, room, e, v)
        if self.eoff:
            c.put(y - 1, x + w - 2, "↑", DIM)
        if self.eoff + h < len(rows):
            c.put(y + h, x + w - 2, "↓", DIM)

    def draw_choose(self, c, y, x, w, h):
        key, _, text, idx, off = self.choose
        opts = self.filtered()
        cur = self.preset["set"].get(key)
        c.put(y, x + 1, "filter › ", DIM)
        c.put(y, x + 10, text)
        c.put(y, x + 10 + len(text), " ", REV)
        c.put(y, x + w - 8, f"{len(opts):>6}", DIM)
        h -= 2
        idx = min(idx, max(0, len(opts) - 1))
        off = max(min(off, idx), idx - h + 1)
        self.choose[4] = off
        for r in range(min(h, len(opts) - off)):
            i = off + r
            o = opts[i]
            mark = "•" if o == cur else " "
            c.put(y + 2 + r, x + 1, f"{mark} {o}".ljust(w - 2)[:w - 2], REV if i == idx else "")

    def draw_shows(self, c, y, x, w, h, preset):
        """What the hovered preset shows or sets, with each one's reading."""
        rows = [(f"{i + 1:>2}", self.t.element(k), None) for i, k in enumerate(preset["show"])]
        rows += [(" ·", e, preset["set"].get(e.key)) for e in self.t.elements
                 if e.kind != "show" and preset["set"].get(e.key) is not None]
        if h < 2 or not rows:
            return
        c.put(y, x, "shows" if preset["show"] else "sets", DIM)
        for r, (mark, e, v) in enumerate(rows[:h - 1]):
            val = shown(e, v) if e.kind != "show" else self.t.value(e.key)
            c.put(y + 1 + r, x, mark, DIM)
            c.put(y + 1 + r, x + 3, e.label, limit=w - 3)
            c.put(y + 1 + r, x + 24, val, DIM, limit=w - 24)
        if len(rows) > h - 1:
            c.put(y + h - 1, x + 3, f"+ {len(rows) - h + 1} more", DIM)

    def hints(self):
        if self.mode == "list":
            return "↑↓ move · enter use · e edit · n new · ? keys"
        if self.mode == "choose":
            return "type to filter · ↑↓ move · enter take · esc back"
        kind, ref = self.erows()[self.ei]
        if kind == "group":
            return "enter fold · -/+ fold all · z undo · esc back · ? keys"
        e = self.t.element(ref)
        own = {"show": "space show/hide · ⇧↑↓ reorder",
               "choice": "←→ change" + (" · enter list" if callable(e.choices) or len(e.choices) > LIST_AT else ""),
               "number": "←→ adjust · ⇧←→ ×10 · enter type",
               "color": "enter pick · # hex",
               "text": "enter type"}[e.kind]
        if e.optional:
            own += " · x unset"
        for key, (label, _) in e.actions.items():
            own += f" · {key} {label}"
        return own + " · z undo · esc back · ? keys"

    def draw_footer(self, c, w, y):
        if self.prompt:
            label, text, _ = self.prompt
            c.put(y, 1, f"{label} › ", BOLD)
            c.put(y, len(label) + 4, text)
            c.put(y, len(label) + 4 + len(text), " ", REV)
            c.put(y, w - 22, "enter ok · esc cancel", DIM)
        elif self.msg:
            c.put(y, 1, self.msg[0], self.msg[1], limit=w - 2)
        else:
            c.put(y, 1, self.hints(), DIM, limit=w - 2)

    def draw_help(self, c, w, h):
        items = HELP[self.mode]
        bw = max(len(a) + len(b) for a, b in items) + 8
        bh = len(items) + 2
        y, x = (h - bh) // 2, (w - bw) // 2
        box(c, y, x, bw, bh, "keys", True, fill=True)
        for i, (k, what) in enumerate(items):
            c.put(y + 1 + i, x + 2, k.ljust(bw - 4 - len(what)), BOLD)
            c.put(y + 1 + i, x + bw - 2 - len(what), what, DIM if not k else "")

    # --- loop -------------------------------------------------------------------

    def run(self):
        self.saved_mode = termios.tcgetattr(self.tty)
        self.out("\x1b[?1049h\x1b[?25l\x1b[?7l")
        tty.setraw(self.tty)
        try:
            size, stale = None, True
            while not self.done:
                now = os.get_terminal_size(self.tty)
                if stale or now != size:
                    self.draw()
                    size, stale = now, False
                if select.select([self.tty], [], [], 0.25)[0]:
                    for k in keys(os.read(self.tty, 1024)):
                        self.key(k)
                        if self.done:
                            break
                    stale = True
        finally:
            termios.tcsetattr(self.tty, termios.TCSADRAIN, self.saved_mode)
            self.out("\x1b[?7h\x1b[?25h\x1b[?1049l")
            self.t.restore()
            os.close(self.tty)
