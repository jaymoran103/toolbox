"""Stopwatch with laps, a time limit and a solve mode. Logic only."""

import time
from types import SimpleNamespace

from timetools import term

HELP = "enter/l lap · space pause · r reset · n next · q quit"
SOLVE_HELP = "space or enter to stop · n next · q quit"


def run(cfg, view):
    clock = term.Clock()
    laps = []
    outcome = nav = None
    limit = None if cfg["for"] in (None, "forever") else cfg["for"]
    cap = cfg["cap"]

    def state():
        return SimpleNamespace(
            tool="stopwatch", now=time.monotonic(), label=cfg["label"] or "", elapsed=clock.elapsed,
            laps=tuple(laps), paused=clock.paused, outcome=outcome, nav=nav, cap=cap,
        )

    with term.Keys() as keys:
        view.open("stopwatch", (SOLVE_HELP if cfg["solve"] else HELP) if keys.interactive else None)
        try:
            while True:
                s = state()
                if cap is not None and s.elapsed >= cap:
                    outcome = "dnf"
                    break
                if limit is not None and s.elapsed >= limit:
                    outcome = "done"
                    break
                view.frame(s)
                ends = [x - s.elapsed for x in (cap, limit) if x is not None and not s.paused]
                key = keys.read(term.soonest(view.next_frame(s), *ends))
                if key in term.NAV:
                    nav, outcome = term.NAV[key], "stopped"
                    break
                if cfg["solve"]:
                    if key in ("space", "enter"):
                        outcome = "done"
                        break
                elif key == "space":
                    clock.toggle()
                    view.event("pause" if clock.paused else "start", state())
                elif key in ("enter", "l"):
                    laps.append(state().elapsed)
                    view.event("lap", state())
                elif key == "r":
                    paused = clock.paused
                    clock.reset()
                    if paused:
                        clock.pause()
                    laps = []
                    view.event("change", state())
        except KeyboardInterrupt:
            nav, outcome = "quit", "stopped"
        finally:
            view.close(state())
            clock.pause()
    return {"tool": "stopwatch", "label": cfg["label"] or "", "outcome": outcome, "nav": nav,
            "elapsed": min(clock.elapsed, cap) if outcome == "dnf" else clock.elapsed, "laps": laps}
