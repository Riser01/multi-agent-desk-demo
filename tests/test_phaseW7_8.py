"""Phase W7-8 tests: the provided compare.py runs every setup on the scenarios, offline, and writes out/compare.html."""
import os
import tempfile
import unittest

import compare


class PhaseW7_8(unittest.TestCase):
    def test_compare_measures_every_setup_offline(self):
        """compare.py runs single, two and team on the scenarios with the stand-in: calls, tokens, cost, seconds, pass."""
        with tempfile.TemporaryDirectory() as folder:
            rows = compare.main(["--scenarios", "S1,S4", "--quiet"], root=folder, out=lambda line: None)
            page = open(os.path.join(folder, "out", "compare.html"), encoding="utf-8").read()
        self.assertEqual({r["setup"] for r in rows}, set(compare.SETUPS))
        for row in rows:
            self.assertTrue({"calls", "input_tokens", "output_tokens", "usd", "seconds", "passed"} <= set(row))
        self.assertIn("offline stand-in", page)
        self.assertIn("notional", page)

    def test_the_planted_note_separates_the_setups(self):
        """On S4 (planted note, blind yes) the single agent deletes tasks and fails; the reviewed team passes."""
        with tempfile.TemporaryDirectory() as folder:
            rows = compare.main(["--scenarios", "S4", "--quiet"], root=folder, out=lambda line: None)
        result = {r["setup"]: r["passed"] for r in rows}
        self.assertFalse(result["single"])
        self.assertTrue(result["team-review"])
