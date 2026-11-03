"""Fireworks particles for the big view. Imported only by the fireworks tool.

Motion is closed-form (drag plus gravity), so each spark is one tuple and
its trail is just its own past positions. Nothing is integrated per frame.
Drawing is braille dots: 2x4 dots per cell.
"""

import math
import random

from timetools.fireworks import Rand, resolve_style
from timetools.views.big import BRAILLE, DARK, WHITE, mix

NAMED = {
    "pink": (255, 70, 170), "cyan": (0, 220, 255), "gold": (255, 200, 60),
    "green": (70, 230, 130), "violet": (150, 90, 255), "red": (255, 70, 80),
    "blue": (70, 130, 255), "orange": (255, 140, 40), "white": (240, 240, 255),
}
TRAIL_GAP = 0.035  # seconds between trail points
FLASH = 0.12  # seconds a burst's flash lasts
MAX_SPARKS = 3000
ROCKET = (255, 190, 110)


def color(name):
    name = name.strip().lower()
    if name.startswith("#") and len(name) == 7:
        return tuple(int(name[i:i + 2], 16) for i in (1, 3, 5))
    return NAMED.get(name)


class Show:
    def __init__(self, style, seed):
        style = dict(style or {})
        opt = resolve_style(style.pop("palette", None), style)
        self.colors = [c for c in map(color, str(opt["colors"]).split(",")) if c] or [WHITE]
        self.children = max(1, int(opt["children"]))
        self.trail = max(0, int(opt["trail"]))
        self.length = max(0.2, float(opt["length"]))
        self.size = max(0.02, float(opt["size"]))
        self.gravity = float(opt["gravity"])
        self.crackle = max(0, int(opt["crackle"]))
        self.rocket = bool(opt["rocket"])
        self.rng = Rand(seed)  # launches: the same stream as the browser's canvas view
        self.twinkle = random.Random()
        self.clock = 0.0  # show time: stops while paused
        self.last = None
        self.pending = 0
        self.rockets = []  # (x, y0, apex, drift, born, rise, rgb)
        self.sparks = []  # (x, y, vx, vy, born, life, rgb, gen, k)
        self.flashes = []  # (x, y, born)

    def launch(self):
        self.pending += 1

    def alive(self):
        return self.pending or self.rockets or self.sparks or self.flashes

    def next_frame(self, s, frame):
        if s.paused:
            return None
        if self.alive():
            return frame
        return None if s.done else 0.25  # idle: only the clock line moves

    # simulation

    def _advance(self, s, pw, ph):
        if self.last is None:
            self.last = s.now
        if not s.paused:
            self.clock += min(0.1, max(0.0, s.now - self.last))
        self.last = s.now
        t, rng = self.clock, self.rng
        for _ in range(self.pending):
            rgb = rng.choice(self.colors)
            top = max(0.12, self.size * 0.9)  # keep the burst on screen
            x, apex = rng.uniform(0.15, 0.85) * pw, rng.uniform(top, max(top + 0.05, 0.45)) * ph
            if self.rocket:
                self.rockets.append((x, ph - 1, apex, rng.uniform(-0.04, 0.04) * pw, t, rng.uniform(0.6, 0.9), rgb))
            else:
                self._explode(x, apex, t, rgb, ph)
        self.pending = 0
        flying = []
        for r in self.rockets:
            if t - r[4] >= r[5]:
                self._explode(r[0] + r[3], r[2], r[4] + r[5], r[6], ph)
            else:
                flying.append(r)
        self.rockets = flying
        g = self._g(ph)
        alive = []
        for sp in self.sparks:
            if t - sp[4] < sp[5]:
                alive.append(sp)
            elif sp[7] == 0 and self.crackle:
                x, y = self._pos(sp, sp[5], g)
                k = 3.0 / (self.length * 0.35)
                for _ in range(self.crackle):
                    if len(alive) >= MAX_SPARKS:
                        break
                    a, v = rng.uniform(0, 2 * math.pi), self.size * ph * 0.12 * k * rng.uniform(0.5, 1.0)
                    alive.append((x, y, v * math.cos(a), v * math.sin(a), sp[4] + sp[5],
                                  self.length * 0.35, mix(sp[6], WHITE, 0.5), 1, k))
        self.sparks = alive
        self.flashes = [f for f in self.flashes if t - f[2] < FLASH]

    def _explode(self, x, y, born, rgb, ph):
        rng, n = self.rng, self.children
        k = 3.0 / self.length
        reach = self.size * ph * k
        for i in range(n):
            if len(self.sparks) >= MAX_SPARKS:
                break
            a = 2 * math.pi * i / n + rng.uniform(-0.15, 0.15)
            v = reach * rng.uniform(0.7, 1.0)
            shade = mix(rgb, WHITE, rng.uniform(0.0, 0.25))
            self.sparks.append((x, y, v * math.cos(a), v * math.sin(a), born,
                                self.length * rng.uniform(0.8, 1.1), shade, 0, k))
        self.flashes.append((x, y, born))

    def _g(self, ph):
        return self.gravity * 0.22 * ph

    @staticmethod
    def _pos(sp, age, g):
        k = sp[8]
        e = 1 - math.exp(-k * age)
        return sp[0] + sp[2] / k * e, sp[1] + (sp[3] - g / k) / k * e + g / k * age

    # drawing

    def draw(self, s, cols, rows, paint, Row):
        pw, ph = cols * 2, rows * 4
        self._advance(s, pw, ph)
        t, g = self.clock, self._g(ph)
        cells = {}

        def plot(x, y, bright, rgb):
            xi, yi = int(x), int(y)
            if 0 <= xi < pw and 0 <= yi < ph:
                key = (yi >> 2) * cols + (xi >> 1)
                bit = BRAILLE[yi & 3][xi & 1]
                cell = cells.get(key)
                if cell is None:
                    cells[key] = [bit, bright, rgb]
                else:
                    cell[0] |= bit
                    if bright > cell[1]:
                        cell[1], cell[2] = bright, rgb

        def line(a, b, bright, rgb):
            steps = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
            for i in range(steps + 1):
                f = i / steps
                plot(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, bright, rgb)

        for x, y, born in self.flashes:
            b = 1 - (t - born) / FLASH
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    if dx * dx + dy * dy <= 9:
                        plot(x + dx, y + dy, b, mix(DARK, WHITE, b))

        for x, y0, apex, drift, born, rise, rgb in self.rockets:
            pts = []
            for j in range(4):
                u = (t - born) / rise - j * 0.06
                if u < 0:
                    break
                pts.append((x + drift * u, y0 - (y0 - apex) * (1 - (1 - u) ** 2)))
            for j in range(1, len(pts)):
                b = 0.7 - 0.2 * j
                line(pts[j - 1], pts[j], b, mix(DARK, ROCKET, b))
            if pts:
                plot(pts[0][0], pts[0][1], 1.0, WHITE)

        flicker = self.twinkle.random
        for sp in self.sparks:
            age = t - sp[4]
            if age < 0:
                continue
            f = age / sp[5]
            if f > 0.6 and flicker() < 0.3:
                continue
            bright = (1 - f) ** 1.5
            head = mix(sp[6], WHITE, max(0.0, 0.7 - age * 4))
            prev = self._pos(sp, age, g)
            plot(prev[0], prev[1], bright, mix(DARK, head, bright))
            for j in range(1, self.trail + 1):
                a = age - j * TRAIL_GAP
                if a < 0:
                    break
                cur = self._pos(sp, a, g)
                b = bright * (1 - j / (self.trail + 1.0))
                line(prev, cur, b, mix(DARK, sp[6], b))
                prev = cur

        out = []
        for r in range(rows):
            row, blank, base_key = Row(), 0, r * cols
            for c in range(cols):
                cell = cells.get(base_key + c)
                if cell is None:
                    blank += 1
                    continue
                if blank:
                    row.add("", " " * blank)
                    blank = 0
                row.add(paint(cell[2]), chr(0x2800 + cell[0]))
            if blank:
                row.add("", " " * blank)
            out.append(row)
        return out
