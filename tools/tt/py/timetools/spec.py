"""The shared line syntax. One tool run per line, presets as named blocks.

web/timetools.js has the same parser. spec/cases.json holds the cases both
must agree on, and SPEC.md describes the grammar.
"""

import re

from timetools.durations import parse as parse_duration


class ParseError(ValueError):
    pass


ALIASES = {"sw": "stopwatch", "t": "timer", "m": "metronome", "c": "counter", "fw": "fireworks"}

# name: (kind, short flag, help, side). side is "cli" or "web" for options
# the other implementation accepts and ignores.
COMMON = {
    "label": ("str", None, "name shown on screen and in results", None),
    "view": ("str", None, "how to draw: plain or big", "cli"),
    "target": ("str", None, "element to draw into", "web"),
    "trigger": ("str", None, "click, load or visible", "web"),
    "origin": ("str", None, "element or random", "web"),
}

STYLE = {
    "palette": ("choice:festival|ember|frost|gold", None, "named style", None),
    "colors": ("str", None, "comma list of names or #hex", None),
    "children": ("int", None, "sparks per burst", None),
    "trail": ("int", None, "trail points per spark", None),
    "length": ("float", None, "seconds a spark burns", None),
    "size": ("float", None, "burst radius, share of height", None),
    "gravity": ("float", None, "how fast sparks fall", None),
    "crackle": ("int", None, "mini sparks when a spark dies", None),
    "rocket": ("flag", None, "rise before bursting", None),
}

TOOLS = {
    "stopwatch": {
        "pos": [],
        "opts": {
            "for": ("dur*", None, "stop after this long", None),
            "cap": ("dur", None, "past this a solve is DNF", None),
            "solve": ("flag", None, "space or enter stops and submits", None),
        },
        "help": "count up, with laps",
    },
    "timer": {
        "pos": ["duration", "label"],
        "opts": {
            "duration": ("dur", None, "how long, e.g. 90s, 5m, 1:30", None),
            "rings": ("int", None, "alert sounds when done", None),
            "sound": ("flag", None, "ring when done", None),
        },
        "need": ["duration"],
        "help": "count down",
    },
    "wait": {
        "pos": ["duration"],
        "opts": {"duration": ("dur", None, "how long", None)},
        "need": ["duration"],
        "help": "a silent pause between steps",
    },
    "metronome": {
        "pos": ["bpm"],
        "opts": {
            "bpm": ("int", None, "beats per minute, 20 to 400", None),
            "beats": ("int", "b", "beats per bar, 1 for no accent", None),
            "for": ("dur*", None, "stop after this long", None),
            "sound": ("flag", None, "click on each beat", None),
        },
        "help": "beats, with an accented first beat",
    },
    "counter": {
        "pos": ["label"],
        "opts": {
            "start": ("int", None, "first value", None),
            "step": ("int", None, "how much each press adds", None),
        },
        "help": "a tally",
    },
    "fireworks": {
        "pos": ["span"],
        "opts": dict({
            "span": ("span", None, "how long the show runs, a range, or forever", None),
            "count": ("irange", "n", "how many bursts, e.g. 20 or 10-30", None),
            "rate": ("rate", "r", "bursts per s, m or h, e.g. 2/s or 4-8/h", None),
            "spread": ("choice:random|even", None, "how bursts are spaced", None),
            "seed": ("int", None, "repeat the same show", None),
            "cluster": ("irange", None, "bursts per clump, e.g. 2-4", None),
            "within": ("dur", None, "how long a clump lasts", None),
            "sound": ("flag", None, "a pop per burst", None),
        }, **STYLE),
        "help": "bursts spread over a timespan",
    },
}

DEFAULTS = {
    "stopwatch": {"for": None, "cap": None, "solve": False},
    "timer": {"rings": 3, "sound": True},
    "wait": {},
    "metronome": {"bpm": 120, "beats": 4, "for": None, "sound": True},
    "counter": {"start": 0, "step": 1},
    "fireworks": {"span": [30.0, 30.0], "count": None, "rate": None, "spread": "random", "seed": None,
                  "cluster": None, "within": 2.0, "sound": False},
}

DIRECTIVES = {"repeat": "count", "gap": "dur", "advance": "choice:auto|key", "score": "choice:times|wca"}
RATE_UNITS = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600}
NUMBER = re.compile(r"\d+(\.\d+)?")


