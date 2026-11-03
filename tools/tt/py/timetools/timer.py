"""Countdown timer, and `wait`, its silent cousin. Logic only."""

import time
from types import SimpleNamespace

from timetools import term

HELP = "space pause · n next · q quit"
WAIT_HELP = "enter skip · n next · q quit"
RING_GAP = 0.6


def run(cfg, view):
    total = cfg["duration"]
    waiting = cfg["tool"] == "wait"
    clock = term.Clock()
    outcome = nav = None

    def state():
        left = max(0.0, total - clock.elapsed)
        return SimpleNamespace(
            tool="timer", now=time.monotonic(), total=total, left=left, label=cfg["label"] or "",
            paused=clock.paused, outcome=outcome, nav=nav, ends_at=time.time() + left,
        )

    with term.Keys() as keys:
        view.open("timer", (WAIT_HELP if waiting else HELP) if keys.interactive else None)
        try:
            while True:
                s = state()
                if s.left <= 0:
                    outcome = "done"
                    break
                view.frame(s)
                key = keys.read(term.soonest(None if s.paused else s.left, view.next_frame(s)))
                if key in term.NAV:
                    nav, outcome = term.NAV[key], "cancelled"
                    break
                if waiting and key in ("enter", "space"):
                    outcome = "skipped"
                    break
                if key == "space":
                    clock.toggle()
                    view.event("pause" if clock.paused else "start", state())
            if outcome == "done" and cfg.get("sound"):
                for _ in range(cfg.get("rings", 0)):
                    term.play("Glass")
                    until = time.monotonic() + RING_GAP
                    while True:
                        s = state()
                        view.frame(s)
                        if s.now >= until:
                            break
                        time.sleep(term.soonest(until - s.now, view.next_frame(s)))
        except KeyboardInterrupt:
            nav, outcome = "quit", "cancelled"
        finally:
            view.close(state())
            clock.pause()
    return {"tool": cfg["tool"], "label": cfg["label"] or "", "outcome": outcome, "nav": nav,
            "elapsed": min(total, clock.elapsed), "total": total}
