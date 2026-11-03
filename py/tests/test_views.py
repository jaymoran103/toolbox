import io
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from timetools import views
from timetools.views import base


def states(now=100.0):
    return [
        SimpleNamespace(tool="stopwatch", now=now, elapsed=75.5, laps=(30.0, 75.0), paused=False),
        SimpleNamespace(tool="stopwatch", now=now, elapsed=0.0, laps=(), paused=True),
        SimpleNamespace(tool="timer", now=now, total=60.0, left=8.2, label="tea", paused=False,
                        outcome=None, ends_at=0.0),
        SimpleNamespace(tool="timer", now=now, total=60.0, left=0.0, label="", paused=False,
                        outcome="done", ends_at=0.0),
        SimpleNamespace(label="", tool="metronome", now=now, bpm=120, beats=4, count=5, pos=0,
                        last_beat_at=now - 0.1, interval=0.5, paused=False),
        SimpleNamespace(label="", tool="metronome", now=now, bpm=60, beats=16, count=0, pos=-1,
                        last_beat_at=None, interval=1.0, paused=True),
        SimpleNamespace(tool="counter", now=now, n=-12, start=0, step=1, label="reps"),
        SimpleNamespace(tool="counter", now=now, n=123456789, start=0, step=1, label=""),
        SimpleNamespace(label="", tool="fireworks", now=now, elapsed=3.0, span=10.0, count=8, fired=2,
                        paused=False, done=False, seed=1),
        SimpleNamespace(label="tavern", tool="fireworks", now=now, elapsed=3.0, span=float("inf"), count=None,
                        fired=2, paused=False, done=False, seed=1),
    ]


class Boom(base.View):
    def frame(self, state):
        raise RuntimeError("boom")


class LoadTest(unittest.TestCase):
    def test_default_is_plain_and_unwrapped(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TIMETOOLS_VIEW", None)
            self.assertEqual(type(views.load()).__module__, "timetools.views.plain")

    def test_unknown(self):
        with self.assertRaises(views.ViewError):
            views.load("nope")

    def test_big_falls_back_without_tty(self):
        with mock.patch.object(sys.stdout, "isatty", return_value=False):
            self.assertEqual(type(views.load("big")).__module__, "timetools.views.plain")

    def test_module_path_and_file(self):
        self.assertIsInstance(views.load(__name__ + ":Boom"), views.Guarded)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("from timetools.views.base import View\n")
        try:
            self.assertIsInstance(views.load(f.name), views.Guarded)
        finally:
            os.unlink(f.name)

    def test_broken_view_hands_over_to_plain(self):
        v = views.Guarded(Boom(), "boom")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            v.open("timer", None)
            v.frame(states()[2])
            v.frame(states()[2])
            v.close(states()[2])
        self.assertIn("view 'boom' failed (RuntimeError: boom)", err.getvalue())
        self.assertIn("00:09", out.getvalue())


class RenderTest(unittest.TestCase):
    def test_every_view_draws_every_state(self):
        for name in ("plain", "big"):
            for cols, lines in ((100, 30), (40, 12), (12, 5)):
                view = views._resolve(name)()
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out), \
                        mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((cols, lines))):
                    view.out = out if hasattr(view, "out") else None
                    view.open("x", "help")
                    for s in states():
                        view.frame(s)
                        view.next_frame(s)
                    for i in range(40):  # a burst, then its sparks over time
                        s = states(100.0 + i * 0.05)[-1]
                        if i % 10 == 0:
                            view.event("burst", s)
                        view.frame(s)
                    view.close(states()[0])
                self.assertTrue(out.getvalue())


if __name__ == "__main__":
    unittest.main()
