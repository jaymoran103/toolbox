"""Fireworks: spread a number of events over a timespan. Logic only.

The core needs no UI. Each burst is a "burst" event that a view may draw,
print or ignore. plan() is the pure scheduling part and can be used alone.
"""

import math
import os
import time
from types import SimpleNamespace

from timetools import term

HELP = "space pause · n next · q quit"
DRAIN = 5.0  # longest a view may keep animating after the show ends
STYLE_DEFAULTS = {
    "colors": "pink,cyan,gold,green,violet,red", "children": 40, "trail": 4,
    "length": 1.4, "size": 0.3, "gravity": 1.0, "crackle": 0, "rocket": True,
}
PALETTES = {
    "festival": {},
    "ember": {"colors": "orange,red,gold", "crackle": 2, "gravity": 1.3, "size": 0.25, "length": 1.6},
    "frost": {"colors": "cyan,blue,white", "trail": 6, "gravity": 0.6, "length": 1.8},
    "gold": {"colors": "gold,white", "crackle": 3, "children": 60},
}
class Rand:
    """Seeded mulberry32. Bit for bit the same stream as timetools.js, so a
    seed gives the same show in the terminal and the browser."""

    def __init__(self, seed=None):
        self.seed = int.from_bytes(os.urandom(4), "big") if seed is None else seed & 0xFFFFFFFF
        self._a = self.seed

    def __call__(self):
        a = self._a = (self._a + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    def uniform(self, a, b):
        return a + (b - a) * self()

    def randint(self, a, b):
        return a + int(self() * (b - a + 1))

    def choice(self, seq):
        return seq[int(self() * len(seq))]


def resolve_style(palette=None, overrides=None):
    """Defaults, then the palette, then single flags."""
    return dict(STYLE_DEFAULTS, **PALETTES.get(palette or "festival", {}), **(overrides or {}))


def _clusters(times, rng, cluster, within, limit=None):
    """Each time becomes a clump of bursts spread over `within` seconds."""
    if not cluster:
        return list(times)
    out = []
    for t in times:
        for off in sorted(rng.uniform(0, within) for _ in range(rng.randint(*cluster))):
            if limit is None or t + off <= limit:  # a clump cut off by the end loses its tail
                out.append(t + off)
    return sorted(out)


def plan(span, count=None, rate=None, spread="random", rng=None, cluster=None, within=2.0):
    """Pick a timespan and an event count from their ranges, then the times.

    span, count, rate and cluster are (lo, hi) pairs. Give count or rate.
    count and rate count clumps when cluster is set.
    Returns (span in seconds, sorted burst offsets in seconds).
    """
    rng = rng or Rand()
    seconds = rng.uniform(*span)
    if count:
        n = rng.randint(*count)
    else:
        n = max(1, int(math.floor(rng.uniform(*rate) * seconds + 0.5)))
    if spread == "even":
        times = [(i + 0.5) * seconds / n for i in range(n)]
    else:
        times = sorted(rng.uniform(0, seconds) for _ in range(n))
    return seconds, _clusters(times, rng, cluster, within, seconds)


def stream(rate, spread="random", rng=None, cluster=None, within=2.0):
    """Burst offsets with no end, for a `forever` show. A random gap is
    uniform between 0 and twice the mean, so bursts keep the rate on average.
    Clumps never overlap: each gap starts after the last clump ends."""
    rng = rng or Rand()
    per_second = rng.uniform(*rate)
    t = 0.0
    while True:
        t += 1.0 / per_second if spread == "even" else rng.uniform(0, 2.0 / per_second)
        for burst in _clusters([t], rng, cluster, within):
            yield burst
        if cluster:
            t += within


def run(cfg, view):
    rng = Rand(cfg["seed"])
    if cfg["rate"] is None and cfg["count"] is None:
        cfg = dict(cfg, rate=[1.0, 1.0])
    forever = cfg["span"] == "forever"
    if forever:
        seconds, times = math.inf, stream(cfg["rate"], cfg["spread"], rng, cfg["cluster"], cfg["within"])
        count = None
    else:
        seconds, planned = plan(cfg["span"], cfg["count"], cfg["rate"], cfg["spread"], rng, cfg["cluster"], cfg["within"])
        times, count = iter(planned), len(planned)
    upcoming = next(times, None)
    clock = term.Clock()
    fired = 0
    done = False
    outcome = nav = None

    def state():
        return SimpleNamespace(
            tool="fireworks", now=time.monotonic(), label=cfg["label"] or "", elapsed=min(seconds, clock.elapsed),
            span=seconds, count=count, fired=fired, paused=clock.paused, done=done, seed=rng.seed,
            outcome=outcome, nav=nav,
        )

    with term.Keys() as keys:
        view.open("fireworks", HELP if keys.interactive else None)
        try:
            while True:
                elapsed = clock.elapsed
                while not clock.paused and upcoming is not None and elapsed >= upcoming:
                    fired += 1
                    upcoming = next(times, None)
                    term.play("Pop", cfg["sound"])
                    view.event("burst", state())
                if not clock.paused and elapsed >= seconds:
                    outcome = "done"
                    break
                s = state()
                view.frame(s)
                next_at = upcoming if upcoming is not None else seconds
                wait = None if clock.paused else max(0.0, next_at - elapsed)
                key = keys.read(term.soonest(wait, view.next_frame(s)))
                if key in term.NAV:
                    nav, outcome = term.NAV[key], "stopped"
                    break
                if key == "space":
                    clock.toggle()
                    view.event("pause" if clock.paused else "start", state())
            done = True
            until = time.monotonic() + DRAIN
            while nav != "quit":  # let the view finish its animation
                s = state()
                view.frame(s)
                wait = view.next_frame(s)
                if wait is None or s.now >= until:
                    break
                if keys.read(min(wait, until - s.now)) in term.NAV:
                    break
        except KeyboardInterrupt:
            nav, outcome = "quit", "stopped"
        finally:
            done = True
            view.close(state())
    return {"tool": "fireworks", "label": cfg["label"] or "", "outcome": outcome, "nav": nav,
            "elapsed": min(seconds, clock.elapsed), "fired": fired, "count": count}
