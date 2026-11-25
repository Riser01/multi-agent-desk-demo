"""AM-2 Your turn (optional exercise): validate_plan also refuses a step that repeats an earlier identical step.

Run with: python check.py 2 your-turn
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import safety


class Phase2YourTurnTests(unittest.TestCase):
    def test_duplicate_identical_step_is_refused_with_its_step_number(self):
        """AM-2 Your turn: two steps with the same tool and same args are refused, and the reason names step 2."""
        reasons = safety.validate_plan([{"tool": "list_tasks", "args": {}}, {"tool": "list_tasks", "args": {}}], "Show my list")
        self.assertTrue(reasons, "a repeated identical step must be refused")
        self.assertIn("2", " ".join(reasons))

    def test_same_tool_with_different_args_is_allowed(self):
        """AM-2 Your turn: the same tool with different args (add A, add B) is still allowed."""
        ok = safety.validate_plan([{"tool": "add_task", "args": {"text": "A"}}, {"tool": "add_task", "args": {"text": "B"}}], "Add A and B")
        self.assertEqual(ok, [])
