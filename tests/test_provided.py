"""Tests for provided plumbing: Desk, gate, todo-list.md, sessions/, /drill, /monitor, honest labels, trace export, single."""
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app
import desk as desk_mod
import llm
from fakes import ScriptedModel

SEED = os.path.join(ROOT, "data", "seed.json")


class ProvidedTests(unittest.TestCase):
    def test_delete_gate_defaults_to_deny_and_enforces_allow_list(self):
        """Irreversible tools require explicit yes; blank/EOF defaults to deny; unknown/disallowed tools are refused."""
        d = desk_mod.load_desk(SEED)
        res_denied = desk_mod.run_tool("delete_task", {"id": 1}, d, allowed=desk_mod.TASK_TOOLS, approve=desk_mod.approve_no)
        self.assertEqual(res_denied.kind, "denied")
        self.assertTrue(any(t["id"] == 1 for t in d.tasks))
        res_refused = desk_mod.run_tool("cancel_event", {"id": 6}, d, allowed=desk_mod.TASK_TOOLS, approve=desk_mod.approve_yes)
        self.assertEqual(res_refused.kind, "refused")

    def test_session_sanitization_and_save_load_latest_copy(self):
        """Session names block traversal/reserved 'latest'; save_session writes latest.json as a real copy and todo-list.md."""
        for bad in ("", "../x", "a/b", "a\\b", "bad:id", "latest", "a" * 65):
            with self.assertRaises(ValueError):
                desk_mod.validate_session_id(bad)
        d = desk_mod.load_desk(SEED)
        with tempfile.TemporaryDirectory() as tmp:
            saved = desk_mod.save_session(tmp, {"id": "demo1", "setup": "single", "desk": d, "turns": 1})
            latest = os.path.join(tmp, "sessions", "latest.json")
            self.assertTrue(os.path.isfile(saved) and os.path.isfile(latest) and not os.path.islink(latest))
            loaded = desk_mod.load_session(tmp, "latest")
            self.assertEqual(loaded["id"], "demo1")
            md = desk_mod.write_todo_file(tmp, d, session_id="demo1", setup="single", turns=1,
                                          session_cost=0.0, cost_available=False, mode="fake")
            self.assertIn("- [ ] `#1` Pay rent", open(md, encoding="utf-8").read())

    def test_drill_is_idempotent_and_monitor_handles_empty_logs(self):
        """/drill attaches one note without duplicating; /monitor prints a friendly message when no logs exist."""
        d = desk_mod.load_desk(SEED)
        n1 = desk_mod.inject_drill_note(d)
        n2 = desk_mod.inject_drill_note(d)
        self.assertEqual(n1["id"], n2["id"])
        lines = []
        with tempfile.TemporaryDirectory() as tmp:
            app.run_monitor(desk_mod.Path(tmp), lines.append)
        self.assertIn("No runs logged yet", "\n".join(lines))

    def test_interactive_chat_works_out_of_box_with_builtin_single_and_autosaves(self):
        """python app.py works before AM-1 via built-in single, updates todo-list.md, and auto-saves on /quit."""
        cmds = iter(["Add Buy milk", "/desk", "/save test1", "/quit"])
        lines = []
        with tempfile.TemporaryDirectory() as tmp:
            code = app.main(["--seed", SEED, "--approve", "no", "--quiet"],
                            input_fn=lambda _: next(cmds), out=lines.append, root=tmp)
            self.assertEqual(code, 0)
            self.assertIn("Saved desk & chat", "\n".join(lines))
            self.assertIn("Buy milk", open(os.path.join(tmp, "todo-list.md"), encoding="utf-8").read())
            loaded = desk_mod.load_session(tmp, "test1")
            self.assertEqual(loaded["turns"], 1)


