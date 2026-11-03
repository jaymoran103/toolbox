"""Tally counter. Logic only."""

import time
from types import SimpleNamespace

from timetools import term

HELP = "space/up/+ add · down/- subtract · u undo · r reset · n next · q quit"


def run(cfg, view):
    n = cfg["start"]
    history = []
    outcome = nav = None

    def state():
        return SimpleNamespace(
            tool="counter", now=time.monotonic(), n=n, start=cfg["start"], step=cfg["step"],
            label=cfg["label"] or "", outcome=outcome, nav=nav,
        )

    with term.Keys() as keys:
        if not keys.interactive:
            print("counter: needs an interactive terminal")
            return {"tool": "counter", "label": cfg["label"] or "", "outcome": "error", "nav": None, "n": n}
        view.open("counter", HELP)
        try:
            while True:
                s = state()
                view.frame(s)
                key = keys.read(view.next_frame(s))
                if key in term.NAV:
                    nav, outcome = term.NAV[key], "done"
                    break
                if key in ("space", "enter", "up", "+", "=", "k"):
                    history.append(n)
                    n += cfg["step"]
                elif key in ("down", "-", "_", "j", "backspace"):
                    history.append(n)
                    n -= cfg["step"]
                elif key == "u" and history:
                    n = history.pop()
                elif key == "r":
                    history.append(n)
                    n = cfg["start"]
                else:
                    continue
                view.event("change", state())
        except KeyboardInterrupt:
            nav, outcome = "quit", "done"
        finally:
            view.close(state())
    return {"tool": "counter", "label": cfg["label"] or "", "outcome": outcome, "nav": nav, "n": n}
