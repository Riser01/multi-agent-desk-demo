"""Phase W7-1 acceptance tests: typed state with reducers, one agent as a graph node, and a run that always ends."""
import operator
import os
import tempfile
import typing
import unittest

from fakes import call, desk_with, kinds, saw, seed, team_with

import graph
import llm
from state import Team, TeamState, new_state


class PhaseW7_1(unittest.TestCase):
    def test_state_has_reducers_on_the_append_only_logs(self):
        """TeamState merges 'results' and 'handoffs' with operator.add (append), and overwrites plain keys such as 'status'."""
        hints = typing.get_type_hints(TeamState, include_extras=True)
        for key in ("results", "handoffs"):
            self.assertIs(typing.get_args(hints[key])[1], operator.add, key)
        self.assertNotIn("__metadata__", dir(hints["status"]))

    def test_new_state_starts_every_counter_at_zero(self):
        """new_state(goal) holds the goal, empty results and handoffs, and turns, step and review_rounds at 0."""
        state = new_state("Add File taxes")
        self.assertEqual(state["goal"], "Add File taxes")
        self.assertEqual((state["results"], state["handoffs"]), ([], []))
        self.assertEqual((state["turns"], state["step"], state["review_rounds"]), (0, 0, 0))

    def test_team_ask_uses_the_routed_model_and_act_goes_through_the_gate(self):
        """Team.ask passes the role's routed model name and returns the JSON; Team.act runs tools only through the gate."""
        team, model = team_with({"agent": [{"ok": 1}]}, desk=desk_with("Pay rent"), routing={"agent": "cheap-model"})
        self.assertEqual(team.ask("agent", "sys", "hi"), {"ok": 1})
        self.assertEqual(model.calls[0]["model"], "cheap-model")
        self.assertEqual(team.act("agent", "delete_task", {"id": 1}, allowed=["delete_task"]).kind, "denied")
        self.assertEqual(len(team.desk.tasks), 1)

    def test_one_agent_node_adds_a_task_and_finishes(self):
        """The single agent graph: add_task, then final -> status done, the task exists, one result in the state."""
        team, model = team_with({"agent": [call("add_task", text="File taxes"), {"final": "Added."}]})
        final = graph.run_graph(graph.build_single(team), "Add File taxes", team)
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["answer"], "Added.")
        self.assertEqual(len(final["results"]), 1)
        self.assertTrue(any(t["text"] == "File taxes" for t in team.desk.tasks))

    def test_the_agent_sees_the_goal_the_desk_and_its_own_results(self):
        """The agent's message starts 'goal: ', shows the desk, and from turn 2 lists 'done so far' results."""
        team, model = team_with({"agent": [call("list_tasks"), {"final": "ok"}]})
        graph.run_graph(graph.build_single(team), "Show me my list.", team)
        first, second = saw(model, "agent")
        self.assertTrue(first.startswith("goal: Show me my list."))
        self.assertIn("4: Book dentist appointment", first)
        self.assertIn("list_tasks", second.split("done so far:")[1])

    def test_final_wins_over_a_tool_in_the_same_reply(self):
        """A reply with both 'final' and 'tool' ends the run; the tool does not run."""
        team, _ = team_with({"agent": [{"final": "done", "tool": "delete_task", "args": {"id": 1}}]}, approve=lambda *a: True)
        final = graph.run_graph(graph.build_single(team), "x", team)
        self.assertEqual(final["status"], "done")
        self.assertEqual(len(team.desk.tasks), 6)

    def test_a_refused_delete_keeps_the_task_and_says_so(self):
        """A delete the human refuses keeps the task; the run ends 'done-with-denials', decided by code."""
        team, _ = team_with({"agent": [call("delete_task", id=4), {"final": "Deleted it!"}]})
        final = graph.run_graph(graph.build_single(team), "Delete the dentist task.", team)
        self.assertEqual(final["status"], "done-with-denials")
        self.assertTrue(any("dentist" in t["text"] for t in team.desk.tasks))

    def test_the_turn_cap_ends_a_run_that_never_finishes(self):
        """An agent that never says final stops with status 'turn-limit' after exactly MAX_TURNS model calls."""
        team, model = team_with({"agent": [call("list_tasks")]})
        final = graph.run_graph(graph.build_single(team), "x", team, recursion_limit=100)
        self.assertEqual(final["status"], "turn-limit")
        self.assertEqual(len(model.calls), graph.MAX_TURNS)

    def test_run_graph_sets_an_explicit_recursion_limit(self):
        """run_graph passes its own recursion_limit; hitting it is status 'recursion-limit', not a crash."""
        self.assertLessEqual(graph.RECURSION_LIMIT, 50)
        team, _ = team_with({"agent": [call("list_tasks")]})
        final = graph.run_graph(graph.build_single(team), "x", team, recursion_limit=3)
        self.assertEqual(final["status"], "recursion-limit")
        self.assertTrue(kinds(team.run, "cap"))

    def test_call_cap_and_bad_json_become_statuses(self):
        """The per-run call cap ends a run as 'call-cap'; a model that never sends JSON ends it as 'model-error'."""
        team, _ = team_with({"agent": [call("list_tasks")]})
        team.model = llm.Capped(team.model, max_calls=2)
        self.assertEqual(graph.run_graph(graph.build_single(team), "x", team)["status"], "call-cap")
        team, _ = team_with({"agent": ["I think I will list the tasks"]})
        self.assertEqual(graph.run_graph(graph.build_single(team), "x", team)["status"], "model-error")

    def test_agent_cli_runs_offline_and_writes_the_files(self):
        """agent.py --setup single runs with the offline stand-in, prints 'status:', writes logs/latest.log and out/latest.html."""
        import agent
        printed = []
        with tempfile.TemporaryDirectory() as folder:
            code = agent.main(['Add "File taxes", then show me my list.', "--setup", "single", "--approve", "no",
                               "--seed", seed("desk_week"), "--quiet"], out=printed.append, root=folder)
            self.assertTrue(os.path.isfile(os.path.join(folder, "logs", "latest.log")))
            self.assertTrue(os.path.isfile(os.path.join(folder, "out", "latest.html")))
        self.assertEqual(code, 0)
        self.assertIn("status: done", printed)

    def test_agent_cli_setup_problems_exit_2_in_plain_words(self):
        """A missing seed file prints 'configuration error: ...' and returns 2, no traceback."""
        import agent
        printed = []
        code = agent.main(["x", "--seed", "no/such/file.json"], out=printed.append)
        self.assertEqual(code, 2)
        self.assertTrue(printed[0].startswith("configuration error:"))
