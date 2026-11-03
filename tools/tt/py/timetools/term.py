"""Terminal helpers: raw key reading, line output, sounds."""

import os
import select
import shutil
import subprocess
import sys
import termios
import time
import tty

HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR_LINE = "\r\x1b[2K"

_ESCAPES = {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left"}


class Keys:
    """Context manager that reads single keypresses without Enter.

    When stdin is not a terminal, read() just sleeps and returns None, so
    tools still run (and stop on Ctrl-C) in pipes and scripts.
    """

    def __init__(self):
        self.fd = sys.stdin.fileno() if sys.stdin.isatty() else None
        self._saved = None

    @property
    def interactive(self):
        return self.fd is not None

    def __enter__(self):
        if self.fd is not None:
            self._saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def __exit__(self, *exc):
        if self._saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._saved)
        return False

    def read(self, timeout=None):
        """Return a key name ('q', 'space', 'enter', 'up', ...) or None on timeout."""
        if timeout is not None:
            timeout = max(0.0, timeout)
        if self.fd is None:
            time.sleep(60 if timeout is None else timeout)
            return None
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return None
        ch = os.read(self.fd, 1)
        if ch == b"\x1b":
            ready, _, _ = select.select([self.fd], [], [], 0.01)
            if ready:
                return _ESCAPES.get(os.read(self.fd, 2), "esc")
            return "esc"
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b" ":
            return "space"
        if ch == b"\x7f":
            return "backspace"
        return ch.decode(errors="ignore")


NAV = {"n": "next", "b": "back", "q": "quit", "esc": "quit"}  # the same keys in every tool


class Clock:
    """Elapsed time that stops while paused."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.start, self.paused_at = time.monotonic(), None

    @property
    def paused(self):
        return self.paused_at is not None

    @property
    def elapsed(self):
        return (self.paused_at if self.paused_at is not None else time.monotonic()) - self.start

    def pause(self):
        if self.paused_at is None:
            self.paused_at = time.monotonic()

    def resume(self):
        if self.paused_at is not None:
            self.start += time.monotonic() - self.paused_at
            self.paused_at = None

    def toggle(self):
        self.resume() if self.paused else self.pause()


def soonest(*waits):
    """The shortest of several wait times, ignoring None. None if all are None."""
    waits = [w for w in waits if w is not None]
    return min(waits) if waits else None


def status(text):
    """Redraw the current line."""
    sys.stdout.write(CLEAR_LINE + text)
    sys.stdout.flush()


def line(text):
    """Print a permanent line above the status line."""
    sys.stdout.write(CLEAR_LINE + text + "\n")
    sys.stdout.flush()


def bar(fraction, width=24):
    fraction = min(1.0, max(0.0, fraction))
    filled = int(round(fraction * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


_AFPLAY = shutil.which("afplay") if sys.platform == "darwin" else None
_REMOTE = bool(os.environ.get("SSH_CONNECTION"))


def play(name, on=True):
    """Play a macOS system sound by name. Over SSH, or without afplay, ring
    the terminal bell, which sounds on the machine you are sitting at."""
    if not on:
        return
    path = "/System/Library/Sounds/%s.aiff" % name
    if _AFPLAY and not _REMOTE and os.path.exists(path):
        subprocess.Popen([_AFPLAY, path], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    sys.stdout.write("\a")
    sys.stdout.flush()