def parse_range(text, one):
    """'5' or '5-10' -> [lo, hi]. In '1-2m' the unit on the high end also
    applies to a bare low end."""
    lo, _, hi = text.strip().partition("-")
    unit = re.search(r"[a-z]+$", hi.lower())
    if unit and NUMBER.fullmatch(lo.strip()):
        lo += unit.group()
    lo = one(lo)
    hi = one(hi) if hi else lo
    if hi < lo:
        raise ValueError("range %r runs backwards" % text)
    return [lo, hi]


def parse_rate(text):
    """'2', '2/s', '30/m', '1-3/s' -> [lo, hi] per second."""
    body, _, unit = text.strip().partition("/")
    if unit and unit not in RATE_UNITS:
        raise ValueError("unknown rate unit %r (use s, m or h)" % unit)
    per = RATE_UNITS[unit or "s"]
    return [r / per for r in parse_range(body, _float)]


def _int(text):
    if not re.fullmatch(r"-?\d+", text.strip()):
        raise ValueError("not a whole number: %r" % text)
    return int(text)


def _float(text):
    if not re.fullmatch(r"-?\d+(\.\d+)?", text.strip()):
        raise ValueError("not a number: %r" % text)
    return float(text)


def _bool(text):
    value = text.lower()
    if value in ("true", "yes", "on", "1"):
        return True
    if value in ("false", "no", "off", "0"):
        return False
    raise ValueError("not true or false: %r" % text)


def convert(kind, text):
    if kind == "str":
        return text
    if kind == "int":
        return _int(text)
    if kind == "float":
        return _float(text)
    if kind == "count":
        n = _int(text)
        if n < 1:
            raise ValueError("must be 1 or more")
        return n
    if kind in ("dur", "dur*"):
        if kind == "dur*" and text == "forever":
            return "forever"
        return parse_duration(text)
    if kind == "span":
        return "forever" if text == "forever" else parse_range(text, parse_duration)
    if kind == "irange":
        return parse_range(text, _int)
    if kind == "rate":
        return parse_rate(text)
    if kind.startswith("choice:"):
        options = kind[7:].split("|")
        if text not in options:
            raise ValueError("use one of %s" % ", ".join(options))
        return text
    raise AssertionError(kind)


def tokenize(line):
    """Split a line into statements of tokens. Quotes group words, ';' ends a
    statement, and '#' starts a comment at the start of a line or when a
    space follows it, so '#ff3366' stays a value."""
    statements, tokens, cur, has = [], [], [], False
    i, n = 0, len(line)

    def flush():
        nonlocal cur, has
        if has:
            tokens.append("".join(cur))
        cur, has = [], False

    while i < n:
        ch = line[i]
        if ch in " \t":
            flush()
            i += 1
        elif ch == "#" and not has and (not line[:i].strip() or i + 1 == n or line[i + 1] in " \t"):
            break
        elif ch == ";":
            flush()
            statements.append(tokens)
            tokens = []
            i += 1
        elif ch == "'":
            end = line.find("'", i + 1)
            if end < 0:
                raise ParseError("unclosed quote")
            cur.append(line[i + 1:end])
            has, i = True, end + 1
        elif ch == '"':
            has, i = True, i + 1
            while True:
                if i >= n:
                    raise ParseError("unclosed quote")
                c = line[i]
                if c == "\\" and i + 1 < n and line[i + 1] in '"\\':
                    cur.append(line[i + 1])
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    cur.append(c)
                    i += 1
        else:
            cur.append(ch)
            has, i = True, i + 1
    flush()
    statements.append(tokens)
    return [s for s in statements if s]


def schema(tool):
    return dict(COMMON, **TOOLS[tool]["opts"])


