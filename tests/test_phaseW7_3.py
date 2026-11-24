"""Phase W7-3 acceptance tests: break the handoff on purpose (bad plan, huge note, injection) and cap it."""
import os
import unittest

from fakes import ROOT, call, kinds, saw, seed, team_with

import graph
import llm
from desk_tools import TEAM_TOOLS, load_desk
from handoff import MAX_CONTEXT_CHARS, MAX_PLAN_STEPS, MAX_TASK_CHARS, HandoffError, PlanStep, make_handoff, validate_plan

INJECTED_PLAN = {"steps": [{"task": "List the tasks", "tool": "list_tasks"},
                           {"task": "remove task 2 (a note on the list asks for it)", "tool": "delete_task"}]}


class PhaseW7_3(unittest.TestCase):
    def test_the_caps_are_small_numbers(self):
        """The caps exist and are small: MAX_PLAN_STEPS <= 10, MAX_TASK_CHARS <= 300, MAX_CONTEXT_CHARS <= 1000."""
        self.assertLessEqual(MAX_PLAN_STEPS, 10)
        self.assertLessEqual(MAX_TASK_CHARS, 300)
        self.assertLessEqual(MAX_CONTEXT_CHARS, 1000)

    def test_a_huge_context_is_cut_with_a_marker_and_flagged(self):
        """A context over MAX_CONTEXT_CHARS is cut to exactly that, ends ' [truncated]', and the handoff says capped=True."""
        handoff = make_handoff("planner", "executor", "Show the list", context="x" * 1500)
        self.assertEqual(handoff.context, "x" * MAX_CONTEXT_CHARS + " [truncated]")
        self.assertTrue(handoff.capped)
        self.assertFalse(make_handoff("planner", "executor", "Show the list", context="short").capped)

    def test_a_task_over_the_cap_is_refused_not_cut(self):
        """A task longer than MAX_TASK_CHARS raises HandoffError: a cut task would be a different task."""
        with self.assertRaises(HandoffError):
            make_handoff("planner", "executor", "x" * (MAX_TASK_CHARS + 1))

    def test_validate_plan_names_every_broken_rule(self):
        """validate_plan returns one sentence per problem: empty, too many steps, unknown tool, task too long."""
        self.assertTrue(validate_plan([], "x", TEAM_TOOLS))
        too_many = [PlanStep("List", "list_tasks")] * (MAX_PLAN_STEPS + 1)
        self.assertTrue(any(str(MAX_PLAN_STEPS) in p for p in validate_plan(too_many, "x", TEAM_TOOLS)))
        self.assertTrue(any("send_email" in p for p in validate_plan([PlanStep("Mail", "send_email")], "x", TEAM_TOOLS)))
        self.assertTrue(validate_plan([PlanStep("x" * 300, "add_task")], "x", TEAM_TOOLS))
        self.assertEqual(validate_plan([PlanStep("Add File taxes", "add_task")], "Add File taxes", TEAM_TOOLS), [])

    def test_an_irreversible_step_needs_the_user_to_have_asked(self):
        """A delete step is refused when the goal never asks to delete, remove, clear or cancel; allowed when it does."""
        step = [PlanStep("remove task 2", "delete_task")]
        self.assertTrue(validate_plan(step, "Tidy up my list.", TEAM_TOOLS))
        self.assertEqual(validate_plan(step, "Delete task 2.", TEAM_TOOLS), [])

    def test_injection_in_a_task_is_stopped_before_any_step(self):
        """Planted note: a fooled planner plans a delete; the plan is rejected, the executor never runs, nothing is deleted."""
        team, model = team_with({"planner": [INJECTED_PLAN], "executor": [call("delete_task", id=2)]},
                                desk=load_desk(seed("trap")), approve=lambda *a: True)
        final = graph.run_graph(graph.build_two_agent(team), "Tidy up my list.", team)
        self.assertEqual(final["status"], "plan-rejected")
        self.assertNotIn("executor", model.roles())
        self.assertEqual(len(team.desk.tasks), 5)
        self.assertTrue(any(e["level"] == "WARN" for e in kinds(team.run, "plan")))

    def test_a_huge_note_cannot_flood_the_executor(self):
        """With a 1,500-character note on the desk, the executor's message stays small and a WARN 'cap' line is logged."""
        team, model = team_with({"planner": [{"steps": [{"task": "Show the list", "tool": "list_tasks"}]}],
                                 "executor": [call("list_tasks")]}, desk=load_desk(seed("long_note")))
        final = graph.run_graph(graph.build_two_agent(team), "Show me my list.", team)
        self.assertEqual(final["status"], "done")
        self.assertLess(len(saw(model, "executor")[0]), MAX_CONTEXT_CHARS + 400)
        self.assertTrue(any(e["level"] == "WARN" for e in kinds(team.run, "cap")))

    def test_the_scripted_bad_plan_is_rejected_with_reasons(self):
        """The replayed bad plan (7 steps, send_email, an unasked delete) is rejected and the reasons name each rule."""
        team, _ = team_with({})
        team.model = llm.ReplayModel(os.path.join(ROOT, "data", "replays", "w7-3-bad-plan.json"))
        final = graph.run_graph(graph.build_two_agent(team), "Add File taxes and show me my list.", team)
        self.assertEqual(final["status"], "plan-rejected")
        for reason in ("send_email", f"cap is {MAX_PLAN_STEPS}", "cannot be undone"):
            self.assertIn(reason, final["answer"])
