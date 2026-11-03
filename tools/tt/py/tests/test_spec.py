import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from timetools import runner, spec

PY = Path(__file__).resolve().parent.parent
CASES = json.loads((PY.parent / "spec" / "cases.json").read_text())


class ConformanceTest(unittest.TestCase):
    """The same cases run in web/test.mjs."""

    def test_lines(self):
        for case in CASES["parse"]:
            with self.subTest(line=case["line"]):
                if case["want"] is None:
                    self.assertRaises(spec.ParseError, spec.parse_line, case["line"])
                else:
                    self.assertEqual(spec.parse_line(case["line"]), case["want"])

    def test_texts(self):
        for case in CASES["text"]:
            with self.subTest(text=case["text"][:30]):
                if case["want"] is None:
                    self.assertRaises(spec.ParseError, spec.parse_text, case["text"])
                else:
                    got = [dict(b, steps=spec.expand(b)) for b in spec.parse_text(case["text"])]
                    self.assertEqual(got, case["want"])

    def test_scores(self):
        for case in CASES["score"]:
            results = [{"tool": "stopwatch", "label": "Solve %d" % i, "outcome": "dnf" if t is None else "done",
                        "elapsed": 120.0 if t is None else t} for i, t in enumerate(case["times"], 1)]
            self.assertEqual(runner.score(results, case["kind"]), case["want"])


class RunTest(unittest.TestCase):
    def tt(self, *args, stdin=None):
        return subprocess.run([sys.executable, "-m", "timetools", *args], cwd=PY, input=stdin,
                              capture_output=True, text=True, timeout=20)

    def test_sequence_runs_in_order_and_writes_results(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "runs.json"
            text = "[set]\n@repeat 2\nwait 0.1s --label 'Rest {n}'\nfireworks 0.2s -n 2 --seed 1 --label 'Show {n}'\n"
            r = self.tt("run", "-", "--out", str(out), stdin=text)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(out.read_text())
            self.assertEqual([x["label"] for x in data["results"]], ["Rest 1", "Show 1", "Rest 2", "Show 2"])
            self.assertEqual([x["outcome"] for x in data["results"]], ["done", "done", "done", "done"])

    def test_emit_writes_json_lines(self):
        r = self.tt("run", "fireworks 0.2s -n 3 --seed 2", "--emit", "-")
        events = [json.loads(line)["event"] for line in r.stdout.splitlines() if line.startswith("{")]
        self.assertEqual(events.count("burst"), 3)
        self.assertEqual(events[:2], ["step", "start"])
        self.assertEqual(events[-1], "summary")

    def test_capped_stopwatch_is_dnf_and_scored(self):
        r = self.tt("run", "@score times; stopwatch --cap 0.2s --label Solve")
        self.assertIn("Solve", r.stdout)
        self.assertIn("DNF", r.stdout)

    def test_errors_name_the_problem(self):
        r = self.tt("metronome", "999")
        self.assertEqual(r.returncode, 2)
        self.assertIn("bpm must be between", r.stderr)
        r = self.tt("run", "nosuchpreset")
        self.assertIn("no preset named", r.stderr)


if __name__ == "__main__":
    unittest.main()
