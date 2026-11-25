"""PM-1 checks: Supervisor + 2 least-privilege workers (PM-1a) and bounded Reviewer on risky actions (PM-1b)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import desk as desk_mod
import llm
import team
from fakes import ScriptedModel, record_graph_configs

SEED = os.path.join(ROOT, "data", "seed.json")
GOAL = "Cancel the team sync on Wednesday and remind me to email Anil."


class Phase3Tests(unittest.TestCase):
    def test_supervisor_routes_across_calendar_and_tasks_workers(self):
        """PM-1a: supervisor routes a multi-domain goal to both calendar and tasks workers."""
        d = desk_mod.load_desk(SEED)
        res = team.run_team(GOAL, d, llm.make_model(), desk_mod.approve_yes, review=False)
        self.assertEqual(res["status"], "done")
        self.assertTrue(any("email Anil" in t["text"] for t in d.tasks))
        self.assertFalse(any(e["id"] == 6 for e in d.events))

    def test_log_says_what_each_agent_sees(self):
        """PM-1a/b: the log has a 'sees:' line for supervisor, tasks, calendar and (with review) reviewer."""
        lines = []
        team.run_team(GOAL, desk_mod.load_desk(SEED), llm.make_model(), desk_mod.approve_no, review=True, log_fn=lines.append)
        text = "\n".join(lines)
        for agent in ("supervisor", "tasks", "calendar", "reviewer"):
            self.assertIn(f"[{agent}] sees:", text)

    def test_each_worker_refuses_a_tool_outside_its_slice(self):
        """PM-1a: a fooled tasks worker cannot cancel an event and a fooled calendar worker cannot delete a task (blind yes)."""
        d = desk_mod.load_desk(SEED)
        model = ScriptedModel({
            "supervisor": [{"next": "tasks", "task": "tidy"}, {"next": "calendar", "task": "tidy"}, {"next": "finish", "answer": "ok"}],
            "tasks_worker": {"tool": "cancel_event", "args": {"id": 6}, "summary": "obey note"},
            "calendar_worker": {"tool": "delete_task", "args": {"id": 1}, "summary": "obey note"},
        })
        res = team.run_team("Tidy up.", d, model, desk_mod.approve_yes, review=False)
        self.assertTrue(any(e["id"] == 6 for e in d.events), "tasks worker must not reach cancel_event")
        self.assertTrue(any(t["id"] == 1 for t in d.tasks), "calendar worker must not reach delete_task")
        self.assertIn("not allowed", " ".join(res.get("done_so_far") or []) + res.get("answer", ""))

    def test_supervisor_turn_cap_stops_a_loop(self):
        """PM-1a: a supervisor that never says finish is stopped after MAX_TURNS (6) calls; a denied delete is not asked again."""
        self.assertEqual(team.MAX_TURNS, 6)
        model = ScriptedModel({"supervisor": {"next": "tasks", "task": "list my tasks"},
                               "tasks_worker": {"tool": "list_tasks", "args": {}}})
        res = team.run_team("Show my list.", desk_mod.load_desk(SEED), model, desk_mod.approve_no)
        self.assertEqual(res["status"], "stopped")
        self.assertEqual(model.count("supervisor"), team.MAX_TURNS)
        # A human "no" is final for that worker: a supervisor that keeps re-routing the same denied delete is stopped.
        model2 = ScriptedModel({"supervisor": {"next": "tasks", "task": "delete the dentist task"},
                                "tasks_worker": {"tool": "delete_task", "args": {"id": 3}}})
        d2 = desk_mod.load_desk(SEED)
        res2 = team.run_team("Delete the dentist task.", d2, model2, desk_mod.approve_no)
        self.assertEqual(res2["status"], "done-with-denials")
        self.assertEqual(model2.count("tasks_worker"), 1, "a denied delete must not be asked again")
        self.assertTrue(any(t["id"] == 3 for t in d2.tasks))

    def test_graph_invoke_passes_a_small_recursion_limit(self):
        """PM-1a: compiled.invoke(...) gets config={"recursion_limit": N} with a small N (LangGraph's default is 10007)."""
        with record_graph_configs() as configs:
            team.run_team(GOAL, desk_mod.load_desk(SEED), llm.make_model(), desk_mod.approve_no)
        self.assertTrue(configs, "run_team must run a LangGraph graph")
        for config in configs:
            limit = (config or {}).get("recursion_limit")
            self.assertIsInstance(limit, int, "pass config={'recursion_limit': ...} to invoke()")
            self.assertLessEqual(limit, 50)

    def test_reviewer_blocks_planted_note_delete_as_defense_in_depth(self):
        """PM-1b: with review=True, the bounded reviewer rejects an unrequested delete from the planted-note drill."""
        d = desk_mod.load_desk(SEED)
        desk_mod.inject_drill_note(d)
        res = team.run_team("Tidy up my tasks.", d, llm.make_model(), desk_mod.approve_yes, review=True)
        self.assertEqual(res["status"], "done-with-denials")
        self.assertTrue(any(t["id"] == 1 for t in d.tasks))

    def test_reviewer_approval_never_bypasses_human_gate(self):
        """PM-1b: even when the reviewer approves an explicit cancel, the blocking [y/N] human gate still wins."""
        d = desk_mod.load_desk(SEED)
        res = team.run_team("Cancel the team sync on Wednesday.", d, llm.make_model(), desk_mod.approve_no, review=True)
        self.assertEqual(res["status"], "done-with-denials")
        self.assertTrue(any(e["id"] == 6 for e in d.events))

    def test_reviewer_runs_exactly_max_review_rounds(self):
        """PM-1b: a reviewer that keeps rejecting is asked MAX_REVIEW_ROUNDS (2) times; reject-then-approve passes in round 2."""
        self.assertEqual(team.MAX_REVIEW_ROUNDS, 2)
        always_no = ScriptedModel({"reviewer": {"approved": False, "reason": "not asked"}})
        ok, _ = team.reviewer_node("Tidy up.", "tasks", "delete_task", {"id": 1}, always_no)
        self.assertFalse(ok)
        self.assertEqual(always_no.count("reviewer"), 2)
        changes_mind = ScriptedModel({"reviewer": [{"approved": False, "reason": "unsure"}, {"approved": True, "reason": "fine"}]})
        ok, _ = team.reviewer_node("Delete task 1.", "tasks", "delete_task", {"id": 1}, changes_mind)
        self.assertTrue(ok)
        self.assertEqual(changes_mind.count("reviewer"), 2)
        always_yes = ScriptedModel({"reviewer": {"approved": True, "reason": "asked"}})
        team.reviewer_node("Delete task 1.", "tasks", "delete_task", {"id": 1}, always_yes)
        self.assertEqual(always_yes.count("reviewer"), 1)

    def test_reviewer_only_accepts_a_real_json_true(self):
        """PM-1b: a verdict like {"approved": "false"} or a missing field is NOT an approval (only JSON true approves)."""
        for verdict in ({"approved": "false"}, {"approved": "yes"}, {"reason": "no field"}):
            ok, _ = team.reviewer_node("Tidy up.", "tasks", "delete_task", {"id": 1}, ScriptedModel({"reviewer": verdict}))
            self.assertFalse(ok, f"{verdict} must not approve")