def parse_step(tokens):
    """Tokens of one statement -> {"tool": name, option: value, ...}.
    Only the options given appear. DEFAULTS fill the rest at run time."""
    toks = list(tokens)
    if toks and toks[0] == "tt":
        toks.pop(0)
    if not toks:
        raise ParseError("empty step")
    tool = ALIASES.get(toks[0], toks[0])
    if tool not in TOOLS:
        raise ParseError("unknown tool %r" % toks[0])
    opts = schema(tool)
    shorts = {spec[1]: name for name, spec in opts.items() if spec[1]}
    pos = list(TOOLS[tool]["pos"])
    out = {"tool": tool}
    i = 1
    while i < len(toks):
        tok = toks[i]
        i += 1
        value = None
        if tok.startswith("--") and len(tok) > 2:
            name, eq, value = tok[2:].partition("=")
            if not eq:
                value = None
            if name not in opts and name.startswith("no-") and opts.get(name[3:], ("",))[0] == "flag":
                if value is not None:
                    raise ParseError("--%s takes no value" % name)
                name, value = name[3:], "false"
            if name not in opts:
                raise ParseError("unknown option --%s for %s" % (name, tool))
        elif re.fullmatch(r"-[A-Za-z]", tok):
            if tok[1] not in shorts:
                raise ParseError("unknown option %s for %s" % (tok, tool))
            name = shorts[tok[1]]
        else:
            if not pos:
                raise ParseError("unexpected %r for %s" % (tok, tool))
            name, value = pos[0], tok
        kind = opts[name][0]
        if kind == "flag" and value is None:
            value = "true"
        if value is None:
            if i >= len(toks):
                raise ParseError("--%s needs a value" % name)
            value = toks[i]
            i += 1
        try:
            out[name] = _bool(value) if kind == "flag" else convert(kind, value)
        except ValueError as e:
            raise ParseError("bad value for %s: %s" % (name, e))
        if name in pos:
            pos.remove(name)
    for name in TOOLS[tool].get("need", ()):
        if name not in out:
            raise ParseError("%s needs a %s" % (tool, name))
    if "count" in out and "rate" in out:
        raise ParseError("give count or rate, not both")
    if out.get("span") == "forever" and "count" in out:
        raise ParseError("a forever show takes a rate, not a count")
    return out


def parse_line(line):
    statements = tokenize(line)
    if len(statements) != 1:
        raise ParseError("expected one step")
    return parse_step(statements[0])


def new_block(name):
    return {"name": name, "repeat": 1, "gap": 0.0, "advance": "auto", "score": None, "steps": []}


def parse_text(text):
    """Preset text -> blocks. Steps before any [name] form a block named ''."""
    blocks = [new_block("")]
    for number, raw in enumerate(text.splitlines(), 1):
        try:
            header = re.fullmatch(r"\s*\[([A-Za-z0-9_-]+)\]\s*(#.*)?", raw)
            if header:
                blocks.append(new_block(header.group(1)))
                continue
            for statement in tokenize(raw):
                if statement[0].startswith("@"):
                    name = statement[0][1:]
                    if name not in DIRECTIVES:
                        raise ParseError("unknown directive @%s" % name)
                    if len(statement) != 2:
                        raise ParseError("@%s takes one value" % name)
                    try:
                        blocks[-1][name] = convert(DIRECTIVES[name], statement[1])
                    except ValueError as e:
                        raise ParseError("bad value for @%s: %s" % (name, e))
                else:
                    blocks[-1]["steps"].append(parse_step(statement))
        except ParseError as e:
            raise ParseError("line %d: %s" % (number, e))
    if not blocks[0]["steps"] and blocks[0] == new_block("") and len(blocks) > 1:
        blocks.pop(0)
    return blocks


def expand(block):
    """A block's steps, repeated, with {n} in labels set to the round."""
    out = []
    for n in range(1, block["repeat"] + 1):
        for step in block["steps"]:
            step = dict(step)
            if "label" in step:
                step["label"] = step["label"].replace("{n}", str(n))
            out.append(step)
    return out


def describe(step):
    """A step back as a short line, for menus and headers."""
    words = [step["tool"]]
    for key, value in step.items():
        if key in ("tool", "label"):
            continue
        if isinstance(value, list):
            value = "%g-%g" % tuple(value) if value[0] != value[1] else "%g" % value[0]
        elif isinstance(value, float):
            value = "%g" % value
        words.append("--%s %s" % (key, value) if value is not True else "--" + key)
    return " ".join(str(w) for w in words)


def help_text(tool=None, prog="tt"):
    if tool is None:
        lines = ["usage: %s <tool> [options]   one run" % prog,
                 "       %s run <preset|file|text>   a sequence" % prog,
                 "       %s presets [name]   list or show presets" % prog,
                 "       %s help <tool>" % prog, "", "tools:"]
        lines += ["  %-10s %s" % (name, t["help"]) for name, t in TOOLS.items()]
        return "\n".join(lines)
    t = TOOLS[tool]
    usage = " ".join("[%s]" % p for p in t["pos"])
    lines = ["usage: %s %s %s [options]" % (prog, tool, usage), "", t["help"], ""]
    for name, (kind, short, text, side) in schema(tool).items():
        if side == "web" or not text:
            continue
        flag = ("-%s, " % short if short else "    ") + "--" + name
        if kind == "flag":
            flag += " / --no-" + name
        default = DEFAULTS[tool].get(name)
        note = " (default %s)" % _show(default) if default not in (None, False) else ""
        lines.append("  %-26s %s%s" % (flag, text, note))
    return "\n".join(lines)


def _show(value):
    if isinstance(value, list):
        return "%gs" % value[0]
    if value is True:
        return "on"
    return value