class ProvidedSafetyAndLabelTests(unittest.TestCase):
    def test_terminal_gate_blank_or_eof_means_no(self):
        """The [y/N] gate approves only on y/yes; blank, other text and EOF (closed input) all mean NO."""
        def ask_with(answer):
            def fake_input(_prompt):
                if answer is EOFError:
                    raise EOFError
                return answer
            return desk_mod.make_ask(fake_input, lambda _: None)("delete_task", {"id": 1}, "delete task #1")
        for no in ("", "   ", "n", "no", "maybe", EOFError):
            self.assertFalse(ask_with(no), f"answer {no!r} must deny")
        for yes in ("y", "Y", "yes", " YES "):
            self.assertTrue(ask_with(yes), f"answer {yes!r} must approve")

    def test_windows_reserved_session_names_rejected(self):
        """Session names Windows cannot save (con, nul, prn, aux, com1-9, lpt1-9) are rejected on every OS."""
        for bad in ("con", "CON", "nul", "prn", "aux", "com1", "COM9", "lpt1", "Lpt9"):
            with self.assertRaises(ValueError):
                desk_mod.validate_session_id(bad)
        for ok in ("console", "com10", "nully", "demo-1"):
            self.assertEqual(desk_mod.validate_session_id(ok), ok)

    def test_corrupt_session_files_are_reported_not_crashed(self):
        """Damaged sessions (turns null, events not a list, bad history or seed) raise a clear ValueError; --resume exits 2."""
        good = desk_mod.desk_to_dict(desk_mod.load_desk(SEED))
        damaged = {
            "turns_null": {"id": "turns_null", "desk": good, "turns": None},
            "events_int": {"id": "events_int", "desk": {**good, "events": 5}},
            "history_int": {"id": "history_int", "desk": good, "history": 3},
            "seed_bad": {"id": "seed_bad", "desk": good, "seed": "/etc/passwd"},
            "seed_type": {"id": "seed_type", "desk": good, "seed": 42},
        }
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "sessions"))
            for name, data in damaged.items():
                with open(os.path.join(tmp, "sessions", f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(data, fh)
                with self.assertRaises(ValueError, msg=name):
                    desk_mod.load_session(tmp, name)
            lines = []
            code = app.main(["--resume", "turns_null", "--quiet"], input_fn=lambda _: "/quit", out=lines.append, root=tmp)
            self.assertEqual(code, 2)
            self.assertIn("configuration error", "\n".join(lines))
        for kind in ("tasks", "events", "notes"):
            with self.assertRaises(ValueError, msg=kind):
                desk_mod.desk_from_dict({**good, kind: 5})

    def test_offline_outputs_say_stand_in_not_a_real_model(self):
        """logs/latest.log, runs.jsonl and out/latest.html say 'offline stand-in (not a real model)'; no Gemini model name."""
        with tempfile.TemporaryDirectory() as tmp:
            code = app.main(["Add Buy milk", "--seed", SEED, "--approve", "no", "--quiet"],
                            input_fn=lambda _: "", out=lambda _: None, root=tmp)
            self.assertEqual(code, 0)
            log = open(os.path.join(tmp, "logs", "latest.log"), encoding="utf-8").read()
            row = json.loads(open(os.path.join(tmp, "logs", "runs.jsonl"), encoding="utf-8").read().splitlines()[-1])
            page = open(os.path.join(tmp, "out", "latest.html"), encoding="utf-8").read()
            for text in (log, row["mode"], page):
                self.assertIn("offline stand-in (not a real model)", text)
            self.assertIn("model=stand-in", log)
            self.assertNotIn("model=gemini", log)

    def test_monitor_shows_na_when_cost_was_not_metered(self):
        """/monitor prints cost n/a (not $0.000000) for runs logged before prod.py existed, and skips broken lines."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "logs"))
            with open(os.path.join(tmp, "logs", "runs.jsonl"), "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"setup": "single", "status": "done", "cost_usd": None}) + "\n{broken\n")
            lines = []
            app.run_monitor(desk_mod.Path(tmp), lines.append)
        text = "\n".join(lines)
        self.assertIn("n/a", text)
        self.assertNotIn("$0.000000", text)


class _RecorderObservation:
    def __init__(self, log, name, as_type):
        self.log, self.name, self.as_type = log, name, as_type

    def update(self, **kwargs):
        self.log.append(("update", self.name, self.as_type, kwargs))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecorderClient:
    """Stands in for langfuse.get_client(): records every observation, sends nothing anywhere."""

    def __init__(self, fail=False):
        self.log, self.flushes, self.fail = [], 0, fail

    def start_as_current_observation(self, *, name, as_type="span", input=None, metadata=None, **_kw):
        if self.fail:
            raise RuntimeError("viewer is down")
        self.log.append(("start", name, as_type, input))
        return _RecorderObservation(self.log, name, as_type)

    def flush(self):
        self.flushes += 1


def _fake_langfuse(client):
    module = types.ModuleType("langfuse")
    module.get_client = lambda: client
    return module


class ProvidedTraceExportTests(unittest.TestCase):
    def _one_shot(self, extra, env, modules):
        lines = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.dict(sys.modules, modules):
            for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
                if key not in env:
                    os.environ.pop(key, None)
            code = app.main(["Delete the dentist task.", "--seed", SEED, "--approve", "no", "--quiet"] + extra,
                            input_fn=lambda _: "", out=lines.append, root=tmp)
        return code, "\n".join(lines)

    def test_console_export_prints_tree_with_model_tool_and_gate(self):
        """--export console prints a span tree: the run, the model call, the tool request and the [y/N] gate answer."""
        code, text = self._one_shot(["--export", "console"], {}, {})
        self.assertEqual(code, 0)
        self.assertIn("trace (console export):", text)
        for piece in ("run ", "model single", "tool  delete_task", "gate  approve delete_task", "out=denied"):
            self.assertIn(piece, text)

    def test_no_export_by_default_prints_no_trace_tree(self):
        """Without --export nothing is exported: the trace tree only appears when you ask for it."""
        code, text = self._one_shot([], {}, {})
        self.assertEqual(code, 0)
        self.assertNotIn("trace (console export):", text)

    def test_langfuse_without_keys_or_package_falls_back_to_console(self):
        """--export langfuse with no keys, or keys but no package, prints the console tree instead and never crashes."""
        code, text = self._one_shot(["--export", "langfuse"], {}, {})
        self.assertEqual(code, 0)
        self.assertIn("no Langfuse keys", text)
        self.assertIn("trace (console export):", text)
        keys = {"LANGFUSE_PUBLIC_KEY": "pk-test-123", "LANGFUSE_SECRET_KEY": "sk-test-SECRET"}
        code, text = self._one_shot(["--export", "langfuse"], keys, {"langfuse": None})   # None = not installed
        self.assertEqual(code, 0)
        self.assertIn("package is missing", text)
        self.assertNotIn("sk-test-SECRET", text)

    def test_langfuse_export_with_recorder_fake_sends_typed_spans_and_never_prints_keys(self):
        """With keys and a (fake, offline) langfuse package, spans go out as agent/generation/tool/guardrail and are flushed."""
        client = _RecorderClient()
        keys = {"LANGFUSE_PUBLIC_KEY": "pk-test-123", "LANGFUSE_SECRET_KEY": "sk-test-SECRET"}
        code, text = self._one_shot(["--export", "langfuse"], keys, {"langfuse": _fake_langfuse(client)})
        self.assertEqual(code, 0)
        kinds = {entry[2] for entry in client.log if entry[0] == "start"}
        self.assertEqual(kinds, {"agent", "generation", "tool", "guardrail"})
        self.assertGreaterEqual(client.flushes, 1)
        self.assertIn("toy data only", text)
        self.assertNotIn("sk-test-SECRET", text)
        self.assertNotIn("pk-test-123", text)
        gen = [e for e in client.log if e[0] == "update" and e[2] == "generation"][0][3]
        self.assertEqual(gen["model"], "stand-in")   # the stand-in is never reported as a real Gemini model

    def test_broken_exporter_never_breaks_the_run(self):
        """If the trace viewer fails, the turn still finishes normally and one warning is printed."""
        keys = {"LANGFUSE_PUBLIC_KEY": "pk-test-123", "LANGFUSE_SECRET_KEY": "sk-test-SECRET"}
        code, text = self._one_shot(["--export", "langfuse"], keys, {"langfuse": _fake_langfuse(_RecorderClient(fail=True))})
        self.assertEqual(code, 0)
        self.assertIn("status: done-with-denials", text)
        self.assertEqual(text.count("trace export problem"), 1)
