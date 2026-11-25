"""AM-1 checks: Planner (no tools) -> structured handoff -> Executor with blocking delete gate."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import desk as desk_mod
import llm
import two_agent
from fakes import ScriptedModel, record_graph_configs

SEED = os.path.join(ROOT, "data", "seed.json")


class Phase1Tests(unittest.TestCase):
    def test_planner_and_executor_add_task_and_list(self):
        """AM-1: two_agent adds a task through the planner -> executor handoff, with exactly 1 model call (the planner)."""
        d = desk_mod.load_desk(SEED)
        model = llm.make_model()
        res = two_agent.run_two_agent("Add File taxes, then show me my list.", d, model, desk_mod.approve_no)
        self.assertEqual(res["status"], "done")
        self.assertTrue(any("File taxes" in t["text"] for t in d.tasks))
        self.assertEqual(model.calls, 1, "only the planner calls the model; the executor runs tools")

    def test_executor_still_gates_irreversible_deletes(self):
        """AM-1: a plan proposing delete_task is still stopped by the blocking [y/N] gate when human says no."""
        d = desk_mod.load_desk(SEED)
        res = two_agent.run_two_agent("Delete the dentist task.", d, llm.make_model(), desk_mod.approve_no)
        self.assertEqual(res["status"], "done-with-denials")
        self.assertTrue(any(t["id"] == 3 for t in d.tasks))

    def test_log_says_what_each_agent_sees(self):
        """AM-1: the log has one 'sees:' line for the planner and one for the executor."""
        lines = []
        two_agent.run_two_agent("Add File taxes.", desk_mod.load_desk(SEED), llm.make_model(), desk_mod.approve_no,
                                log_fn=lines.append)
        text = "\n".join(lines)
        self.assertIn("[planner] sees:", text)
        self.assertIn("[executor] sees:", text)

    def test_graph_invoke_passes_a_small_recursion_limit(self):
        """AM-1: compiled.invoke(...) gets config={"recursion_limit": N} with a small N (LangGraph's default is 10007)."""
        with record_graph_configs() as configs:
            two_agent.run_two_agent("Add File taxes.", desk_mod.load_desk(SEED), llm.make_model(), desk_mod.approve_no)
        self.assertTrue(configs, "run_two_agent must run a LangGraph graph")
        for config in configs:
            limit = (config or {}).get("recursion_limit")
            self.assertIsInstance(limit, int, "pass config={'recursion_limit': ...} to invoke()")
            self.assertLessEqual(limit, 50)

    def test_malformed_plan_runs_nothing_and_does_not_crash(self):
        """AM-1: a live-style malformed plan (steps not a list, or steps without a tool name) runs nothing, no crash."""
        for bad in ({"steps": "delete everything"}, {"steps": ["x", {"tool": 5}, {"args": {}}]}):
            d = desk_mod.load_desk(SEED)
            before = desk_mod.desk_to_dict(d)
            res = two_agent.run_two_agent("Tidy up my tasks.", d, ScriptedModel({"planner": bad}), desk_mod.approve_yes)
            self.assertIn(res["status"], ("done", "plan-rejected"))
            self.assertEqual(desk_mod.desk_to_dict(d), before)
