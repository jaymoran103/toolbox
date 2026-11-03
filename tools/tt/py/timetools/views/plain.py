"""One status line. The default, and the only view the baseline path imports."""

import sys

from timetools import term
from timetools.views import base

REFRESH = {"stopwatch": 0.05, "timer": 0.1, "fireworks": 0.1}


class View(base.View):
    def open(self, tool, help):
        sys.stdout.write(term.HIDE_CURSOR)
        if help:
            term.line(help)

    def next_frame(self, s):
        if getattr(s, "done", False):
            return None
        return REFRESH.get(s.tool)

    def frame(self, s):
        term.status(base.status(s))

    def event(self, name, s):
        if name == "lap":
            term.line(base.lap_line(s.laps, len(s.laps) - 1))
        elif name == "change" and s.tool == "stopwatch":
            term.line("reset")
        elif name == "burst":
            term.line(base.burst_line(s))

    def close(self, s):
        term.status(base.summary(s))
        self.abort()

    def abort(self):
        sys.stdout.write(term.SHOW_CURSOR + "\n")
        sys.stdout.flush()
