"""Full screen: big gradient digits, smooth bars, a swinging pendulum.

Draws on the terminal's alternate screen, so scrollback stays as it was.
Honours NO_COLOR, and uses 24-bit color when COLORTERM says it can.
"""

import math
import os
import shutil
import sys
import time

from timetools.durations import fmt
from timetools.views import base

FRAME = 1 / 30.0

ALT_ON, ALT_OFF = "\x1b[?1049h", "\x1b[?1049l"
HIDE, SHOW = "\x1b[?25l", "\x1b[?25h"
RESET, DIM = "\x1b[0m", "\x1b[2m"

GLYPHS = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": (" ██", "  █", "  █", "  █", "  █"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", " ██", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    ":": (" ", "█", " ", "█", " "),
    ".": (" ", " ", " ", " ", "█"),
    "-": ("   ", "   ", "███", "   ", "   "),
}
PARTIAL = " ▏▎▍▌▋▊▉"
BRAILLE = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))  # [row][col] dot bits

CYAN = (0, 220, 255)
VIOLET = (150, 90, 255)
PINK = (255, 70, 170)
GREEN = (70, 230, 130)
AMBER = (255, 200, 60)
RED = (255, 70, 80)
WHITE = (240, 240, 255)
GREY = (120, 120, 145)
DARK = (55, 55, 72)


