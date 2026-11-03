"""Parse and format durations."""

import math
import re

_UNITS = {"h": 3600, "m": 60, "s": 1}
_PART = re.compile(r"(\d+(?:\.\d+)?)([hms])")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def parse(text):
    """Turn '90', '90s', '5m', '1h30m', '2.5m', '1:30' or '1:02:03' into seconds."""
    t = text.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("empty duration")
    if ":" in t:
        parts = t.split(":")
        if len(parts) > 3 or not all(_NUMBER.fullmatch(p) for p in parts):
            raise ValueError("can't read duration: %r" % text)
        total = 0.0
        for p in parts:
            total = total * 60 + float(p)
        return total
    if _NUMBER.fullmatch(t):
        return float(t)
    total, pos = 0.0, 0
    for m in _PART.finditer(t):
        if m.start() != pos:
            break
        total += float(m.group(1)) * _UNITS[m.group(2)]
        pos = m.end()
    if pos == 0 or pos != len(t):
        raise ValueError("can't read duration: %r" % text)
    return total


def fmt(seconds, decimals=0, ceil=False):
    """Format seconds as MM:SS or H:MM:SS, with optional fractional digits.

    ceil=True rounds up to the next whole second, which reads right for a
    countdown: it shows 00:01 until time is fully up.
    """
    seconds = max(0.0, seconds)
    if decimals:
        scale = 10 ** decimals
        whole, frac = divmod(int(seconds * scale), scale)
    else:
        whole, frac = (math.ceil(seconds) if ceil else int(seconds)), None
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    out = "%d:%02d:%02d" % (h, m, s) if h else "%02d:%02d" % (m, s)
    if frac is not None:
        out += ".%0*d" % (decimals, frac)
    return out
