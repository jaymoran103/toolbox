import subprocess
import sys
import unittest
from pathlib import Path

from timetools.durations import parse
from timetools.fireworks import Rand, plan, stream
from timetools.spec import parse_range, parse_rate

ROOT = str(Path(__file__).resolve().parent.parent)


class ParseTest(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(parse_range("5", int), [5, 5])
        self.assertEqual(parse_range("10-30", int), [10, 30])
        self.assertEqual(parse_range("30s-1m", parse), [30, 60])
        self.assertEqual(parse_range("1-2m", parse), [60, 120])
        for bad in ("30-10", "-5", "a-b"):
            with self.assertRaises(ValueError, msg=bad):
                parse_range(bad, int)

    def test_rates(self):
        self.assertEqual(parse_rate("2"), [2, 2])
        self.assertEqual(parse_rate("2/s"), [2, 2])
        self.assertEqual(parse_rate("30/m"), [0.5, 0.5])
        self.assertEqual(parse_rate("60-120/h"), [60 / 3600, 120 / 3600])
        with self.assertRaises(ValueError):
            parse_rate("2/d")


class PlanTest(unittest.TestCase):
    def test_count(self):
        span, times = plan((10, 10), count=(7, 7), rng=Rand(1))
        self.assertEqual((span, len(times)), (10, 7))
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(0 <= t <= 10 for t in times))

    def test_rate_times_span(self):
        span, times = plan((20, 20), rate=(0.5, 0.5), rng=Rand(1))
        self.assertEqual(len(times), 10)

    def test_ranges_stay_inside(self):
        rng = Rand(2)
        for _ in range(200):
            span, times = plan((5, 9), count=(3, 6), rng=rng)
            self.assertTrue(5 <= span <= 9 and 3 <= len(times) <= 6)

    def test_even_and_seed(self):
        _, times = plan((4, 4), count=(4, 4), spread="even")
        self.assertEqual(times, [0.5, 1.5, 2.5, 3.5])
        self.assertEqual(plan((1, 9), count=(1, 50), rng=Rand(9)),
                         plan((1, 9), count=(1, 50), rng=Rand(9)))


class ClusterTest(unittest.TestCase):
    def test_clumps_stay_inside_the_span(self):
        span, times = plan((10, 10), count=(4, 4), rng=Rand(3), cluster=(2, 3), within=1.5)
        self.assertTrue(8 <= len(times) <= 12)
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(0 <= t <= span for t in times))

    def test_forever_stream_is_sorted_and_keeps_going(self):
        it = stream((2, 2), rng=Rand(1), cluster=(2, 3), within=1.0)
        times = [next(it) for _ in range(200)]
        self.assertEqual(times, sorted(times))
        self.assertGreater(times[-1], 30)


class RandTest(unittest.TestCase):
    def test_known_stream(self):
        # mulberry32(1) reference values, also checked by web/test.mjs
        r = Rand(1)
        self.assertEqual([round(r(), 10) for _ in range(3)], [0.6270739406, 0.0027357212, 0.52744704])


class HeadlessTest(unittest.TestCase):
    def test_runs_without_a_terminal(self):
        out = subprocess.run([sys.executable, "-m", "timetools", "fireworks", "0.6s", "-n", "5", "--seed", "1"],
                             cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.count("✦ burst"), 5)
        self.assertIn("5 of 5 bursts", out.stdout)


if __name__ == "__main__":
    unittest.main()