def mix(a, b, t):
    t = min(1.0, max(0.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def ramp(stops, t):
    t = min(1.0, max(0.0, t)) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    return mix(stops[i], stops[i + 1], t - i)


def spaced(text):
    return " ".join(text.upper()) if len(text) <= 24 else text


class Paint:
    def __init__(self):
        self.off = bool(os.environ.get("NO_COLOR"))
        self.true = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
        self._cache = {}

    def __call__(self, rgb):
        code = self._cache.get(rgb)
        if code is None:
            if len(self._cache) > 4096:
                self._cache.clear()
            if self.off:
                code = ""
            elif self.true:
                code = "\x1b[38;2;%d;%d;%dm" % rgb
            else:
                r, g, b = (int(round(c / 255.0 * 5)) for c in rgb)
                code = "\x1b[38;5;%dm" % (16 + 36 * r + 6 * g + b)
            self._cache[rgb] = code
        return code


class Row:
    """One screen line. Tracks its visible width and skips repeated color codes."""

    __slots__ = ("parts", "width", "code")

    def __init__(self, code="", text=""):
        self.parts, self.width, self.code = [], 0, None
        if text:
            self.add(code, text)

    def add(self, code, text):
        if code and code != self.code:
            self.parts.append(code)
            self.code = code
        self.parts.append(text)
        self.width += len(text)
        return self

    def render(self):
        return "".join(self.parts) + RESET


class View(base.View):
    needs_tty = True

    def __init__(self, style=None):
        base.View.__init__(self, style)
        self.fx = None
        self.p = Paint()
        self.out = sys.stdout
        self.size = None
        self.last = None
        self.help = None
        self.lap_at = -9.0
        self.count_n = None
        self.count_at = -9.0
        self.count_delta = 0

    # contract

    def open(self, tool, help):
        self.help = help
        self.out.write(ALT_ON + HIDE + "\x1b[2J")
        self.out.flush()

    def next_frame(self, s):
        if s.tool == "counter":
            return FRAME if s.now - self.count_at < 0.6 else None
        if s.tool == "metronome" and s.paused:
            return None
        if s.tool == "fireworks":
            return self._show(s).next_frame(s, FRAME)
        return FRAME

    def frame(self, s):
        cols, lines = shutil.get_terminal_size()
        rows = getattr(self, "_" + s.tool)(s, cols, lines)
        self._draw(rows, cols, lines)

    def event(self, name, s):
        if name == "lap":
            self.lap_at = s.now
        elif name == "burst":
            self._show(s).launch()

    def close(self, s):
        self.abort()
        if s.tool == "stopwatch":
            for i in range(len(s.laps)):
                self.out.write(base.lap_line(s.laps, i) + "\n")
        self.out.write(base.summary(s) + "\n")
        self.out.flush()

    def abort(self):
        self.out.write(RESET + ALT_OFF + SHOW)
        self.out.flush()

    # screen

    def _draw(self, rows, cols, lines):
        clear = ""
        if (cols, lines) != self.size:
            self.size, self.last, clear = (cols, lines), None, "\x1b[2J"
        body = lines - 1 if self.help else lines
        rows = [r for r in rows if r.width <= cols][:body]
        top = (body - len(rows)) // 2
        screen = [""] * top + [" " * ((cols - r.width) // 2) + r.render() for r in rows]
        screen += [""] * (body - len(screen))
        if self.help:
            hint = self.help[:cols]
            screen.append(" " * ((cols - len(hint)) // 2) + DIM + hint + RESET)
        frame = clear + "\x1b[H" + "\x1b[K\r\n".join(screen) + "\x1b[K"
        if frame != self.last:
            self.out.write(frame)
            self.out.flush()
            self.last = frame

    def _digits(self, text, cols, color_at):
        """Big block digits plus a dim reflection row. Falls back to plain text."""
        glyphs = [GLYPHS.get(ch, ("  ",) * 5) for ch in text]
        for scale in (2, 1):
            width = sum(len(g[0]) for g in glyphs) * scale + (len(glyphs) - 1) * scale
            if width <= cols - 4:
                break
        else:
            return [Row(self.p(color_at(0.5)), text)]
        rows = []
        for r in range(5):
            row, x = Row(), 0
            for gi, g in enumerate(glyphs):
                if gi:
                    row.add("", " " * scale)
                    x += scale
                for ch in g[r]:
                    for _ in range(scale):
                        if ch == " ":
                            row.add("", " ")
                        else:
                            row.add(self.p(color_at(x / max(1.0, width - 1.0))), "█")
                        x += 1
            rows.append(row)
        shine = Row()
        for part in rows[-1].parts:
            if part.startswith("\x1b"):
                continue
            shine.add(self.p(DARK), "".join("▀" if c == "█" else " " for c in part))
        rows.append(shine)
        return rows

    def _bar(self, frac, width, stops, empty="░"):
        frac = min(1.0, max(0.0, frac))
        cells = frac * width
        full = int(cells)
        part = int((cells - full) * len(PARTIAL))
        row = Row()
        for x in range(width):
            c = self.p(ramp(stops, x / max(1.0, width - 1.0)))
            if x < full:
                row.add(c, "█")
            elif x == full and part:
                row.add(c, PARTIAL[part])
            else:
                row.add(self.p(DARK), empty)
        return row

    # tools

    def _stopwatch(self, s, cols, lines):
        p = self.p
        blink = int(s.now * 2) % 2 == 0
        if s.paused:
            title = Row(p(PINK if blink else GREY), "P A U S E D")
            color_at = lambda t: GREY
        else:
            title = Row(p(GREY), spaced(getattr(s, "label", "") or "stopwatch"))
            color_at = lambda t: ramp((CYAN, VIOLET, PINK), t)
        rows = [title, Row()]
        rows += self._digits(fmt(s.elapsed, 2), cols, color_at)
        rows.append(Row())
        width = min(60, cols - 4)
        sweep = self._bar((s.elapsed % 60) / 60.0, width, (CYAN, VIOLET, PINK), empty="─")
        rows.append(sweep)
        if s.laps:
            rows.append(Row())
            split = base.splits(s.laps)
            best, worst = min(split), max(split)
            flash = s.now - self.lap_at < 0.4
            for i in range(len(s.laps) - 1, max(-1, len(s.laps) - 7), -1):
                color = GREY
                if len(split) > 1 and split[i] == best:
                    color = GREEN
                elif len(split) > 1 and split[i] == worst:
                    color = RED
                if flash and i == len(s.laps) - 1:
                    color = WHITE
                rows.append(Row(p(color), "lap %2d    %s    %s" % (i + 1, fmt(split[i], 2), fmt(s.laps[i], 2))))
        return rows

    def _timer(self, s, cols, lines):
        p = self.p
        frac = 1 - s.left / s.total
        if s.outcome == "done":
            on = int(s.now * 4) % 2 == 0
            rows = [Row(p(RED if on else WHITE), "T I M E ' S   U P"), Row()]
            rows += self._digits(fmt(0), cols, lambda t: RED if on else WHITE)
            if s.label:
                rows += [Row(), Row(p(WHITE), s.label)]
            return rows
        tone = ramp((GREEN, AMBER, RED), frac)
        if s.paused:
            tone = GREY
        elif s.left <= 10:
            tone = mix(tone, WHITE, 0.35 * (1 + math.sin(s.now * 2 * math.pi)))
        rows = [Row(p(GREY), spaced(getattr(s, "label", "") or "timer")), Row()]
        rows += self._digits(fmt(s.left, ceil=True), cols, lambda t: mix(WHITE, tone, 0.55 + 0.45 * t))
        rows.append(Row())
        bar = self._bar(frac, min(56, cols - 10), (GREEN, AMBER, RED))
        rows.append(bar.add(p(GREY), "  %3d%%" % int(frac * 100)))
        rows.append(Row())
        if s.paused:
            blink = int(s.now * 2) % 2 == 0
            rows.append(Row(p(AMBER if blink else GREY), "paused"))
        else:
            rows.append(Row(p(GREY), "ends at %s" % time.strftime("%H:%M:%S", time.localtime(s.ends_at))))
        return rows

    def _beat(self, s):
        """(phase through the current beat 0..1, flash strength 0..1)."""
        if s.paused or s.last_beat_at is None:
            return 0.0, 0.0
        phase = min(1.0, (s.now - s.last_beat_at) / s.interval)
        return phase, max(0.0, 1 - phase / 0.3)

    def _metronome(self, s, cols, lines):
        p = self.p
        phase, flash = self._beat(s)
        accent = s.beats > 1 and s.pos == 0
        hit = PINK if accent else CYAN
        rows = [Row(p(GREY), spaced(getattr(s, "label", "") or "metronome")), Row()]
        rows += self._digits(str(s.bpm), cols, lambda t: mix(ramp((VIOLET, PINK), t), WHITE, flash * 0.5))
        rows.append(Row(p(GREY), "b p m"))
        rows.append(Row())
        rows += self._pendulum(s, phase, mix(WHITE, hit, flash), max(3, min(8, lines - 17)))
        rows.append(Row())
        rows += self._boxes(s, phase, cols)
        if s.paused:
            rows += [Row(), Row(p(AMBER), "paused")]
        return rows

    def _pendulum(self, s, phase, bob_color, h):
        """A braille-dot pendulum: 2x4 dots per cell, with a fading motion trail."""
        p = self.p
        swing = math.radians(30)
        length = h * 4 - 3
        w = int(math.ceil(length * math.sin(swing))) + 3
        px_w, px_h = w * 2, h * 4
        cx, cy = px_w // 2, px_h - 1
        cells = {}  # (col, row) -> [dot bits, layer]

        def plot(x, y, layer):
            x, y = int(round(x)), int(round(y))
            if 0 <= x < px_w and 0 <= y < px_h:
                cell = cells.setdefault((x // 2, y // 4), [0, -1])
                cell[0] |= BRAILLE[y % 4][x % 2]
                cell[1] = max(cell[1], layer)

        def draw(ph, arm_layer, bob_layer):
            if s.paused or s.last_beat_at is None:
                theta = 0.0
            else:
                theta = (1 if s.count % 2 else -1) * math.cos(math.pi * ph) * swing
            bx, by = cx + length * math.sin(theta), cy - length * math.cos(theta)
            if arm_layer is not None:
                steps = length * 2
                for i in range(steps + 1):
                    plot(cx + (bx - cx) * i / steps, cy + (by - cy) * i / steps, arm_layer)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if dx * dx + dy * dy <= 4.5:
                        plot(bx + dx, by + dy, bob_layer)

        if not s.paused and s.last_beat_at is not None:
            for lag in (0.16, 0.08):
                draw(phase - lag, None, 0)
        draw(phase, 1, 2)
        colors = (DARK, GREY, bob_color)
        rows = []
        for r in range(h):
            row = Row()
            for c in range(w):
                cell = cells.get((c, r))
                if cell:
                    row.add(p(colors[cell[1]]), chr(0x2800 + cell[0]))
                else:
                    row.add("", " ")
            rows.append(row)
        mid = cx // 2
        rows.append(Row(p(DARK), "▔" * mid + "▲" + "▔" * (w - mid - 1)))
        return rows

    def _boxes(self, s, phase, cols):
        p = self.p
        box = 4 if s.beats * 6 <= cols - 4 else 2
        gap = 2 if box == 4 else 1
        if s.beats * (box + gap) > cols - 4:
            return [Row(p(GREY), base.status(s).split("  ", 1)[1])]
        row = Row()
        for i in range(s.beats):
            if i:
                row.add("", " " * gap)
            if i == s.pos:
                lit = PINK if i == 0 and s.beats > 1 else CYAN
                row.add(p(mix(lit, DARK, phase * 0.75)), "█" * box)
            else:
                row.add(p(DARK), "█" * box)
        return [row, row]

    def _show(self, s):
        if self.fx is None:
            from timetools.views import fireworks_fx  # only fireworks pays for this
            self.fx = fireworks_fx.Show(self.style, s.seed)
        return self.fx

    def _fireworks(self, s, cols, lines):
        p = self.p
        body = lines - 1 if self.help else lines
        hud = base.status(s)
        if s.done:
            hud = "✦ %d" % s.fired + ("" if s.count is None else "/%d" % s.count)
        top = Row(p(AMBER if s.paused else GREY), hud[:cols])
        top.add("", " " * (cols - top.width))
        return [top] + self._show(s).draw(s, cols, max(1, body - 1), p, Row)

    def _counter(self, s, cols, lines):
        p = self.p
        if self.count_n is None:
            self.count_n = s.n
        if s.n != self.count_n:
            self.count_delta, self.count_n, self.count_at = s.n - self.count_n, s.n, s.now
        glow = max(0.0, 1 - (s.now - self.count_at) / 0.5)
        rows = [Row(p(GREY), spaced(getattr(s, "label", "") or "counter"))]
        if glow:
            up = self.count_delta > 0
            rows.append(Row(p(mix(DARK, GREEN if up else RED, glow)), "%+d" % self.count_delta))
        else:
            rows.append(Row())
        rows += self._digits(str(s.n), cols, lambda t: mix(ramp((CYAN, VIOLET, PINK), t), WHITE, glow * 0.7))
        rows.append(Row())
        marks = abs(s.n)
        if 0 < marks <= 60:
            row = Row()
            for i in range(marks):
                if i and i % 5 == 0:
                    row.add("", " ")
                row.add(p(ramp((CYAN, VIOLET, PINK), i / 60.0) if s.n > 0 else RED), "▮")
            rows.append(row)
        return rows
