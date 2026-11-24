# Edge cases, tagged by phase

Each row is something that really goes wrong in a multi-agent system. The tests cover them; the try-it commands show most of them.

| Phase | Edge case | What must happen | Where to see it |
|---|---|---|---|
| W7-0 | twelve look-alike tools; "archive" turns into delete | the gate asks; the false "done" is visible in the log | `sample-runs/00a` (REPLAYED) |
| W7-1 | the model never says final | `turn-limit` after exactly `MAX_TURNS` calls | test |
| W7-1 | a graph loop with no exit | `recursion-limit` from your explicit `recursion_limit` (default would be 10,007) | test |
| W7-1 | the model replies with prose, twice | one re-ask, then `model-error` | test |
| W7-1 | the per-run call cap is reached | `call-cap`, no extra call made | test |
| W7-1 | a reply with both `tool` and `final` | final wins, nothing runs | test |
| W7-2 | the executor reaches for a tool the plan did not name | refused by the gate: `tool X is not allowed for executor` | test |
| W7-2 | a plan with the wrong shape | `plan-rejected`, the executor never runs | test |
| W7-2 | a planned delete | the human is still asked | test, `sample-runs/01b` |
| W7-3 | a 7-step plan with an unknown tool | `plan-rejected` naming every broken rule | `sample-runs/03c` (REPLAYED) |
| W7-3 | a planted note makes the planner plan deletes | `plan-rejected`: the user's goal never asked to delete | `sample-runs/03a` |
| W7-3 | a 1,500-character note on the desk | the handoff context is cut at 600 with `[truncated]` and a WARN | `sample-runs/03b` |
| W7-3 | a task longer than 200 characters | refused (`HandoffError`), never cut | test |
| W7-4 | the supervisor keeps routing | `turn-limit` after `MAX_TURNS` routing turns | test |
| W7-4 | the supervisor invents a worker ("email") | `model-error`, no worker runs | test |
| W7-4 | the calendar worker asks for `delete_task` | refused by the allow-list, even with a human yes | test |
| W7-4 | planted note + blind human yes, no reviewer | a task is deleted and the status says `done` | `sample-runs/04b` |
| W7-5 | parallel workers write one key with no reducer | `InvalidUpdateError`, explained | `sample-runs/09c` |
| W7-5 | two parallel workers add items at once | a lock: unique ids | `extras/fanout.py` |
| W7-6 | the reviewer rejects twice | `blocked`, back to the supervisor, nothing deleted | `sample-runs/06a` |
| W7-6 | the reviewer approves, the human says no | denied: the human has the last word | `sample-runs/06b` |
| W7-6 | a read or a write (not irreversible) | no review call | test |
| W7-7 | the cost passes the ceiling mid-run | `cost-ceiling`; the pending action never runs | `sample-runs/07b` |
| W7-7 | a model missing from the price list | priced as the fallback model, never as free | test |
| W7-7 | a prompt changes | the `prompts=` hash in the stamp changes | test |
| live | `429` / `503` | `llm.py` waits with growing pauses up to 70 s, then a plain error | test with a fake client |
| live | no key | `configuration error: No API key ...`, exit 2 | test |
