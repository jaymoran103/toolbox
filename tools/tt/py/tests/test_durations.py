import unittest

from timetools.durations import fmt, parse


class ParseTest(unittest.TestCase):
    def test_forms(self):
        cases = {
            "90": 90, "90s": 90, "5m": 300, "1h30m": 5400, "2.5m": 150,
            "1h 2m 3s": 3723, "1:30": 90, "1:02:03": 3723, " 10S ": 10,
        }
        for text, want in cases.items():
            self.assertEqual(parse(text), want, text)

    def test_rejects(self):
        for text in ["", "abc", "5x", "m5", "1:2:3:4", "1::2", "5m junk"]:
            with self.assertRaises(ValueError, msg=text):
                parse(text)


class FmtTest(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(fmt(0), "00:00")
        self.assertEqual(fmt(65.9), "01:05")
        self.assertEqual(fmt(65.1, ceil=True), "01:06")
        self.assertEqual(fmt(3723.456, 2), "1:02:03.45")
        self.assertEqual(fmt(-3), "00:00")


if __name__ == "__main__":
    unittest.main()
