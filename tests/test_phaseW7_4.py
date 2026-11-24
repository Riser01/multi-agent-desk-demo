"""Phase W7-4 acceptance tests: a hand-written supervisor, two specialist workers, shared state, and who sees what."""
import unittest

from fakes import call, kinds, saw, team_with

import graph
from stand_in import StandIn
from supervisor import MAX_TURNS, WORKERS

ROUTE_BOTH = [{"next": "calendar", "task": "Add a dentist appointment on Fri 27 Nov 10:00"},
              {"next": "tasks", "task": "Add a task to buy a gift"},
              {"next": "finish", "answer": "Both done."}]


def team_run(script, goal="Add a dentist appointment on Fri 27 Nov 10:00 and add a task to buy a gift.", **kwargs):
    """Run the team graph (no reviewer) and return (final state, team, model)."""
    team, model = team_with(script, **kwargs)
    return graph.run_graph(graph.build_team(team), goal, team), team, model


class PhaseW7_4(unittest.TestCase):
    def test_two_workers_with_short_allow_lists(self):
        """WORKERS has exactly 'tasks' and 'calendar'; the calendar worker cannot delete tasks."""
        self.assertEqual(sorted(WORKERS), ["calendar", "tasks"])
        self.assertNotIn("delete_task", WORKERS["calendar"])
        self.assertLessEqual(len(WORKERS["tasks"]), 6)

    def test_the_supervisor_routes_each_part_to_the_right_worker(self):
        """Supervisor -> calendar -> supervisor -> tasks -> supervisor -> finish; both changes land; status done."""
        final, team, model = team_run({"supervisor": ROUTE_BOTH, "calendar": [call("add_event", when="Fri 27 Nov 10:00", title="Dentist")],
                                       "tasks": [call("add_task", text="Buy a gift")]})
        self.assertEqual(model.roles(), ["supervisor", "calendar", "supervisor", "tasks", "supervisor"])
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["answer"], "Both done.")
        self.assertTrue(any(e["title"] == "Dentist" for e in team.desk.events))
        self.assertEqual(len(final["results"]), 2)
        self.assertEqual([h["to_agent"] for h in final["handoffs"]], ["calendar", "tasks"])
        self.assertTrue(all(h["return_to"] == "supervisor" for h in final["handoffs"]))

    def test_what_each_agent_saw(self):
        """The supervisor sees the goal and results but no desk; each worker sees its handoff and only its half of the desk."""
        _final, _team, model = team_run({"supervisor": ROUTE_BOTH, "calendar": [call("list_events")], "tasks": [call("list_tasks")]})
        first_supervisor = saw(model, "supervisor")[0]
        self.assertTrue(first_supervisor.startswith("goal: "))
        self.assertNotIn("Book dentist appointment", first_supervisor)
        calendar, tasks = saw(model, "calendar")[0], saw(model, "tasks")[0]
        self.assertIn("Team sync", calendar)
        self.assertNotIn("Pay rent", calendar)
        self.assertIn("Pay rent", tasks)
        self.assertNotIn("Team sync", tasks)
        self.assertIn("calendar", saw(model, "supervisor")[1].split("done so far:")[1])
        self.assertTrue(kinds(_team.run, "route"))

    def test_least_privilege_holds_whatever_the_worker_asks(self):
        """A calendar worker that asks for delete_task is refused by the gate, even with a human who says yes."""
        final, team, _ = team_run({"supervisor": [{"next": "calendar", "task": "Cancel the sync"}, {"next": "finish", "answer": "x"}],
                                   "calendar": [call("delete_task", id=4)]}, approve=lambda *a: True)
        self.assertIn("not allowed", final["results"][0]["text"])
        self.assertEqual(len(team.desk.tasks), 6)

    def test_the_turn_cap_ends_a_supervisor_that_never_finishes(self):
        """A supervisor that keeps routing stops with status 'turn-limit' after MAX_TURNS routing turns."""
        final, _team, model = team_run({"supervisor": [{"next": "tasks", "task": "List my tasks"}], "tasks": [call("list_tasks")]})
        self.assertEqual(final["status"], "turn-limit")
        self.assertEqual(model.roles().count("supervisor"), MAX_TURNS)

    def test_an_invented_worker_is_refused_by_code(self):
        """If the supervisor names a worker that does not exist, the run stops 'model-error' and no worker runs."""
        final, _team, model = team_run({"supervisor": [{"next": "email", "task": "Send it"}]})
        self.assertEqual(final["status"], "model-error")
        self.assertEqual(model.roles(), ["supervisor"])

    def test_the_offline_stand_in_runs_the_whole_team(self):
        """With the offline stand-in, the two-domain request adds both the event and the task."""
        team, _ = team_with({})
        team.model = StandIn()
        final = graph.run_graph(graph.build_team(team), "Add a dentist appointment on Fri 27 Nov 10:00 and add a task to buy a gift for Anil.", team)
        self.assertEqual(final["status"], "done")
        self.assertTrue(any("Dentist" in e["title"] for e in team.desk.events))
        self.assertTrue(any("gift for Anil" in t["text"] for t in team.desk.tasks))
