"""Phase W7-2 acceptance tests: the structured handoff, the planner, the executor, and the two-agent graph."""
import unittest

from fakes import call, kinds, saw, team_with

import graph
from handoff import Handoff, HandoffError, PlanStep, make_handoff, parse_plan

PLAN = {"steps": [{"task": "Add File taxes", "tool": "add_task", "why": "asked"},
                  {"task": "Show the list", "tool": "list_tasks", "why": "asked"}]}


def two_agent(script, goal="Add File taxes, then show me my list.", **kwargs):
    """Run the two-agent graph on a script and return (final state, team, model)."""
    team, model = team_with(script, **kwargs)
    final = graph.run_graph(graph.build_two_agent(team), goal, team)
    return final, team, model


class PhaseW7_2(unittest.TestCase):
    def test_a_handoff_has_four_parts_and_shows_exactly_them(self):
        """A Handoff carries task, context, constraints and a return address; to_text() shows them in that order."""
        handoff = make_handoff("planner", "executor", "Add File taxes", context="tasks:\n1: Pay rent",
                               constraints=["use only the tool: add_task"], return_to="finish")
        text = handoff.to_text()
        positions = [text.index(label) for label in ("task: ", "context:", "constraints:", "return to: ")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("- use only the tool: add_task", text)
        self.assertEqual((handoff.from_agent, handoff.to_agent, handoff.return_to), ("planner", "executor", "finish"))
        self.assertEqual(Handoff(**handoff.to_dict()), handoff)

    def test_a_broken_handoff_is_refused(self):
        """make_handoff refuses an empty task or a missing receiver (HandoffError); the return address defaults to the sender."""
        with self.assertRaises(HandoffError):
            make_handoff("planner", "executor", "   ")
        with self.assertRaises(HandoffError):
            make_handoff("planner", "", "do it")
        self.assertEqual(make_handoff("supervisor", "tasks", "do it").return_to, "supervisor")

    def test_the_plan_is_parsed_into_checked_steps(self):
        """parse_plan turns {'steps': [...]} into PlanStep records and raises HandoffError on a wrong shape."""
        self.assertEqual(parse_plan(PLAN)[0], PlanStep("Add File taxes", "add_task", "asked"))
        for bad in ({}, {"steps": "add"}, {"steps": [{"task": "x"}]}):
            with self.assertRaises(HandoffError):
                parse_plan(bad)

    def test_planner_then_executor_does_each_step_once(self):
        """Two plan steps: the executor is asked exactly twice, the task is added, status done, two results, two handoffs."""
        final, team, model = two_agent({"planner": [PLAN], "executor": [call("add_task", text="File taxes"), call("list_tasks")]})
        self.assertEqual(final["status"], "done")
        self.assertEqual(model.roles(), ["planner", "executor", "executor"])
        self.assertEqual((len(final["results"]), len(final["handoffs"])), (2, 2))
        self.assertTrue(any(t["text"] == "File taxes" for t in team.desk.tasks))
        self.assertTrue(kinds(team.run, "plan") and kinds(team.run, "handoff"))

    def test_each_agent_sees_only_what_it_needs(self):
        """The planner sees the goal and the desk; the executor sees only its handoff (task, context...), never the goal line."""
        _final, _team, model = two_agent({"planner": [PLAN], "executor": [call("add_task", text="File taxes"), call("list_tasks")]})
        self.assertTrue(saw(model, "planner")[0].startswith("goal: "))
        for message in saw(model, "executor"):
            self.assertTrue(message.startswith("task: "))
            self.assertNotIn("goal:", message)

    def test_the_executor_may_use_only_the_planned_tool(self):
        """If the executor reaches for a different tool than the plan named, the gate refuses it and nothing changes."""
        final, team, _ = two_agent({"planner": [{"steps": [{"task": "Show the list", "tool": "list_tasks"}]}],
                                    "executor": [call("delete_task", id=4)]}, approve=lambda *a: True)
        self.assertEqual(final["results"][0]["kind"], "error")
        self.assertIn("not allowed", final["results"][0]["text"])
        self.assertEqual(len(team.desk.tasks), 6)

    def test_an_irreversible_step_still_asks_the_human(self):
        """A planned delete goes through the gate: the human says no, the task stays, status 'done-with-denials'."""
        final, team, _ = two_agent({"planner": [{"steps": [{"task": "Delete the dentist task", "tool": "delete_task"}]}],
                                    "executor": [call("delete_task", id=4)]}, goal="Delete the dentist task.")
        self.assertEqual(final["status"], "done-with-denials")
        self.assertTrue(any("dentist" in t["text"] for t in team.desk.tasks))

    def test_a_malformed_plan_stops_before_any_step(self):
        """A plan with the wrong shape ends the run 'plan-rejected' and the executor is never asked."""
        final, _team, model = two_agent({"planner": [{"plan": "just do it"}]})
        self.assertEqual(final["status"], "plan-rejected")
        self.assertEqual(model.roles(), ["planner"])
