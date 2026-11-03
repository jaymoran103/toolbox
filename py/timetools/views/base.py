"""The view contract, plus text every view can reuse.

A tool calls, in order: open() once, then frame() and next_frame() each time
it wakes, event() for one-off moments, and close() once on the way out.
Views draw. They never change tool state, and they must stay cheap: a frame
runs on the same thread that keeps time.

State is a plain object. Every state has `tool` and `now` (time.monotonic()).
  stopwatch  elapsed, laps (lap totals), paused
  timer      total, left, label, paused, ends_at (wall clock), outcome
             (None while running, then done, cancelled or interrupted)
  metronome  bpm, beats, count, pos (-1 if none), last_beat_at, interval, paused
  counter    n, start, step, label
  fireworks  elapsed, span, count, fired, paused, done, seed
Events: stopwatch "lap" and "reset", fireworks "burst".

A view gets a `style` dict from the tool's styling flags. Views read the
keys they know and ignore the rest.
"""

from timetools import term
from timetools.durations import fmt


class View:
    needs_tty = False  # True: fall back to plain when stdout is not a terminal

    def __init__(self, style=None):
        self.style = style or {}

    def open(self, tool, help):
        """Start drawing. help is a key hint line, or None when keys are off."""

    def frame(self, state):
        """Draw the current state."""

    def next_frame(self, state):
        """Seconds until this view wants another frame, or None for 'only on change'."""
        return None

    def event(self, name, state):
        """A one-off moment, such as a lap."""

    def close(self, state):
        """Stop drawing and leave the terminal as it was, plus a summary line."""

    def abort(self):
        """Restore the terminal after this view failed. No summary."""


def status(s):
    """One-line text for any state, led by its label when it has one."""
    text = _status(s)
    label = getattr(s, "label", "")
    if label and s.tool not in ("timer", "counter"):  # those two place the label themselves
        text = "%s  %s" % (label, text)
    return text


def _status(s):
    if s.tool == "stopwatch":
        cap = "  cap %s" % fmt(s.cap) if getattr(s, "cap", None) else ""
        return "%s  lap %d%s%s" % (fmt(s.elapsed, 2), len(s.laps) + 1, cap, "  paused" if s.paused else "")
    if s.tool == "timer":
        if s.outcome == "done":
            return ("done  %s  %s" % (fmt(s.total), s.label)).rstrip()
        bar = term.bar(1 - s.left / s.total)
        return "%s  %s  %s%s" % (fmt(s.left, ceil=True), bar, s.label, "  paused" if s.paused else "")
    if s.tool == "metronome":
        dots = " ".join("●" if i == s.pos else "○" for i in range(s.beats)) if s.beats > 1 else "●"
        return "%3d bpm  %s%s" % (s.bpm, dots, "  paused" if s.paused else "")
    if s.tool == "counter":
        return ("%s: %d" % (s.label, s.n)) if s.label else str(s.n)
    if s.tool == "fireworks":
        paused = "  paused" if s.paused else ""
        if s.count is None:
            return "✦ %d  %s%s" % (s.fired, fmt(s.elapsed), paused)
        return "✦ %d/%d  %s left%s" % (s.fired, s.count, fmt(s.span - s.elapsed, ceil=True), paused)
    return ""


def summary(s):
    """The line left on screen when a tool exits."""
    if s.tool == "stopwatch":
        if getattr(s, "outcome", None) == "dnf":
            return "DNF  over %s" % fmt(s.cap)
        return "total %s" % fmt(s.elapsed, 2)
    if s.tool == "timer":
        if s.outcome == "cancelled":
            return "cancelled with %s left" % fmt(s.left, ceil=True)
        if s.outcome == "interrupted":
            return "cancelled"
    if s.tool == "fireworks":
        of = "" if s.count is None else " of %d" % s.count
        return "fireworks: %d%s bursts in %s" % (s.fired, of, fmt(s.elapsed))
    return status(s)


def burst_line(s):
    of = "" if s.count is None else "/%d" % s.count
    return "✦ burst %d%s at %s" % (s.fired, of, fmt(s.elapsed, 2))


def splits(laps):
    return [b - a for a, b in zip((0.0,) + tuple(laps[:-1]), laps)]


def lap_line(laps, i):
    return "lap %2d  %s  total %s" % (i + 1, fmt(splits(laps)[i], 2), fmt(laps[i], 2))
