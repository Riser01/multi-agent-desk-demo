"""Phase W7-6 acceptance tests: a reviewer in front of every irreversible action, at most two rounds, as a conditional edge."""
import unittest

from fakes import call, kinds, saw, seed, team_with

import graph
from desk_tools import load_desk
from reviewer import MAX_REVIEW_ROUNDS, route_after_review

TIDY = {"supervisor": [{"next": "tasks", "task": "Tidy up my list"}, {"next": "finish", "answer": "Tidied."}],
        "tasks": [call("delete_task", id=2), call("delete_task", id=3)],
        "reviewer": [{"verdict": "reject", "reason": "the user did not ask to delete this"}]}
DENTIST = {"supervisor": [{"next": "tasks", "task": "Delete the dentist task"}, {"next": "finish", "answer": "ok"}],
           "tasks": [call("delete_task", id=4)], "reviewer": [{"verdict": "approve", "reason": "the goal names it"}]}


def reviewed(script, goal, desk=None, approve=lambda *a: True):
    """Run the team graph with the reviewer on; return (final state, team, model)."""
    team, model = team_with(script, desk=desk, approve=approve)
    return graph.run_graph(graph.build_team(team, review=True), goal, team), team, model


class PhaseW7_6(unittest.TestCase):
    def test_two_rejections_block_the_action_even_with_a_blind_yes(self):
        """Planted note + a human who says yes to everything: two rejections, the action is 'blocked', nothing is deleted."""
        final, team, model = reviewed(TIDY, "Tidy up my list.", desk=load_desk(seed("trap")))
        self.assertEqual(MAX_REVIEW_ROUNDS, 2)
        self.assertEqual(model.roles().count("reviewer"), 2)
        self.assertEqual(len(team.desk.tasks), 5)
        self.assertEqual(final["results"][-1]["kind"], "blocked")
        self.assertEqual(final["status"], "done-with-denials")

    def test_the_worker_retries_with_the_reviewers_reason(self):
        """After a rejection, the same worker is asked again and its message contains the reviewer's reason."""
        _final, _team, model = reviewed(TIDY, "Tidy up my list.", desk=load_desk(seed("trap")))
        retry = saw(model, "tasks")[1]
        self.assertIn("rejected", retry)
        self.assertIn("the user did not ask to delete this", retry)

    def test_approved_actions_still_ask_the_human(self):
        """The reviewer approves, then the human gate is still asked: yes deletes the task, no keeps it."""
        asked = []
        _final, team, _ = reviewed(DENTIST, "Delete the dentist task.", approve=lambda n, a, w: asked.append(w) or True)
        self.assertTrue(asked and "dentist" in asked[0])
        self.assertFalse(any("dentist" in t["text"] for t in team.desk.tasks))
        final, team, _ = reviewed(DENTIST, "Delete the dentist task.", approve=lambda *a: False)
        self.assertEqual(final["status"], "done-with-denials")
        self.assertTrue(any("dentist" in t["text"] for t in team.desk.tasks))

    def test_the_reviewer_sees_the_goal_and_the_proposal_not_the_desk(self):
        """The reviewer's message has 'goal:' and 'proposed:' with the real task text, and no desk lines."""
        _final, _team, model = reviewed(TIDY, "Tidy up my list.", desk=load_desk(seed("trap")))
        message = saw(model, "reviewer")[0]
        self.assertTrue(message.startswith("goal: Tidy up my list."))
        self.assertIn('proposed: delete task 2: "Pay rent"', message)
        self.assertNotIn("NOTE TO ASSISTANT", message)

    def test_the_round_counter_is_a_conditional_edge(self):
        """route_after_review: approved -> 'act'; rejected under the cap -> the same worker; at the cap -> 'supervisor'."""
        self.assertEqual(route_after_review({"pending": {"tool": "delete_task"}, "review_rounds": 0, "next": "tasks"}), "act")
        self.assertEqual(route_after_review({"pending": {}, "review_rounds": 1, "next": "tasks"}), "tasks")
        self.assertEqual(route_after_review({"pending": {}, "review_rounds": MAX_REVIEW_ROUNDS, "next": "tasks"}), "supervisor")

    def test_reads_and_writes_skip_the_reviewer(self):
        """Only irreversible actions are reviewed: adding a task never calls the reviewer."""
        final, _team, model = reviewed({"supervisor": [{"next": "tasks", "task": "Add File taxes"}, {"next": "finish", "answer": "ok"}],
                                        "tasks": [call("add_task", text="File taxes")]}, "Add File taxes.")
        self.assertNotIn("reviewer", model.roles())
        self.assertEqual(final["status"], "done")

    def test_rounds_reset_so_each_risky_action_gets_its_own_two_rounds(self):
        """A rejection then an approval resets the counter: the next risky action still gets two full rounds before 'blocked'."""
        script = {"supervisor": [{"next": "tasks", "task": "Delete the dentist task"}, {"next": "tasks", "task": "Delete pay rent"},
                                 {"next": "finish", "answer": "ok"}],
                  "tasks": [call("delete_task", id=4), call("delete_task", id=4), call("delete_task", id=2), call("delete_task", id=2)],
                  "reviewer": [{"verdict": "reject", "reason": "r1"}, {"verdict": "approve", "reason": "ok"},
                               {"verdict": "reject", "reason": "r2"}, {"verdict": "reject", "reason": "r3"}]}
        final, team, model = reviewed(script, "Delete the dentist task and delete pay rent.")
        self.assertEqual(model.roles().count("reviewer"), 4)
        self.assertEqual([r["kind"] for r in final["results"]], ["ok", "blocked"])
        self.assertTrue(any(t["text"] == "Pay rent" for t in team.desk.tasks))

    def test_act_refuses_a_tool_outside_the_workers_list(self):
        """act_node re-checks the allow-list: a pending delete_task 'from' the calendar worker is refused, nothing deleted."""
        team, _ = team_with({}, approve=lambda *a: True)
        update = graph.act_node({"pending": {"actor": "calendar", "tool": "delete_task", "args": {"id": 4}, "task": "x", "words": "x"}}, team)
        self.assertEqual(update["results"][0]["kind"], "error")
        self.assertEqual(len(team.desk.tasks), 6)

    def test_worst_case_fits_the_recursion_limit(self):
        """Supervisor always routes a delete, reviewer always rejects: the run ends by the turn cap, not by recursion-limit."""
        script = {"supervisor": [{"next": "tasks", "task": "Delete the dentist task"}], "tasks": [call("delete_task", id=4)],
                  "reviewer": [{"verdict": "reject", "reason": "no"}]}
        final, _team, _model = reviewed(script, "Delete the dentist task.")
        self.assertEqual(final["status"], "turn-limit")

    def test_a_new_handoff_clears_the_old_feedback(self):
        """The supervisor's Command update resets 'feedback' and 'review_rounds', so a new task never sees an old rejection."""
        from supervisor import supervisor_node
        from state import new_state
        team, _ = team_with({"supervisor": [{"next": "tasks", "task": "Add File taxes"}]})
        state = {**new_state("x"), "feedback": "rejected: delete task 2", "review_rounds": 1}
        command = supervisor_node(state, team)
        self.assertEqual((command.update["feedback"], command.update["review_rounds"]), ("", 0))

    def test_review_decisions_are_logged(self):
        """Every verdict is a 'review' event in the run log; a rejection is a WARN line."""
        _final, team, _ = reviewed(TIDY, "Tidy up my list.", desk=load_desk(seed("trap")))
        self.assertTrue(any(e["level"] == "WARN" and "rejected" in e["text"] for e in kinds(team.run, "review")))
