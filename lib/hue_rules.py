"""hue_rules: the hues in hues.json, and how a group and its items take their steps.

The one copy of these rules. hue-pick --assign draws its preview by them, and
callers such as awday and awforge draw their views by them, so the picker
shows exactly what the caller draws. Callers load this file from beside
hue-pick (bin/../lib/hue_rules.py) rather than keeping their own copy.

A group picks one hue. Its own colour is one of that hue's five hand-checked
xterm steps, darkest first: the middle for the first group on a hue, the next
of ITEM_ORDER for the next group sharing it, or a step set by hand.

A group's items take steps too. An item set by hand keeps its step. The rest,
by their rank (biggest first), take the first `steps` steps outward from the
group's own, lighter first, repeating. Sorted views list a group's items by
step, dark to light, so lightness climbs down each section.

Hues sit in hues.json in wheel order. Two neighbouring hues on neighbouring
groups read alike: neighbours() names them, for a warning, never a block.
"""
import json, os

STEPS = 5                        # hand-checked xterm steps per hue
ITEM_ORDER = (2, 3, 1, 4, 0)     # middle out over the five steps

HERE = os.path.dirname(os.path.realpath(__file__))
HUES_FILES = (os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "hue-pick", "hues.json"),
              os.path.join(os.path.dirname(HERE), "config", "hue-pick", "hues.json"))


def hues_file():
    return next((p for p in HUES_FILES if os.path.exists(p)), None)


def load_hues():
    """[{"name", "hue", "light", "xterm": [five steps]}], in wheel order. Raises on a bad file."""
    path = hues_file()
    if not path:
        raise FileNotFoundError("no hues.json · looked in " + " and ".join(HUES_FILES))
    with open(path) as f:
        return json.load(f)["hues"]


def outward(base, n=STEPS):
    """Steps from base outward, lighter first: 2 gives 2, 3, 1, 4, 0."""
    seq, d = [base], 1
    while len(seq) < n:
        seq += [b for b in (base + d, base - d) if 0 <= b < n]
        d += 1
    return seq[:n]


def group_steps(pairs, fixed):
    """{key: step} for [(key, hue)] in display order; fixed holds steps set by hand."""
    seen, out = {}, {}
    for key, hue in pairs:
        k = seen.get(hue, 0)
        out[key] = fixed[key] if fixed.get(key) is not None else ITEM_ORDER[k % STEPS]
        seen[hue] = k + 1
    return out


def item_steps(base, steps, fixed):
    """Each item's step, by rank. fixed is one entry per item, a step or None.
    An auto item takes the steps outward from base by its own rank, so setting
    one item by hand never moves another."""
    use = outward(base)[:max(1, min(steps, STEPS))]
    return [f if f is not None else use[j % len(use)] for j, f in enumerate(fixed)]


def item_colours(xterm, base, steps, fixed):
    """The group's colour, then each item's, by rank."""
    return [xterm[base]] + [xterm[s] for s in item_steps(base, steps, fixed)]


def by_step(items, steps_of):
    """Items in sorted-view order: dark to light, rank kept within a step."""
    return [x for _, _, x in sorted((steps_of[i], i, x) for i, x in enumerate(items))]


def neighbours(pairs, hues):
    """[(key, key, hue, hue)] for each two groups side by side whose hues sit next
    to each other on the wheel. A shared hue is not a warning: steps tell those apart."""
    at = {h["name"]: i for i, h in enumerate(hues)}
    out = []
    for (a, ha), (b, hb) in zip(pairs, pairs[1:]):
        if ha in at and hb in at and ha != hb and (at[ha] - at[hb]) % len(hues) in (1, len(hues) - 1):
            out.append((a, b, ha, hb))
    return out


def nearest(hexc, hues):
    """(hue, step) whose xterm colour sits closest to hexc, or (None, None)."""
    if not hues or not hexc or not hexc.startswith("#"):
        return None, None
    rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    want = rgb(hexc)
    return min((sum((a - b) ** 2 for a, b in zip(rgb(x), want)), h["name"], i)
               for h in hues for i, x in enumerate(h["xterm"]))[1:]
