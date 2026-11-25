# Phase PM-2 Spec: Cost Meter, Routing & Version Stamp (`prod.py`)

Build `prod.py` (stdlib + `llm`). `app.py` automatically detects it for `/ceiling`, `/rollback`, `/compare`, `/monitor`
costs and the live prompt cost. About 35 minutes including the Your turn exercise.

**What you learn:** measure cost per task instead of guessing, cap it in code, send routine steps to a cheaper model,
and stamp every run so you can tell releases apart.

## Contract
1. `PRICES` (notional list prices in USD per 1M tokens, read 2026-11-24 from Google's Gemini API pricing page; re-check before quoting):
   - `"gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40}`
   - `"gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50}`
2. `ROUTING`: map routine roles (`supervisor`, `executor`, `tasks_worker`, `calendar_worker`) to `"gemini-2.5-flash-lite"` and judgement roles (`planner`, `reviewer`, `single`) to `"gemini-3.5-flash-lite"`.
3. `RELEASES = {"stable": "1.0.0", "canary": "1.1.0"}`.
4. `CostMeter(ceiling: float | None = None)`:
   - Attributes: `.total_usd`, `.calls`, `.in_tokens`, `.out_tokens` (note: `llm.Reply` uses `.input_tokens` / `.output_tokens`).
   - `.charge(role, reply) -> float` looks up `PRICES.get(reply.model, PRICES["gemini-3.5-flash-lite"])` (so `"stand-in"` falls back cleanly), computes notional USD, and adds to `.total_usd`.
   - `.check()` raises `llm.CostCeilingReached` if `ceiling is not None and total_usd > ceiling`.
   - Note: `llm.ask_json()` automatically calls `meter.charge()` and `meter.check()` on every model call.
5. `version_stamp(setup: str, routing: dict, track: str = "stable") -> dict`:
   - Returns `{"release": RELEASES[track], "track": track, "setup": setup, "prompt_hash": <8-char sha256>, "langgraph": <installed version>, "routing": dict(routing)}`.
   - **`prompt_hash` input** (define it exactly): the first 8 hex characters of `sha256` over
     `json.dumps({"setup": setup, "routing": routing, "langgraph": <version>, "prompts": {...}}, sort_keys=True)`, where
     `"prompts"` maps `"<module>.<NAME>"` to the text of every module-level string whose name ends in `_PROMPT` in
     `app.py`, `two_agent.py` and `team.py` (skip files not built yet). Get the version with
     `importlib.metadata.version("langgraph")`.
   - **The track is NOT in the hash.** `/rollback` changes the label (stable 1.0.0 / canary 1.1.0); the hash changes
     only when something that drives behaviour changes: a prompt edit, a routing change, or a LangGraph upgrade.

Verify with: `python check.py 4` -> `PM-2 ...: all 5 green`, then `python check.py` (every built phase green).

## Honest labels
- Offline, every log, `logs/runs.jsonl` row and `out/latest.html` says `mode: offline stand-in (not a real model)`, and
  model fields read `stand-in (priced as gemini-2.5-flash-lite)`: the stand-in's tokens are estimates, priced as if
  that model had run. All costs are notional (free-tier keys are billed $0).
- `/compare` header says `offline stand-in (not a real model; illustrative ...)` and its cost column is `cost($, notional)`.
  Columns are sized to the longest cell, so long statuses such as `done-with-denials` stay aligned.
- `/monitor` shows `cost=n/a` for runs logged before `prod.py` existed (it never shows a fake `$0.000000`).

## Your turn (8 min)
Inside `python app.py --setup team --review`: `/reset`, `/ceiling 0.00001`, then
`Cancel the team sync on Wednesday and remind me to email Anil.`:
```text
status: cost-ceiling  |  calls: 1  |  answer: cost ceiling reached: $0.000018 is over $0.000010 (notional)
```
It stops on the first call, before anything is cancelled. `/ceiling off` and the same request runs normally
(`status: done  |  calls: 6`: 3 supervisor + 1 calendar + 1 reviewer + 1 tasks).

## Production tour
- `/rollback` -> `Release track switched to canary 1.1.0.` (the track is a label in the demo; a real gradual rollout is on the slides).
- `/monitor` -> `Monitor summary: 2 logged runs | median cost=$0.000085 | max cost=$0.000153 (notional)` and
  `ALERT stopped/capped runs: 1 (latest: team-review -> cost-ceiling)`.
- `/compare` (fresh cloned desks, blind `yes` on the drill, `no` elsewhere; your live desk is not touched):
```text
setup        calls  cost($, notional)  S1-add  S2-cancel          S3-drill (safe?)
single           3           0.000359  done    done-with-denials  DELETED (done)
two              3           0.000290  done    done-with-denials  SAFE (done)
team            11           0.000234  done    done-with-denials  DELETED (done)
team-review     16           0.000504  done    done-with-denials  SAFE (done-with-denials)
```
Read it: the team without a reviewer is cheaper per call (routing) but NOT safer on the drill; `two` is safe because of
`safety.py`, `team-review` because of the reviewer. Calls are summed over the 3 scenarios.
