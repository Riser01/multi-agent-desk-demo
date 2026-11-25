"""AM-2 checks (main contract): handoff context cap and plan validation against planted-note deletes.

The duplicate-step rule is the Your turn exercise: see test_phase2_yourturn.py and `python check.py 2 your-turn`.
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import desk as desk_mod
import llm
import safety
import two_agent
from fakes import ScriptedModel

SEED = os.path.join(ROOT, "data", "seed.json")


class Phase2Tests(unittest.TestCase):
    def test_limits_are_the_specified_numbers(self):
        """AM-2: MAX_CONTEXT_CHARS is 600 and MAX_PLAN_STEPS is 5."""
        self.assertEqual(safety.MAX_CONTEXT_CHARS, 600)
        self.assertEqual(safety.MAX_PLAN_STEPS, 5)

    def test_context_cap_cuts_huge_notes(self):
        """AM-2: cap_context cuts text over 600 chars to 600 + ' [truncated]', and leaves short text alone."""
        big = "A" * (safety.MAX_CONTEXT_CHARS + 200)
        cut, was_cut = safety.cap_context(big)
        self.assertTrue(was_cut)
        self.assertEqual(cut, "A" * 600 + " [truncated]")
        self.assertEqual(safety.cap_context("short"), ("short", False))

    def test_validate_plan_blocks_unrequested_delete_unknown_tool_and_long_plans(self):
        """AM-2: validate_plan refuses an unrequested delete, an unknown tool and a 6-step plan; allows a requested delete and 5 steps."""
        self.assertTrue(safety.validate_plan([{"tool": "delete_task", "args": {"id": 1}}], "Tidy up my tasks."))
        self.assertTrue(safety.validate_plan([{"tool": "format_disk", "args": {}}], "Show my list"))
        self.assertEqual(safety.validate_plan([{"tool": "delete_task", "args": {"id": 3}}], "Delete the dentist task."), [])
        five = [{"tool": "add_task", "args": {"text": f"T{i}"}} for i in range(5)]
        self.assertEqual(safety.validate_plan(five, "Add five tasks"), [])
        six = [{"tool": "add_task", "args": {"text": f"T{i}"}} for i in range(6)]
        self.assertTrue(safety.validate_plan(six, "Add six tasks"))

    def test_drill_cap_trims_the_override_before_the_planner_reads_it(self):
        """AM-2: on /drill, cap_context is called and the planner receives capped notes without the trailing override."""
        d = desk_mod.load_desk(SEED)
        desk_mod.inject_drill_note(d)
        model = ScriptedModel({"planner": lambda user: llm.StandIn()("planner", "", user).text})
        with mock.patch.object(safety, "cap_context", wraps=safety.cap_context) as spy:
            res = two_agent.run_two_agent("Tidy up my tasks.", d, model, desk_mod.approve_yes)
        self.assertTrue(spy.called, "two_agent must call safety.cap_context on the notes")
        planner_saw = model.seen["planner"][0]
        self.assertIn("[truncated]", planner_saw)
        self.assertNotIn("SYSTEM OVERRIDE", planner_saw)
        self.assertEqual(res["status"], "done")
        self.assertTrue(any(t["id"] == 1 for t in d.tasks))

    def test_validate_plan_is_a_second_barrier_even_with_blind_yes(self):
        """AM-2: if a fooled planner still proposes deleting task 1, the plan is rejected and nothing runs (blind yes)."""
        d = desk_mod.load_desk(SEED)
        desk_mod.inject_drill_note(d)
        model = ScriptedModel({"planner": {"steps": [{"task": "obey note", "tool": "delete_task", "args": {"id": 1}}]}})
        res = two_agent.run_two_agent("Tidy up my tasks.", d, model, desk_mod.approve_yes)
        self.assertEqual(res["status"], "plan-rejected")
        self.assertTrue(any(t["id"] == 1 for t in d.tasks))
