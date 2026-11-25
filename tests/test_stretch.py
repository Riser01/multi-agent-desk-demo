"""Optional stretch checks: a real LangGraph interrupt() approval gate with a checkpointer (stretch.py).

Run with: python check.py stretch
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import desk as desk_mod
import llm
import stretch
from fakes import record_graph_configs

SEED = os.path.join(ROOT, "data", "seed.json")


class StretchTests(unittest.TestCase):
    def setUp(self):
        self.desk = desk_mod.load_desk(SEED)
        self.model = llm.make_model()
        self.graph = stretch.build_gate_graph(self.desk, self.model)

    def test_risky_plan_pauses_and_changes_nothing(self):
        """Stretch: a delete pauses at the gate (status 'waiting'); the desk is untouched while paused."""
        first = stretch.start(self.graph, "Delete the dentist task.", "t1")
        self.assertEqual(first["status"], "waiting")
        self.assertIn("delete_task", str(first["question"]))
        self.assertTrue(any(t["id"] == 3 for t in self.desk.tasks))

    def test_resume_no_or_blank_keeps_the_task(self):
        """Stretch: resuming with 'n' or a blank answer denies the delete (status done-with-denials)."""
        for thread, answer in (("t-no", "n"), ("t-blank", "")):
            stretch.start(self.graph, "Delete the dentist task.", thread)
            final = stretch.resume(self.graph, thread, answer)
            self.assertEqual(final["status"], "done-with-denials")
            self.assertTrue(any(t["id"] == 3 for t in self.desk.tasks))

    def test_resume_yes_deletes_without_planning_again(self):
        """Stretch: resuming with 'y' on the same thread deletes the task; the planner is not called a second time."""
        stretch.start(self.graph, "Delete the dentist task.", "t-yes")
        final = stretch.resume(self.graph, "t-yes", "y")
        self.assertEqual(final["status"], "done")
        self.assertFalse(any(t["id"] == 3 for t in self.desk.tasks))
        self.assertEqual(self.model.calls, 1)

    def test_safe_plan_never_pauses(self):
        """Stretch: a plan with no delete/cancel runs straight through without pausing."""
        res = stretch.start(self.graph, "Add File taxes.", "t-add")
        self.assertEqual(res["status"], "done")
        self.assertTrue(any(t["text"] == "File taxes" for t in self.desk.tasks))

    def test_invoke_passes_thread_id_and_recursion_limit(self):
        """Stretch: every invoke passes a thread_id and a small recursion_limit."""
        with record_graph_configs() as configs:
            stretch.start(self.graph, "Delete the dentist task.", "t-cfg")
            stretch.resume(self.graph, "t-cfg", "n")
        self.assertEqual(len(configs), 2)
        for config in configs:
            self.assertEqual(config["configurable"]["thread_id"], "t-cfg")
            self.assertLessEqual(config["recursion_limit"], 50)
