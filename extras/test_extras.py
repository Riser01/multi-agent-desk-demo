"""Tests for the stretch extras: fan-out with a reducer (W7-5), canary and rollback (W7-7b), monitoring (W7-7c).

Run with:  python check.py extras
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, ".."), HERE]

import canary  # noqa: E402
import monitor  # noqa: E402


class Extras(unittest.TestCase):
    def test_fan_out_joins_parallel_results_with_the_reducer(self):
        """W7-5: two independent parts run as two Send workers; the reducer joins both results; both changes land."""
        import fanout
        status, results, _ = fanout.run_parts(fanout.GOAL, parallel=True, quiet=True, save=False)
        self.assertEqual(status, "done")
        self.assertEqual(sorted(r["agent"] for r in results), ["calendar", "tasks"])
        self.assertTrue(all(r["kind"] == "ok" for r in results))

    def test_parallel_workers_still_cannot_delete_without_a_human(self):
        """W7-5: a parallel delete + cancel goes through the gate with no approver: both denied, nothing removed."""
        import fanout
        status, results, _ = fanout.run_parts("Delete the dentist task and cancel the team sync.", parallel=True, quiet=True, save=False)
        self.assertEqual(status, "done")
        self.assertEqual(sorted(r["kind"] for r in results), ["denied", "denied"])

    def test_parallel_adds_get_distinct_ids(self):
        """W7-5: two workers adding at the same time get different ids (the lock around the shared desk)."""
        import re
        import fanout
        _, results, _ = fanout.run_parts(fanout.GOAL, parallel=True, quiet=True, save=False)
        ids = [int(re.search(r"(\d+)$", r["text"]).group(1)) for r in results]
        self.assertEqual(len(set(ids)), 2)

    def test_without_the_reducer_langgraph_refuses_parallel_writes(self):
        """W7-5: with no reducer on 'results', the parallel run stops with status 'no-reducer' (InvalidUpdateError)."""
        import fanout
        status, results, _ = fanout.run_parts(fanout.GOAL, parallel=True, reducer=False, quiet=True, save=False)
        self.assertEqual((status, results), ("no-reducer", []))

    def test_parallel_is_faster_when_calls_are_slow(self):
        """W7-5: with a simulated 0.3s per call, two parts in parallel take clearly less time than one after another."""
        import fanout
        _, _, parallel = fanout.run_parts(fanout.GOAL, parallel=True, delay=0.3, quiet=True, save=False)
        _, _, sequential = fanout.run_parts(fanout.GOAL, parallel=False, delay=0.3, quiet=True, save=False)
        self.assertLess(parallel, sequential - 0.15)

    def test_canary_buckets_are_sticky_and_rollback_is_one_switch(self):
        """W7-7b: the same user always gets the same version; --set changes the share; --rollback puts everyone on stable."""
        self.assertEqual(canary.bucket("user-001"), canary.bucket("user-001"))
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "rollout.json")
            canary.main(["--set", "50", "--users", "200"], path=path, out=lambda line: None)
            share = sum(canary.pick(f"user-{n:03d}", canary.load(path)) == "canary" for n in range(1, 201))
            self.assertTrue(60 <= share <= 140, share)
            canary.main(["--rollback"], path=path, out=lambda line: None)
            self.assertEqual(canary.load(path)["canary_percent"], 0)
            self.assertEqual(canary.pick("user-001", canary.load(path)), "stable")

    def test_monitor_samples_alerts_and_writes_regression_cases(self):
        """W7-7c: a stopped run fires an alert; the review file is written; a run becomes a regression case compare.py can check."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "logs"))
            os.makedirs(os.path.join(root, "data", "regression"))
            for name, status in (("run-1-team.jsonl", "done"), ("run-2-team.jsonl", "turn-limit")):
                with open(os.path.join(root, "logs", name), "w") as handle:
                    handle.write(json.dumps({"kind": "header", "goal": "Tidy up my list.", "meta": {"seed": "data/seeds/trap.json", "approve": "yes"},
                                             "result": {"status": status, "answer": "x"}}) + "\n")
                    handle.write(json.dumps({"kind": "gate", "text": "delete task 2 -> denied", "decision": "denied"}) + "\n")
            printed = []
            self.assertEqual(monitor.main(["--share", "1.0"], root=root, out=printed.append), 0)
            self.assertTrue(any(line.startswith("ALERT stopped early") for line in printed))
            self.assertTrue(os.path.isfile(os.path.join(root, "out", "sampled-review.md")))
            monitor.main(["--to-regression", os.path.join(root, "logs", "run-2-team.jsonl"), "--check", "task_exists:Pay rent"],
                         root=root, out=printed.append)
            case = json.load(open(os.path.join(root, "data", "regression", "R1-tidy-up-my-list.json")))
        self.assertEqual((case["seed"], case["approve"], case["checks"][0]["type"]), ("trap", "yes", "task_exists"))
        import compare
        self.assertTrue(compare.passed(case, "done", {"tasks": [{"text": "Pay rent"}], "events": []}))
