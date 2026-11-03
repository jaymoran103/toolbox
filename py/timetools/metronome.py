"""Metronome with an accented first beat. Logic only."""

import time
from types import SimpleNamespace

from timetools import term

MIN_BPM, MAX_BPM = 20, 400
HELP = "up/down ±1 · right/left ±5 · t tap · space pause · n next · q quit"


def clamp(bpm):
    return max(MIN_BPM, min(MAX_BPM, bpm))


def run(cfg, view):
    bpm = clamp(cfg["bpm"])
    beats = max(1, cfg["beats"])
    limit = None if cfg["for"] in (None, "forever") else cfg["for"]
    clock = term.Clock()
    count = 0  # beats played since start or resume
    played = 0
    last_beat_at = None
    next_at = time.monotonic()
    taps = []
    outcome = nav = None

    def state():
        return SimpleNamespace(
            tool="metronome", now=time.monotonic(), label=cfg["label"] or "", bpm=bpm, beats=beats,
            count=count, pos=(count - 1) % beats if count and not clock.paused else -1,
            last_beat_at=last_beat_at, interval=60.0 / bpm, paused=clock.paused,
            elapsed=clock.elapsed, outcome=outcome, nav=nav,
        )

    with term.Keys() as keys:
        view.open("metronome", HELP if keys.interactive else None)
        try:
            while True:
                now = time.monotonic()
                if limit is not None and clock.elapsed >= limit:
                    outcome = "done"
                    break
                if not clock.paused and now >= next_at:
                    term.play("Tink" if count % beats == 0 and beats > 1 else "Pop", cfg["sound"])
                    count += 1
                    played += 1
                    last_beat_at = now
                    next_at += 60.0 / bpm
                    if next_at < now:  # fell behind (e.g. laptop slept): resync
                        next_at = now + 60.0 / bpm
                    view.event("beat", state())
                s = state()
                view.frame(s)
                wait = None if clock.paused else next_at - time.monotonic()
                end = None if limit is None or clock.paused else limit - clock.elapsed
                key = keys.read(term.soonest(wait, end, view.next_frame(s)))
                if key is None:
                    continue
                if key in term.NAV:
                    nav, outcome = term.NAV[key], "stopped"
                    break
                old = bpm
                if key == "space":
                    clock.toggle()
                    count, last_beat_at, next_at = 0, None, time.monotonic()
                    view.event("pause" if clock.paused else "start", state())
                elif key in ("up", "+", "="):
                    bpm = clamp(bpm + 1)
                elif key in ("down", "-", "_"):
                    bpm = clamp(bpm - 1)
                elif key == "right":
                    bpm = clamp(bpm + 5)
                elif key == "left":
                    bpm = clamp(bpm - 5)
                elif key == "t":
                    now = time.monotonic()
                    taps = [t for t in taps if now - t < 2.5] + [now]
                    if len(taps) >= 2:
                        gaps = [b - a for a, b in zip(taps, taps[1:])]
                        bpm = clamp(int(round(60.0 * len(gaps) / sum(gaps))))
                if bpm != old:
                    next_at += 60.0 / bpm - 60.0 / old
                    view.event("change", state())
        except KeyboardInterrupt:
            nav, outcome = "quit", "stopped"
        finally:
            view.close(state())
            clock.pause()
    return {"tool": "metronome", "label": cfg["label"] or "", "outcome": outcome, "nav": nav,
            "elapsed": clock.elapsed, "bpm": bpm, "beats": played}
